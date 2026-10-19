import base64
import csv
import hashlib
import hmac
import atexit
import io
import json
import mimetypes
import os
import secrets
import shutil
import time
import threading
import uuid
import sys
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, unquote


import tts_hub_store as tts_store
import donor_store
import portability
from integration_manager import IntegrationManager


ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from safe_json import load_json as _robust_load_json, save_json as _robust_save_json
from washington_integration import WashingtonIntegration
from source_registry import public_registry
from tools.create_diagnostic_report import create_report
from integrations.donationalerts.donationalerts_integration import DonationAlertsIntegration
from integrations.streamlabs.streamlabs_integration import StreamlabsIntegration

PUBLIC = ROOT / "public"

DATA_DIR = ROOT / "data"
RUNTIME_DIR = PROJECT_ROOT / "runtime"

STATE_FILE = DATA_DIR / "state.json"
DONATIONS_FILE = DATA_DIR / "donations.json"
RATES_FILE = DATA_DIR / "rates.json"


DONATTY_STATUS_FILE = RUNTIME_DIR / "donatty_status.json"
STREAMERBOT_STATUS_FILE = RUNTIME_DIR / "streamerbot_status.json"
STREAMERBOT_SENT_FILE = PROJECT_ROOT / "integrations" / "streamerbot" / "streamerbot_sent.json"

TTS_DIR = PROJECT_ROOT / "integrations" / "tts"
TTS_QUEUE_FILE = TTS_DIR / "tts_queue.json"
TTS_AUDIO_DIR = TTS_DIR / "audio_cache"
TTS_CONFIG_FILE = TTS_DIR / "tts_config.json"
TTS_STATUS_FILE = RUNTIME_DIR / "tts_status.json"

HOST = "127.0.0.1"
PORT = 3333

VERSION_FILE = PROJECT_ROOT / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "dev"
SERVER_STARTED_AT = time.time()
BROKEN_JSON_DIR = PROJECT_ROOT / "backups" / "broken_json"
_BROKEN_JSON_BACKED_UP = set()


FILE_LOCK = threading.RLock()

INTEGRATION_MANAGER = None
DA_INTEGRATION = None
STREAMLABS_INTEGRATION = None
WASHINGTON = WashingtonIntegration(PROJECT_ROOT)


DEFAULT_RATES = {
    "baseCurrency": "RUB",
    "ratesToRUB": {
        "RUB": 1,
        "USD": 90,
        "EUR": 100,
        "KZT": 0.18
    }
}


def _backup_broken_json(path, error):
    """Сохраняет повреждённый JSON один раз за запуск, прежде чем использовать fallback."""
    try:
        path = Path(path)
        marker = str(path.resolve())
        if marker in _BROKEN_JSON_BACKED_UP or not path.exists() or path.stat().st_size == 0:
            return

        BROKEN_JSON_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{path.stem}_{stamp}{path.suffix}.broken.bak"
        backup_path = BROKEN_JSON_DIR / backup_name
        shutil.copy2(path, backup_path)
        _BROKEN_JSON_BACKED_UP.add(marker)
        print(f"[JSON] Повреждённый файл сохранён: {backup_path}")
        print(f"[JSON] Причина: {type(error).__name__}: {error}")
    except Exception as backup_error:
        print(f"[JSON] Не удалось создать резервную копию {path}: {backup_error}")


def load_json(path, fallback):
    return _robust_load_json(
        path,
        fallback,
        retries=16,
        backup_dir=BROKEN_JSON_DIR,
        backup_decode_errors=True,
    )


def save_json(path, data):
    _robust_save_json(path, data, retries=120)


def ensure_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    TTS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    BROKEN_JSON_DIR.mkdir(parents=True, exist_ok=True)
    tts_store.ensure_tts_files()
    donor_store.ensure_files()

    if not STATE_FILE.exists():
        save_json(STATE_FILE, {
            "title": "Сбор на цель",
            "current": 0,
            "baseAmount": 0,
            "goal": 10000,
            "currency": "RUB",
            "lastDonation": None
        })

    if not DONATIONS_FILE.exists():
        save_json(DONATIONS_FILE, [])

    if not RATES_FILE.exists():
        save_json(RATES_FILE, DEFAULT_RATES)



def load_rates():
    rates = load_json(RATES_FILE, DEFAULT_RATES)
    if not isinstance(rates, dict):
        rates = dict(DEFAULT_RATES)

    table = rates.get("ratesToRUB")
    if not isinstance(table, dict):
        table = dict(DEFAULT_RATES["ratesToRUB"])

    normalized_table = {}
    for key, value in table.items():
        currency = normalize_currency(key)
        number = to_number(value, 0)
        if number > 0:
            normalized_table[currency] = number

    normalized_table.setdefault("RUB", 1)

    return {
        "baseCurrency": normalize_currency(rates.get("baseCurrency") or "RUB"),
        "ratesToRUB": normalized_table
    }


def save_rates(rates):
    table = rates.get("ratesToRUB") if isinstance(rates, dict) else None
    if not isinstance(table, dict):
        table = {}

    normalized_table = {}
    for key, value in table.items():
        currency = normalize_currency(key)
        number = to_number(value, 0)
        if number > 0:
            normalized_table[currency] = number

    normalized_table.setdefault("RUB", 1)

    result = {
        "baseCurrency": "RUB",
        "ratesToRUB": dict(sorted(normalized_table.items()))
    }
    save_json(RATES_FILE, result)
    return result


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def bool_from_any(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "y", "да", "д", "on"):
        return True
    if text in ("false", "0", "no", "n", "нет", "н", "off"):
        return False
    return default


def normalize_state(state):
    if not isinstance(state, dict):
        state = {}

    state.setdefault("title", "Сбор на цель")
    state.setdefault("current", 0)
    state.setdefault("baseAmount", 0)
    state.setdefault("goal", 10000)
    state.setdefault("currency", "RUB")
    state.setdefault("lastDonation", None)
    return state


def normalize_donation_record(donation, state=None):
    if state is None:
        state = load_json(STATE_FILE, {})

    source = str(donation.get("source") or "manual")
    external_id = str(donation.get("externalId") or donation.get("external_id") or donation.get("externalID") or uuid.uuid4())
    unique_key = str(donation.get("uniqueKey") or f"{source}:{external_id}")

    amount = to_number(donation.get("amount"), 0)
    currency = normalize_currency(donation.get("currency"))
    goal_currency = normalize_currency(state.get("currency", "RUB"))

    amount_for_goal = donation.get("amountForGoal")
    if amount_for_goal is None:
        amount_for_goal = convert_to_goal_currency(amount, currency, goal_currency)
    else:
        amount_for_goal = to_number(amount_for_goal, 0)

    created_at = str(donation.get("createdAt") or donation.get("created_at") or "")
    received_at = str(donation.get("receivedAt") or donation.get("received_at") or created_at or now_iso())

    # Авто-донаты из сервисов по умолчанию отправляем в Streamer.bot,
    # а ручные донаты — только если ты явно поставил галочку в админке.
    default_notify_streamerbot = source != "manual"

    return {
        "uniqueKey": unique_key,
        "source": source,
        "externalId": external_id,
        "username": str(donation.get("username") or donation.get("name") or "Аноним"),
        "amount": amount,
        "currency": currency,
        "amountForGoal": round(amount_for_goal, 2),
        "includeInGoal": bool_from_any(donation.get("includeInGoal"), True),
        "notifyStreamerBot": bool_from_any(donation.get("notifyStreamerBot"), default_notify_streamerbot),
        "triggerDonationEvents": bool_from_any(donation.get("triggerDonationEvents"), source != "manual"),
        "speakTTS": bool_from_any(donation.get("speakTTS"), source != "manual"),
        "includeInTop": bool_from_any(donation.get("includeInTop"), True),
        "donorId": str(donation.get("donorId") or ""),
        "amountForTop": round(to_number(
            donation.get("amountForTop") if donation.get("amountForTop") is not None
            else convert_to_goal_currency(amount, currency, donor_store.TOP_CURRENCY),
            0
        ), 2),
        "topCurrency": donor_store.TOP_CURRENCY,
        "message": str(donation.get("message") or ""),
        "anonymous": bool_from_any(donation.get("anonymous"), str(donation.get("username") or donation.get("name") or "Аноним").lower() in ("аноним", "anonymous")),
        "createdAt": created_at,
        "receivedAt": received_at,
        "note": str(donation.get("note") or "")
    }


def normalize_storage():
    """Load and normalize persistent storage without rewriting unchanged files.

    The admin UI polls `/api/state` and `/api/donations` frequently. Older builds
    rewrote both JSON files on every GET, which created Windows sharing races with
    Streamer.bot Bridge and antivirus software. v1.4.3 writes only when migration
    or recalculation actually changes data.
    """
    with FILE_LOCK:
        raw_state = load_json(STATE_FILE, {})
        raw_donations = load_json(DONATIONS_FILE, [])
        if not isinstance(raw_donations, list):
            raw_donations = []

        state = normalize_state(dict(raw_state) if isinstance(raw_state, dict) else {})
        normalized = []
        seen = set()
        for donation in raw_donations:
            if not isinstance(donation, dict):
                continue
            item = normalize_donation_record(donation, state)
            if item["uniqueKey"] in seen:
                continue
            seen.add(item["uniqueKey"])
            normalized.append(item)

        normalized, _profiles = donor_store.sync_donations(normalized)
        recalc_goal_current(state, normalized)

        if normalized != raw_donations:
            save_json(DONATIONS_FILE, normalized)
        if state != raw_state:
            save_json(STATE_FILE, state)
        return state, normalized


def recalc_goal_current(state, donations):
    state = normalize_state(state)
    base = max(0, to_number(state.get("baseAmount"), 0))
    total = base

    for donation in donations:
        if bool_from_any(donation.get("includeInGoal"), True):
            total += to_number(donation.get("amountForGoal"), 0)

    state["baseAmount"] = round(base, 2)
    state["current"] = round(total, 2)
    state["lastDonation"] = donations[-1] if donations else None
    return state


def load_state():
    with FILE_LOCK:
        state = normalize_state(load_json(STATE_FILE, {}))
        donations = load_json(DONATIONS_FILE, [])
        if isinstance(donations, list):
            recalc_goal_current(state, donations)
        return state


def save_state(state):
    with FILE_LOCK:
        save_json(STATE_FILE, normalize_state(state))


def load_donations():
    with FILE_LOCK:
        donations = load_json(DONATIONS_FILE, [])
        if not isinstance(donations, list):
            return []
        state = normalize_state(load_json(STATE_FILE, {}))
        return [normalize_donation_record(d, state) for d in donations if isinstance(d, dict)]


def save_donations(donations):
    with FILE_LOCK:
        save_json(DONATIONS_FILE, donations)


def normalize_currency(currency):
    currency = (currency or "RUB").strip().upper()
    return currency or "RUB"


def to_number(value, default=0):
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def convert_to_goal_currency(amount, currency, goal_currency):
    currency = normalize_currency(currency)
    goal_currency = normalize_currency(goal_currency)

    if currency == goal_currency:
        return amount

    rates_to_rub = load_rates().get("ratesToRUB", {})
    source_rate = to_number(rates_to_rub.get(currency), 0)
    goal_rate = to_number(rates_to_rub.get(goal_currency), 0)

    if source_rate > 0 and goal_rate > 0:
        return amount * source_rate / goal_rate

    # Если курс неизвестен, не ломаем приём доната, но добавляем сумму как есть.
    # В админке можно будет добавить курс и пересохранить валюту цели/донат.
    return amount


def add_donation(donation):
    with FILE_LOCK:
        state = normalize_state(load_json(STATE_FILE, {}))
        donations = load_json(DONATIONS_FILE, [])
        if not isinstance(donations, list):
            donations = []

        normalized = normalize_donation_record(donation, state)

        for old in donations:
            if old.get("uniqueKey") == normalized["uniqueKey"]:
                return state, False, "Этот донат уже был учтён"

        if normalized["amount"] <= 0:
            return state, False, "Сумма должна быть больше нуля"

        donations.append(normalized)
        donations, _profiles = donor_store.sync_donations(donations)
        recalc_goal_current(state, donations)

        save_json(DONATIONS_FILE, donations)
        save_json(STATE_FILE, state)

        # Only newly persisted donations reach this hook; replay/import never do.
        try:
            WASHINGTON.submit(normalized, normalize_currency(state.get("currency", "RUB")))
        except Exception as error:
            print(f"[Washington] enqueue_failed: {type(error).__name__}")
        return state, True, "Донат добавлен"


def update_donation(update_data):
    with FILE_LOCK:
        state = normalize_state(load_json(STATE_FILE, {}))
        donations = load_json(DONATIONS_FILE, [])
        if not isinstance(donations, list):
            donations = []

        unique_key = str(update_data.get("uniqueKey") or "")
        if not unique_key:
            return state, False, "Не передан uniqueKey"

        changed = None
        for index, old in enumerate(donations):
            old = normalize_donation_record(old, state)
            if old.get("uniqueKey") != unique_key:
                donations[index] = old
                continue

            if "username" in update_data:
                old["username"] = str(update_data.get("username") or "Аноним")
            if "message" in update_data:
                old["message"] = str(update_data.get("message") or "")
            if "note" in update_data:
                old["note"] = str(update_data.get("note") or "")
            if "includeInGoal" in update_data:
                old["includeInGoal"] = bool_from_any(update_data.get("includeInGoal"), True)
            if "notifyStreamerBot" in update_data:
                old["notifyStreamerBot"] = bool_from_any(update_data.get("notifyStreamerBot"), False)
            if "triggerDonationEvents" in update_data:
                old["triggerDonationEvents"] = bool_from_any(update_data.get("triggerDonationEvents"), False)
            if "speakTTS" in update_data:
                old["speakTTS"] = bool_from_any(update_data.get("speakTTS"), False)
            if "includeInTop" in update_data:
                old["includeInTop"] = bool_from_any(update_data.get("includeInTop"), True)
            if "amount" in update_data:
                old["amount"] = to_number(update_data.get("amount"), old.get("amount", 0))
            if "currency" in update_data:
                old["currency"] = normalize_currency(update_data.get("currency"))

            old["amountForGoal"] = round(convert_to_goal_currency(
                to_number(old.get("amount"), 0),
                old.get("currency", "RUB"),
                state.get("currency", "RUB")
            ), 2)
            if "amount" in update_data or "currency" in update_data:
                old["amountForTop"] = round(convert_to_goal_currency(
                    to_number(old.get("amount"), 0),
                    old.get("currency", "RUB"),
                    donor_store.TOP_CURRENCY
                ), 2)
                old["topCurrency"] = donor_store.TOP_CURRENCY

            donations[index] = old
            changed = old
            break

        if changed is None:
            return state, False, "Донат не найден"

        donations, _profiles = donor_store.sync_donations(donations)
        recalc_goal_current(state, donations)
        save_json(DONATIONS_FILE, donations)
        save_json(STATE_FILE, state)

        return state, True, "Донат обновлён"


def delete_donation(delete_data):
    with FILE_LOCK:
        state = normalize_state(load_json(STATE_FILE, {}))
        donations = load_json(DONATIONS_FILE, [])
        if not isinstance(donations, list):
            donations = []

        unique_key = str(delete_data.get("uniqueKey") or "")
        if not unique_key:
            return state, False, "Не передан uniqueKey"

        new_donations = [d for d in donations if d.get("uniqueKey") != unique_key]
        if len(new_donations) == len(donations):
            return state, False, "Донат не найден"

        normalized = [normalize_donation_record(d, state) for d in new_donations if isinstance(d, dict)]
        recalc_goal_current(state, normalized)
        save_json(DONATIONS_FILE, normalized)
        save_json(STATE_FILE, state)

        return state, True, "Донат удалён"


def reset_goal_progress_keep_history():
    with FILE_LOCK:
        state = normalize_state(load_json(STATE_FILE, {}))
        donations = load_json(DONATIONS_FILE, [])
        if not isinstance(donations, list):
            donations = []

        normalized = []
        for donation in donations:
            if not isinstance(donation, dict):
                continue
            item = normalize_donation_record(donation, state)
            item["includeInGoal"] = False
            normalized.append(item)

        state["baseAmount"] = 0
        recalc_goal_current(state, normalized)
        save_json(DONATIONS_FILE, normalized)
        save_json(STATE_FILE, state)
        return state


def get_integration_manager():
    global INTEGRATION_MANAGER, DA_INTEGRATION, STREAMLABS_INTEGRATION
    if INTEGRATION_MANAGER is None:
        DA_INTEGRATION = DonationAlertsIntegration(
            PROJECT_ROOT,
            add_donation=add_donation,
            load_json=load_json,
            save_json=save_json,
        )
        STREAMLABS_INTEGRATION = StreamlabsIntegration(
            PROJECT_ROOT,
            add_donation=add_donation,
            load_json=load_json,
            save_json=save_json,
        )
        INTEGRATION_MANAGER = IntegrationManager(PROJECT_ROOT)
        INTEGRATION_MANAGER.register_adapter("donationalerts", DA_INTEGRATION)
        INTEGRATION_MANAGER.register_adapter("streamlabs", STREAMLABS_INTEGRATION)
    return INTEGRATION_MANAGER


def get_da_integration():
    get_integration_manager()
    return DA_INTEGRATION


def get_streamlabs_integration():
    get_integration_manager()
    return STREAMLABS_INTEGRATION


def html_page(title, body):
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#111827; color:#f9fafb; font-family:Arial,sans-serif; }}
    .card {{ width:min(720px,calc(100% - 32px)); padding:28px; border-radius:18px; background:#1f2937; line-height:1.55; }}
    a {{ color:#67e8f9; }} code {{ background:#111827; padding:2px 6px; border-radius:6px; }}
  </style>
</head>
<body><div class="card">{body}</div></body>
</html>"""


def read_json_file_status(path, stale_after=20):
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}

    updated_at = to_number(data.get("updatedAt"), 0)
    age = max(0, time.time() - updated_at) if updated_at else None
    data["stale"] = bool(age is None or age > stale_after)
    data["ageSeconds"] = round(age, 1) if age is not None else None
    return data




def load_tts_queue():
    data = load_json(TTS_QUEUE_FILE, [])
    if isinstance(data, dict):
        data = data.get("queue", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def save_tts_queue(queue):
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    save_json(TTS_QUEUE_FILE, [item for item in queue if isinstance(item, dict)])


def load_tts_public_config():
    config = load_json(TTS_CONFIG_FILE, {})
    if not isinstance(config, dict):
        config = {}

    volume = to_number(config.get("volume"), 0.9)
    volume = max(0, min(volume, 1))

    return {
        "enabled": bool_from_any(config.get("enabled"), False),
        "volume": volume,
        "pollIntervalMs": int(max(250, to_number(config.get("browser_poll_interval_ms"), 700))),
        "delayAfterDoneMs": int(max(0, to_number(config.get("delay_after_done_ms"), 500)))
    }


def build_tts_status():
    queue = load_tts_queue()
    file_count = 0
    try:
        if TTS_AUDIO_DIR.exists():
            file_count = len([p for p in TTS_AUDIO_DIR.iterdir() if p.is_file()])
    except Exception:
        file_count = 0

    listener_status = read_json_file_status(TTS_STATUS_FILE, stale_after=20)

    return {
        "listener": listener_status,
        "queueLength": len(queue),
        "audioFiles": file_count,
        "publicConfig": load_tts_public_config()
    }


def remove_tts_task(task_id):
    task_id = str(task_id or "")
    if not task_id:
        return False

    with FILE_LOCK:
        queue = load_tts_queue()
        new_queue = [item for item in queue if str(item.get("id") or "") != task_id]
        changed = len(new_queue) != len(queue)
        if changed:
            save_tts_queue(new_queue)
        return changed


def build_system_status():
    manager = get_integration_manager()
    bootstrap = manager.bootstrap()
    integrations = bootstrap.get("integrations", []) if isinstance(bootstrap, dict) else []
    by_id = {item.get("id"): item for item in integrations if isinstance(item, dict)}
    da_summary = by_id.get("donationalerts", {})
    donatty_summary = by_id.get("donatty", {})
    da_status = dict(da_summary.get("status", {}))
    da_status.update({"configured": da_summary.get("configured", False), "enabled": da_summary.get("enabled", False), "running": da_summary.get("running", False), "connected": da_summary.get("connected", False)})
    donatty_status = dict(donatty_summary.get("status", {}))
    donatty_status.update({"configured": donatty_summary.get("configured", False), "enabled": donatty_summary.get("enabled", False), "running": donatty_summary.get("running", False), "connected": donatty_summary.get("connected", False)})

    enabled_integrations = [item for item in integrations if item.get("enabled")]
    configured_integrations = [item for item in integrations if item.get("configured")]
    connected_integrations = [item for item in enabled_integrations if item.get("commonState") == "connected"]
    attention_integrations = [item for item in enabled_integrations if item.get("commonState") in {"degraded", "error", "stopped", "unconfigured"}]

    streamerbot = read_json_file_status(STREAMERBOT_STATUS_FILE, stale_after=15)
    streamerbot_config = load_json(PROJECT_ROOT / "integrations/streamerbot/streamerbot_config.json", {})
    sb_enabled = bool(streamerbot_config.get("enabled", True)) if isinstance(streamerbot_config, dict) else True
    if not sb_enabled:
        sb_state = "disabled"
    elif streamerbot.get("running") and not streamerbot.get("stale"):
        sb_state = "degraded" if streamerbot.get("lastError") else "connected"
    elif streamerbot.get("lastError"):
        sb_state = "error"
    elif streamerbot.get("stale"):
        sb_state = "error"
    else:
        sb_state = "stopped"
    streamerbot["enabled"] = sb_enabled
    streamerbot["commonState"] = sb_state

    tts = tts_store.public_status()
    tts_config = tts.get("config", {}) if isinstance(tts, dict) else {}
    tts_runtime = tts.get("runtime", {}) if isinstance(tts, dict) else {}
    tts_enabled = bool(tts_config.get("enabled", True))
    if not tts_enabled:
        tts_state = "disabled"
    elif tts_runtime.get("running") and not tts_runtime.get("stale"):
        tts_state = "degraded" if tts_runtime.get("lastError") else "connected"
    elif tts_runtime.get("lastError"):
        tts_state = "error"
    elif tts_runtime.get("stale"):
        tts_state = "error"
    else:
        tts_state = "stopped"
    tts["commonState"] = tts_state

    integration_manager_state = "connected"
    if any(item.get("commonState") == "error" for item in enabled_integrations):
        integration_manager_state = "degraded"

    system_modules = [
        {
            "id": "core", "name": "Core Server", "commonState": "connected",
            "text": "локальный сервер работает", "detail": f"v{APP_VERSION}; uptime {round(max(0, time.time() - SERVER_STARTED_AT))} сек.",
        },
        {
            "id": "integration-manager", "name": "Integration Manager", "commonState": integration_manager_state,
            "text": f"{len(connected_integrations)} из {len(enabled_integrations)} включённых подключены",
            "detail": f"Всего {len(integrations)}; настроено {len(configured_integrations)}; требуют внимания {len(attention_integrations)}",
        },
        {
            "id": "streamerbot", "name": "Streamer.bot Bridge", "commonState": sb_state,
            "text": "bridge работает" if sb_state == "connected" else (streamerbot.get("lastError") or "bridge не отвечает"),
            "detail": streamerbot.get("lastEvent") or (f"heartbeat {streamerbot.get('ageSeconds')} сек. назад" if streamerbot.get("ageSeconds") is not None else ""),
        },
        {
            "id": "tts", "name": "TTS Hub", "commonState": tts_state,
            "text": str(tts_runtime.get("provider") or tts_config.get("activeProvider") or "провайдер не выбран"),
            "detail": f"очередь {tts.get('queueLength', 0)}; история {tts.get('historyCount', 0)}" + (f"; {tts_runtime.get('lastError')}" if tts_runtime.get("lastError") else ""),
        },
    ]

    return {
        "version": APP_VERSION,
        "server": {
            "running": True,
            "version": APP_VERSION,
            "updatedAt": time.time(),
            "time": now_iso(),
            "uptimeSeconds": round(max(0, time.time() - SERVER_STARTED_AT), 1)
        },
        "systemModules": system_modules,
        "integrationManager": {
            "commonState": integration_manager_state,
            "total": len(integrations),
            "enabled": len(enabled_integrations),
            "configured": len(configured_integrations),
            "connected": len(connected_integrations),
            "attention": len(attention_integrations),
        },
        "sourceRegistry": public_registry(),
        "integrations": bootstrap,
        "donationAlerts": da_status,
        "donatty": donatty_status,
        "streamerbot": streamerbot,
        "tts": tts
    }


def load_streamerbot_sent():
    data = load_json(STREAMERBOT_SENT_FILE, {"sent": []})
    if isinstance(data, list):
        return {"sent": [str(x) for x in data]}
    if not isinstance(data, dict):
        return {"sent": []}
    sent = data.get("sent", [])
    if not isinstance(sent, list):
        sent = []
    return {"sent": [str(x) for x in sent]}


def save_streamerbot_sent(data):
    STREAMERBOT_SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_json(STREAMERBOT_SENT_FILE, {"sent": sorted(set(str(x) for x in data.get("sent", [])))})


def replay_donation(replay_data):
    with FILE_LOCK:
        state = normalize_state(load_json(STATE_FILE, {}))
        donations = load_json(DONATIONS_FILE, [])
        if not isinstance(donations, list):
            donations = []

        unique_key = str(replay_data.get("uniqueKey") or "")
        if not unique_key:
            return state, False, "Не передан uniqueKey"

        found = None
        for index, donation in enumerate(donations):
            item = normalize_donation_record(donation, state)
            if item.get("uniqueKey") == unique_key:
                item["notifyStreamerBot"] = True
                donations[index] = item
                found = item
                break
            donations[index] = item

        if found is None:
            return state, False, "Донат не найден"

        sent_file_existed = STREAMERBOT_SENT_FILE.exists()
        sent_data = load_streamerbot_sent()

        if sent_file_existed:
            sent_data["sent"] = [key for key in sent_data.get("sent", []) if key != unique_key]
        else:
            # Если bridge ещё ни разу не запускался, не даём ему потом проиграть всю старую историю.
            sent_data["sent"] = [
                normalize_donation_record(d, state).get("uniqueKey")
                for d in donations
                if isinstance(d, dict) and normalize_donation_record(d, state).get("uniqueKey") != unique_key
            ]

        save_streamerbot_sent(sent_data)

        recalc_goal_current(state, donations)
        save_json(DONATIONS_FILE, donations)
        save_json(STATE_FILE, state)

        return state, True, "Оповещение поставлено в очередь Streamer.bot"


def bulk_update_donations(data):
    allowed = {"includeInGoal", "notifyStreamerBot", "triggerDonationEvents", "speakTTS", "includeInTop"}
    field = str(data.get("field") or "")
    if field not in allowed:
        return False, "Неизвестный флаг", 0
    value = bool_from_any(data.get("value"), False)
    with FILE_LOCK:
        state = normalize_state(load_json(STATE_FILE, {}))
        donations = load_json(DONATIONS_FILE, [])
        if not isinstance(donations, list):
            donations = []
        normalized = []
        for donation in donations:
            if not isinstance(donation, dict):
                continue
            item = normalize_donation_record(donation, state)
            item[field] = value
            normalized.append(item)
        normalized, _profiles = donor_store.sync_donations(normalized)
        recalc_goal_current(state, normalized)
        save_json(DONATIONS_FILE, normalized)
        save_json(STATE_FILE, state)
        return True, f"Флаг {field} изменён у всех донатов", len(normalized)


def donor_top_payload(query=""):
    state, donations = normalize_storage()
    return donor_store.build_top(donations, query=query)


def donor_detail_payload(profile_id):
    state, donations = normalize_storage()
    return donor_store.get_detail(profile_id, donations)


def _csv_safe_text(value):
    """Защита Excel/LibreOffice от выполнения пользовательского текста как формулы."""
    text = str(value if value is not None else "")
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _csv_force_text(value):
    """Сохраняет длинные ID и ISO-даты как текст, а не scientific notation."""
    text = str(value if value is not None else "")
    if not text:
        return ""
    return '="' + text.replace('"', '""') + '"'


def donations_to_csv_bytes(donations):
    output = io.StringIO(newline="")
    output.write("sep=;\r\n")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([
        "receivedAt",
        "createdAt",
        "source",
        "username",
        "amount",
        "currency",
        "amountForGoal",
        "includeInGoal",
        "notifyStreamerBot",
        "triggerDonationEvents",
        "speakTTS",
        "includeInTop",
        "donorId",
        "amountForTop",
        "topCurrency",
        "message",
        "note",
        "uniqueKey",
        "externalId"
    ])

    for donation in donations:
        writer.writerow([
            _csv_force_text(donation.get("receivedAt", "")),
            _csv_force_text(donation.get("createdAt", "")),
            _csv_safe_text(donation.get("source", "")),
            _csv_safe_text(donation.get("username", "")),
            donation.get("amount", ""),
            _csv_safe_text(donation.get("currency", "")),
            donation.get("amountForGoal", ""),
            donation.get("includeInGoal", ""),
            donation.get("notifyStreamerBot", ""),
            donation.get("triggerDonationEvents", ""),
            donation.get("speakTTS", ""),
            donation.get("includeInTop", ""),
            _csv_force_text(donation.get("donorId", "")),
            donation.get("amountForTop", ""),
            _csv_safe_text(donation.get("topCurrency", donor_store.TOP_CURRENCY)),
            _csv_safe_text(donation.get("message", "")),
            _csv_safe_text(donation.get("note", "")),
            _csv_force_text(donation.get("uniqueKey", "")),
            _csv_force_text(donation.get("externalId", ""))
        ])

    return ("\ufeff" + output.getvalue()).encode("utf-8")


def portability_status_payload():
    files = portability.collect_user_files(PROJECT_ROOT)
    return {
        "ok": True,
        "appVersion": APP_VERSION,
        "backupSchemaVersion": portability.BACKUP_SCHEMA_VERSION,
        "userFileCount": len(files),
        "userDataSize": sum(path.stat().st_size for path in files if path.exists()),
        "backups": portability.list_local_backups(PROJECT_ROOT),
        "categories": sorted({portability.category_for_path(path.relative_to(PROJECT_ROOT).as_posix()) for path in files}),
    }


def _donationalerts_alias_totals(donations):
    totals = {}
    for donation in donations:
        if not isinstance(donation, dict) or str(donation.get("source") or "").lower() != "donationalerts":
            continue
        key = donor_store.alias_key("donationalerts", donation.get("username"))
        totals[key] = round(totals.get(key, 0) + to_number(
            donation.get("amountForTop") if donation.get("amountForTop") is not None else donation.get("amountForGoal"), 0
        ), 2)
    return totals


def donationalerts_import_preview(rows, donations):
    aggregated = {}
    display_names = {}
    for row in rows:
        username = str(row.get("username") or "Аноним").strip() or "Аноним"
        key = donor_store.alias_key("donationalerts", username)
        aggregated[key] = round(aggregated.get(key, 0) + to_number(row.get("amount"), 0), 2)
        display_names.setdefault(key, username)

    actual = _donationalerts_alias_totals(donations)
    profiles = donor_store.load_profiles()
    profile_by_alias = {}
    for profile in profiles:
        for alias in profile.get("aliases", []):
            profile_by_alias[donor_store.alias_key(alias.get("source"), alias.get("username"))] = profile
    adjustments = donor_store.load_adjustments()
    snapshot_by_key = {
        str(item.get("snapshotKey") or ""): item
        for item in adjustments
        if item.get("kind") == "source_snapshot" and item.get("source") == "donationalerts"
    }
    manual_by_profile = {}
    for item in adjustments:
        if item.get("kind") == "source_snapshot":
            continue
        profile_id = str(item.get("donorId") or "")
        manual_by_profile[profile_id] = manual_by_profile.get(profile_id, 0) + to_number(item.get("amountForTop"), 0)

    preview_rows = []
    total_export = 0
    total_change = 0
    recommended_change = 0
    overlap_profiles = set()
    review_rows = 0
    for key in sorted(aggregated, key=lambda item: (-aggregated[item], display_names[item].casefold())):
        exported = round(aggregated[key], 2)
        recorded = round(actual.get(key, 0), 2)
        proposed_snapshot = round(max(exported - recorded, 0), 2)
        current_snapshot = round(to_number(snapshot_by_key.get(key, {}).get("amountForTop"), 0), 2)
        change = round(proposed_snapshot - current_snapshot, 2)
        profile = profile_by_alias.get(key)
        manual_amount = round(manual_by_profile.get(str((profile or {}).get("id") or ""), 0), 2)
        if profile and abs(manual_amount) >= 0.005:
            overlap_profiles.add(profile.get("id"))
        requires_review = bool(abs(change) >= 0.005 and abs(manual_amount) >= 0.005 and abs(current_snapshot) < 0.005)
        selected_by_default = bool(abs(change) >= 0.005 and not requires_review)
        if requires_review:
            review_rows += 1
        if selected_by_default:
            recommended_change += change
        total_export += exported
        total_change += change
        preview_rows.append({
            "importKey": key,
            "username": display_names[key],
            "exported": exported,
            "recordedEvents": recorded,
            "currentSnapshot": current_snapshot,
            "proposedSnapshot": proposed_snapshot,
            "change": change,
            "profileName": (profile or {}).get("displayName") or display_names[key],
            "manualAdjustments": manual_amount,
            "requiresReview": requires_review,
            "selectedByDefault": selected_by_default,
        })

    warnings = [
        "Файл содержит итог по каждому имени, а не отдельные донаты. Он изменит только TopDonation.",
        "Импорт не запустит TTS, Streamer.bot, донат-ивенты и не изменит текущий сбор.",
    ]
    if overlap_profiles:
        warnings.append(
            f"У {len(overlap_profiles)} профилей уже есть ручные корректировки. {review_rows} спорных строк сняты с выбора по умолчанию, чтобы не задвоить исторические суммы."
        )
    return {
        "kind": "donationalerts",
        "compatible": True,
        "rows": len(preview_rows),
        "exportedTotal": round(total_export, 2),
        "topChange": round(total_change, 2),
        "recommendedTopChange": round(recommended_change, 2),
        "possibleOverlapProfiles": len(overlap_profiles),
        "reviewRows": review_rows,
        "items": preview_rows,
        "warnings": warnings,
    }


def create_user_backup(reason="manual", group="manual"):
    # Keep history, donor profiles and TTS stores at one Core state while the
    # snapshot is read. Separate workers are checked by the stable capture.
    with FILE_LOCK, donor_store.LOCK, tts_store.LOCK:
        return portability.write_backup(PROJECT_ROOT, reason=reason, group=group)


def apply_staged_import(token, options=None):
    # No donation may arrive between the rollback snapshot and applying/undoing
    # an import; otherwise a rollback could erase that new donation.
    with FILE_LOCK, donor_store.LOCK, tts_store.LOCK:
        return _apply_staged_import_locked(token, options)


def _apply_staged_import_locked(token, options=None):
    options = options if isinstance(options, dict) else {}
    metadata, raw = portability.load_stage(PROJECT_ROOT, token)
    kind = str(metadata.get("kind") or "")
    if kind in {"backup", "folder"}:
        from tools.update_from_old import ensure_stopped
        ensure_stopped(PROJECT_ROOT, allow_core=True)
    backup_path, backup_manifest = create_user_backup(
        reason=f"before_{kind}_import",
        group="automatic",
    )
    restart_required = False
    result = {"kind": kind}
    new_import_paths = []

    try:
        with FILE_LOCK:
            if kind == "backup":
                _manifest, payload = portability.inspect_backup_bytes(raw, current_version=APP_VERSION)
                from tools.update_from_old import prepare_payload
                payload, _ = prepare_payload(payload, existing=portability._capture_user_payload(PROJECT_ROOT))
                new_import_paths = [portability._user_data_destination(PROJECT_ROOT, p) for p in payload
                                    if not portability._user_data_destination(PROJECT_ROOT, p).exists()]
                restored = portability.apply_payload(PROJECT_ROOT, payload)
                normalize_storage()
                restart_required = True
                result.update({"restoredFiles": len(restored), "sourceVersion": metadata.get("preview", {}).get("sourceVersion")})
            elif kind == "folder":
                payload = portability.payload_from_staged_folder(raw)
                from tools.update_from_old import prepare_payload
                payload, _ = prepare_payload(payload, existing=portability._capture_user_payload(PROJECT_ROOT))
                new_import_paths = [portability._user_data_destination(PROJECT_ROOT, p) for p in payload
                                    if not portability._user_data_destination(PROJECT_ROOT, p).exists()]
                restored = portability.apply_payload(PROJECT_ROOT, payload)
                normalize_storage()
                restart_required = True
                result.update({"restoredFiles": len(restored), "sourceVersion": metadata.get("preview", {}).get("sourceVersion")})
            elif kind == "donations":
                incoming = portability.parse_donations_bytes(raw)
                state = normalize_state(load_json(STATE_FILE, {}))
                existing = load_json(DONATIONS_FILE, [])
                if not isinstance(existing, list):
                    existing = []
                merged, stats = portability.merge_donations(
                    incoming,
                    existing,
                    lambda item: normalize_donation_record(item, state),
                    include_in_goal=bool(options.get("includeInGoal", False)),
                )
                merged, _profiles = donor_store.sync_donations(merged)
                recalc_goal_current(state, merged)
                save_json(DONATIONS_FILE, merged)
                save_json(STATE_FILE, state)
                result.update(stats)
            elif kind == "donationalerts":
                rows = portability.parse_donationalerts_table(raw)
                donations = load_donations()
                actual = _donationalerts_alias_totals(donations)
                aggregated = {}
                names = {}
                for row in rows:
                    username = str(row.get("username") or "Аноним").strip() or "Аноним"
                    key = donor_store.alias_key("donationalerts", username)
                    aggregated[key] = round(aggregated.get(key, 0) + to_number(row.get("amount"), 0), 2)
                    names.setdefault(key, username)
                staged_preview = metadata.get("preview") if isinstance(metadata.get("preview"), dict) else {}
                preview_items = staged_preview.get("items") if isinstance(staged_preview.get("items"), list) else []
                default_keys = {
                    str(item.get("importKey") or "")
                    for item in preview_items
                    if isinstance(item, dict) and item.get("selectedByDefault")
                }
                requested_keys = options.get("selectedKeys")
                selected_keys = {
                    str(item) for item in requested_keys
                } if isinstance(requested_keys, list) else default_keys
                selected_keys &= set(aggregated)
                batch_id = f"da-import-{uuid.uuid4()}"
                changed = 0
                skipped = 0
                snapshot_total = 0
                for key, exported in aggregated.items():
                    if key not in selected_keys:
                        skipped += 1
                        continue
                    _profile, item, delta = donor_store.upsert_source_snapshot(
                        "donationalerts",
                        names[key],
                        exported,
                        actual.get(key, 0),
                        batch_id=batch_id,
                    )
                    snapshot_total += delta
                    if item is not None or abs(delta) < 0.005:
                        changed += 1
                result.update({
                    "profilesProcessed": changed,
                    "rowsSkipped": skipped,
                    "snapshotTotal": round(snapshot_total, 2),
                    "batchId": batch_id,
                })
            else:
                raise portability.PortabilityError("Неизвестный тип импорта")
    except Exception as import_error:
        try:
            _rollback_manifest, rollback_payload = portability.inspect_backup_bytes(backup_path.read_bytes())
            portability.apply_payload(PROJECT_ROOT, rollback_payload)
            for path in new_import_paths:
                # Re-resolve on rollback as well: never follow a changed parent
                # outside the project when removing an introduced file.
                relative = path.relative_to(PROJECT_ROOT.resolve()).as_posix()
                portability._user_data_destination(PROJECT_ROOT, relative).unlink(missing_ok=True)
            normalize_storage()
        except Exception as rollback_error:
            raise portability.PortabilityError(
                f"Импорт прерван, но автоматический откат тоже не выполнен: {rollback_error}. "
                f"Исходный бэкап: {backup_path.name}"
            ) from import_error
        raise portability.PortabilityError(
            f"Импорт прерван; исходные данные автоматически восстановлены из {backup_path.name}: {import_error}"
        ) from import_error

    portability.delete_stage(PROJECT_ROOT, token)
    result.update({
        "ok": True,
        "message": "Импорт завершён",
        "restartRequired": restart_required,
        "automaticBackup": backup_path.name,
        "backupCreatedAt": backup_manifest.get("createdAt"),
    })
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html, code=200):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, content_type="application/octet-stream", code=200, extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _read_chunked_body(self, max_bytes=4 * 1024 * 1024):
        chunks = []
        total = 0
        while True:
            size_line = self.rfile.readline(128)
            if not size_line:
                break
            size_text = size_line.strip().split(b";", 1)[0]
            try:
                size = int(size_text, 16)
            except ValueError as error:
                raise ValueError("Некорректное chunked-тело запроса") from error
            if size == 0:
                # Consume optional trailer headers and the final empty line.
                while True:
                    trailer = self.rfile.readline(8192)
                    if trailer in (b"", b"\r\n", b"\n"):
                        break
                break
            total += size
            if total > max_bytes:
                raise ValueError(f"Тело запроса превышает {max_bytes // (1024 * 1024)} МБ")
            chunks.append(self.rfile.read(size))
            ending = self.rfile.read(2)
            if ending not in (b"\r\n", b"\n"):
                raise ValueError("Некорректное завершение chunked-блока")
        return b"".join(chunks)

    def read_body_bytes(self, max_bytes=4 * 1024 * 1024):
        transfer_encoding = str(self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in transfer_encoding:
            raw_bytes = self._read_chunked_body(max_bytes=max_bytes)
        else:
            length = int(self.headers.get("Content-Length") or 0)
            if length < 0 or length > max_bytes:
                raise ValueError("Некорректный размер тела запроса")
            raw_bytes = self.rfile.read(length) if length else b""

        self._last_raw_body = raw_bytes
        return raw_bytes

    def read_body_json(self, max_bytes=4 * 1024 * 1024):
        raw_bytes = self.read_body_bytes(max_bytes=max_bytes)
        if not raw_bytes:
            return {}
        raw = raw_bytes.decode("utf-8", errors="replace")

        try:
            return json.loads(raw)
        except Exception:
            parsed = parse_qs(raw)
            return {key: values[0] if values else "" for key, values in parsed.items()}

    def require_local_portability_request(self):
        host = str(self.headers.get("Host") or "").split(":", 1)[0].lower()
        origin = str(self.headers.get("Origin") or "").lower()
        if host not in {"127.0.0.1", "localhost", "::1", ""}:
            self.send_json({"ok": False, "message": "Операции с данными доступны только локально"}, 403)
            return False
        if origin and not (origin.startswith("http://127.0.0.1") or origin.startswith("http://localhost")):
            self.send_json({"ok": False, "message": "Недопустимый Origin для операции с данными"}, 403)
            return False
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        host = str(self.headers.get("Host") or "").split(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost", "::1", ""}:
            self.send_json({"ok": False, "message": "External access is limited to signed integration webhooks"}, 404)
            return

        if path == "/":
            self.redirect("/widget.html")
            return

        if path == "/api/washington":
            try:
                self.send_json({"config": WASHINGTON.config(), "status": WASHINGTON.status(), "sources": public_registry()})
            except ValueError as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/health":
            self.send_json({
                "ok": True,
                "service": "VicDonationGoal",
                "version": APP_VERSION,
                "time": now_iso(),
                "uptimeSeconds": round(max(0, time.time() - SERVER_STARTED_AT), 1)
            })
            return

        if path == "/api/state":
            state, donations = normalize_storage()
            self.send_json(state)
            return

        if path == "/api/donations":
            state, donations = normalize_storage()
            self.send_json(donations)
            return

        if path == "/api/donations/export.csv":
            state, donations = normalize_storage()
            self.send_bytes(
                donations_to_csv_bytes(donations),
                content_type="text/csv; charset=utf-8",
                extra_headers={"Content-Disposition": "attachment; filename=donations_export.csv"}
            )
            return

        if path == "/api/portability/status":
            self.send_json(portability_status_payload())
            return

        if path == "/api/portability/backup":
            try:
                backup_path, manifest = create_user_backup(reason="manual_download", group="manual")
                self.send_bytes(
                    backup_path.read_bytes(),
                    content_type="application/zip",
                    extra_headers={
                        "Content-Disposition": f'attachment; filename="{backup_path.name}"',
                        "X-VicDonationGoal-Backup-Schema": str(manifest.get("schemaVersion")),
                    },
                )
            except Exception as error:
                self.send_json({"ok": False, "message": f"Не удалось создать резервную копию: {type(error).__name__}: {error}"}, 500)
            return

        if path == "/api/donors/top":
            qs = parse_qs(parsed.query)
            query = str(qs.get("q", [""])[0])
            self.send_json(donor_top_payload(query))
            return

        if path == "/api/donors/detail":
            qs = parse_qs(parsed.query)
            profile_id = str(qs.get("id", [""])[0])
            detail = donor_detail_payload(profile_id)
            self.send_json({"ok": bool(detail), "detail": detail}, 200 if detail else 404)
            return

        if path == "/api/donors/export.csv":
            qs = parse_qs(parsed.query)
            profile_id = str(qs.get("id", [""])[0])
            state, donations = normalize_storage()
            body, filename = donor_store.donor_csv_bytes(profile_id, donations)
            if body is None:
                self.send_json({"ok": False, "message": "Донатер не найден"}, 404)
                return
            self.send_bytes(
                body,
                content_type="text/csv; charset=utf-8",
                extra_headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
            return

        if path == "/api/rates":
            self.send_json(load_rates())
            return

        if path == "/api/status":
            self.send_json(build_system_status())
            return

        if path == "/api/tts/status":
            self.send_json(tts_store.public_status())
            return

        if path == "/api/tts/bootstrap":
            self.send_json({
                "ok": True,
                "config": tts_store.get_config(),
                "profiles": tts_store.get_profiles(),
                "rules": tts_store.get_rules(),
                "queue": tts_store.get_queue(),
                "control": tts_store.get_control(),
                "status": tts_store.public_status()
            })
            return

        if path == "/api/tts/config":
            self.send_json(tts_store.get_config())
            return

        if path == "/api/tts/profiles":
            self.send_json(tts_store.get_profiles())
            return

        if path == "/api/tts/rules":
            self.send_json(tts_store.get_rules())
            return

        if path == "/api/tts/queue":
            self.send_json(tts_store.get_queue())
            return

        if path == "/api/tts/history":
            qs = parse_qs(parsed.query)
            limit = int(max(1, to_number(qs.get("limit", ["200"])[0], 200)))
            self.send_json(tts_store.get_history(limit))
            return

        if path == "/api/tts/logs":
            qs = parse_qs(parsed.query)
            limit = int(max(1, to_number(qs.get("limit", ["200"])[0], 200)))
            self.send_json(tts_store.get_logs(limit))
            return

        if path == "/api/tts/control-state":
            self.send_json(tts_store.get_control())
            return

        if path == "/api/tts/player-status":
            self.send_json(tts_store.get_player_status())
            return

        if path == "/api/tts/next":
            config = tts_store.get_config()
            queue = tts_store.get_queue()
            ready = next((item for item in queue if str(item.get("status")) == "ready" and item.get("audioUrl")), None)
            public_config = {
                "provider": config.get("activeProvider"),
                "volume": max(0, min(to_number(config.get("browserVolume"), 0.9), 1)),
                "pollIntervalMs": int(max(250, to_number(config.get("queue", {}).get("browserPollIntervalMs"), 500))),
                "delayAfterDoneMs": int(max(0, to_number(config.get("queue", {}).get("browserDelayAfterDoneMs"), 250))),
                "maxPlayAttempts": int(max(1, to_number(config.get("queue", {}).get("browserMaxPlayAttempts"), 3))),
                "stopToken": int(tts_store.get_control().get("stopToken", 0) or 0)
            }
            if ready:
                updated = tts_store.update_job(str(ready.get("id")), {"status": "playing", "startedPlayingAt": now_iso()})
                task = updated or ready
                task = dict(task)
                task["text"] = task.get("cleanedText") or task.get("originalText") or ""
                task["volume"] = public_config["volume"]
                self.send_json({"ok": True, "task": task, "queueLength": len(queue), "config": public_config})
            else:
                self.send_json({"ok": False, "task": None, "queueLength": len(queue), "config": public_config})
            return

        if path.startswith("/api/tts/audio/"):
            filename = Path(unquote(path.split("/api/tts/audio/", 1)[1])).name
            if not filename:
                self.send_response(404)
                self.end_headers()
                return

            file_path = tts_store.AUDIO_DIR / filename
            if not file_path.exists() or not file_path.is_file():
                self.send_response(404)
                self.end_headers()
                return

            content_type = mimetypes.guess_type(str(file_path))[0] or "audio/mpeg"
            self.send_bytes(file_path.read_bytes(), content_type=content_type)
            return

        if path == "/api/source-registry":
            self.send_json({"ok": True, "sources": public_registry()})
            return

        if path == "/api/integrations":
            self.send_json(get_integration_manager().bootstrap())
            return

        if path == "/api/integrations/detail":
            qs = parse_qs(parsed.query)
            integration_id = str(qs.get("id", [""])[0])
            try:
                self.send_json(get_integration_manager().detail(integration_id))
            except KeyError as error:
                self.send_json({"ok": False, "message": str(error)}, 404)
            return

        if path == "/api/integrations/logs":
            qs = parse_qs(parsed.query)
            integration_id = str(qs.get("id", [""])[0])
            limit = int(max(1, to_number(qs.get("limit", ["250"])[0], 250)))
            try:
                self.send_json(get_integration_manager().logs(integration_id, limit))
            except KeyError as error:
                self.send_json({"ok": False, "message": str(error)}, 404)
            return

        if path == "/api/da/status":
            self.send_json(get_da_integration().public_status())
            return

        if path == "/admin/add":
            qs = parse_qs(parsed.query)
            donation = {
                "source": qs.get("source", ["manual"])[0],
                "externalId": qs.get("externalId", [str(uuid.uuid4())])[0],
                "username": qs.get("username", ["Аноним"])[0],
                "amount": qs.get("amount", ["0"])[0],
                "currency": qs.get("currency", ["RUB"])[0],
                "message": qs.get("message", [""])[0],
                "includeInGoal": qs.get("includeInGoal", ["true"])[0],
                "notifyStreamerBot": qs.get("notifyStreamerBot", ["false"])[0],
                "triggerDonationEvents": qs.get("triggerDonationEvents", ["false"])[0],
                "speakTTS": qs.get("speakTTS", ["false"])[0]
            }
            state, ok, message = add_donation(donation)
            self.send_json({"ok": ok, "message": message, "state": state})
            return

        if path == "/auth/donationalerts/start":
            self.da_auth_start()
            return

        if path == "/auth/donationalerts/callback":
            self.da_auth_callback(parsed)
            return

        if path == "/auth/streamlabs/start":
            self.streamlabs_auth_start()
            return

        if path == "/auth/streamlabs/callback":
            self.streamlabs_auth_callback(parsed)
            return

        self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/api/washington/config", "/api/washington/test", "/api/washington/check"):
            if not self.require_local_portability_request():
                return
            try:
                if path.endswith('/config'):
                    result = {"ok": True, "config": WASHINGTON.save_config(self.read_body_json())}
                elif path.endswith('/test'):
                    ok = WASHINGTON.test(normalize_currency(load_state().get('currency', 'RUB')))
                    result = {"ok": ok, "message": "Тест поставлен в очередь; сообщение будет отправлено в Twitch" if ok else "Очередь заполнена"}
                else:
                    result = {"ok": True, "status": WASHINGTON.check()}
                self.send_json(result)
            except (ValueError, TypeError) as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            except Exception as error:
                self.send_json({"ok": False, "message": type(error).__name__}, 500)
            return

        if path == "/api/portability/stage":
            if not self.require_local_portability_request():
                return
            try:
                query = parse_qs(parsed.query)
                kind = str(query.get("kind", [""])[0]).strip().lower()
                filename = str(query.get("filename", ["import.bin"])[0])
                raw = self.read_body_bytes(max_bytes=portability.MAX_UPLOAD_BYTES)
                if not raw:
                    raise portability.PortabilityError("Выбранный файл пуст")
                state, donations = normalize_storage()
                if kind == "backup":
                    preview = portability.backup_preview(raw, APP_VERSION)
                elif kind == "donations":
                    incoming = portability.parse_donations_bytes(raw)
                    preview = portability.donation_preview(
                        incoming,
                        donations,
                        lambda item: normalize_donation_record(item, state),
                    )
                elif kind == "donationalerts":
                    rows = portability.parse_donationalerts_table(raw)
                    preview = donationalerts_import_preview(rows, donations)
                else:
                    raise portability.PortabilityError("Неизвестный тип импорта")
                token = portability.create_stage(PROJECT_ROOT, kind, filename, raw, preview)
                self.send_json({"ok": True, "token": token, "preview": preview})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/portability/stage-folder":
            if not self.require_local_portability_request():
                return
            try:
                request = self.read_body_json(max_bytes=96 * 1024 * 1024)
                payload = portability.folder_payload_from_request(request.get("files"))
                source_version = str(request.get("sourceVersion") or "unknown")
                preview = portability.folder_preview(payload, APP_VERSION, source_version=source_version)
                token = portability.create_folder_stage(PROJECT_ROOT, payload, preview)
                self.send_json({"ok": True, "token": token, "preview": preview})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/portability/stage-local-backup":
            if not self.require_local_portability_request():
                return
            try:
                request = self.read_body_json()
                backup_path = portability.resolve_local_backup(PROJECT_ROOT, request.get("id"))
                raw = backup_path.read_bytes()
                preview = portability.backup_preview(raw, APP_VERSION)
                token = portability.create_stage(PROJECT_ROOT, "backup", backup_path.name, raw, preview)
                self.send_json({"ok": True, "token": token, "preview": preview})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/portability/apply":
            if not self.require_local_portability_request():
                return
            manager = None
            restart_integrations = False
            try:
                request = self.read_body_json()
                token = str(request.get("token") or "")
                metadata, _raw = portability.load_stage(PROJECT_ROOT, token)
                restart_integrations = metadata.get("kind") in {"backup", "folder"}
                if restart_integrations:
                    manager = get_integration_manager()
                    manager.stop_all()
                result = apply_staged_import(token, options=request.get("options"))
                if restart_integrations and manager is not None:
                    manager.start_enabled()
                self.send_json(result)
            except Exception as error:
                if restart_integrations and manager is not None:
                    try:
                        manager.start_enabled()
                    except Exception:
                        pass
                self.send_json({"ok": False, "message": f"Импорт не выполнен: {type(error).__name__}: {error}"}, 400)
            return

        data = self.read_body_json()

        if path.startswith("/api/integrations/tribute/webhook/"):
            status_path = PROJECT_ROOT / "runtime/integrations/tribute_status.json"
            debug_path = PROJECT_ROOT / "runtime/integrations/tribute_last_webhook.json"

            def update_tribute_status(**values):
                status = load_json(status_path, {})
                status.update(values)
                status["updatedAt"] = time.time()
                save_json(status_path, status)

            try:
                manifest_config = get_integration_manager()._load_config("tribute")
                if manifest_config.get("widget_url"):
                    self.send_json({"status":"error", "message":"Tribute подключён по OBS-ссылке; прежний webhook отключён"}, 410)
                    return
                expected_secret = str(manifest_config.get("webhook_secret") or "")
                actual_secret = unquote(path.rsplit("/", 1)[-1])
                raw_body = getattr(self, "_last_raw_body", b"")
                event_name = str(data.get("name") or data.get("event") or data.get("type") or "unknown") if isinstance(data, dict) else "unknown"
                request_meta = {
                    "receivedAt": now_iso(),
                    "eventName": event_name,
                    "bodyBytes": len(raw_body),
                    "contentType": str(self.headers.get("Content-Type") or ""),
                    "transferEncoding": str(self.headers.get("Transfer-Encoding") or ""),
                    "signaturePresent": bool(self.headers.get("trbt-signature")),
                    "topLevelKeys": sorted(str(key) for key in data.keys()) if isinstance(data, dict) else [],
                    "payloadKeys": sorted(str(key) for key in (data.get("payload") or {}).keys()) if isinstance(data, dict) and isinstance(data.get("payload"), dict) else [],
                }

                if not expected_secret or not secrets.compare_digest(actual_secret, expected_secret):
                    update_tribute_status(
                        lastWebhookAt=now_iso(), lastWebhookHttpStatus=404,
                        lastWebhookReason="webhook_secret_mismatch", lastWebhookMeta=request_meta,
                        lastError="Webhook URL secret не совпадает",
                    )
                    self.send_json({"status": "error", "message": "Webhook not found"}, 404)
                    return

                api_key = str(manifest_config.get("api_key") or "")
                raw_signature = str(self.headers.get("trbt-signature") or "").strip().strip('"')
                signature_candidates = []
                if raw_signature:
                    signature_candidates.append(raw_signature)
                    for part in raw_signature.split(","):
                        part = part.strip()
                        if "=" in part:
                            key, value = part.split("=", 1)
                            if key.strip().lower() in {"sha256", "v1", "signature", "sig"}:
                                signature_candidates.append(value.strip().strip('"'))
                    for prefix in ("sha256=", "v1="):
                        if raw_signature.lower().startswith(prefix):
                            signature_candidates.append(raw_signature[len(prefix):].strip())

                digest = hmac.new(api_key.encode("utf-8"), raw_body, hashlib.sha256).digest()
                expected_hex = digest.hex()
                expected_b64 = base64.b64encode(digest).decode("ascii")
                expected_b64url = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
                signature_ok = bool(api_key and signature_candidates) and any(
                    hmac.compare_digest(candidate.lower(), expected_hex.lower())
                    or hmac.compare_digest(candidate, expected_b64)
                    or hmac.compare_digest(candidate.rstrip("="), expected_b64.rstrip("="))
                    or hmac.compare_digest(candidate.rstrip("="), expected_b64url)
                    for candidate in signature_candidates
                )
                if not signature_ok:
                    update_tribute_status(
                        lastWebhookAt=now_iso(), lastWebhookHttpStatus=401,
                        lastWebhookReason="invalid_signature", lastWebhookMeta=request_meta,
                        lastError="Tribute webhook дошёл, но подпись trbt-signature не совпала",
                    )
                    self.send_json({"status": "error", "message": "Invalid Tribute signature"}, 401)
                    return

                # Save the last verified payload locally for private debugging.
                save_json(debug_path, {"meta": request_meta, "data": data})

                from integrations.base.common import extract_donations
                donations = [] if event_name == "vicdonationgoal_test" else extract_donations(data, "tribute", "RUB", "Tribute webhook")
                accepted = 0
                messages = []
                for donation in donations:
                    _state, ok, message = add_donation(donation)
                    messages.append(message)
                    accepted += 1 if ok else 0

                payload_uuid = ""
                if isinstance(data, dict) and isinstance(data.get("payload"), dict):
                    payload_uuid = str((data.get("payload") or {}).get("uuid") or "")
                event_id = str((donations[0] if donations else {}).get("externalId") or payload_uuid)
                if not event_id:
                    event_id = str(data.get("id") or data.get("name") or "unknown") if isinstance(data, dict) else "unknown"
                update_tribute_status(
                    running=True, connected=True, status="webhook_received",
                    lastEvent=event_id, lastError=None, lastWebhookAt=now_iso(),
                    lastWebhookHttpStatus=200, lastWebhookReason="ok",
                    lastWebhookMeta=request_meta, lastWebhookFound=len(donations),
                    lastWebhookAccepted=accepted,
                )
                self.send_json({"status": "ok", "accepted": accepted, "found": len(donations), "messages": messages}, 200)
            except Exception as error:
                try:
                    update_tribute_status(
                        lastWebhookAt=now_iso(), lastWebhookHttpStatus=400,
                        lastWebhookReason="handler_error",
                        lastError=f"{type(error).__name__}: {error}",
                    )
                except Exception:
                    pass
                self.send_json({"status": "error", "message": f"{type(error).__name__}: {error}"}, 400)
            return

        host = str(self.headers.get("Host") or "").split(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost", "::1", ""}:
            self.send_json({"ok": False, "message": "External access is limited to signed integration webhooks"}, 404)
            return

        if path == "/api/diagnostics/create":
            try:
                archive = create_report(PROJECT_ROOT)
                self.send_json({"ok": True, "message": "Диагностический отчёт создан", "path": str(archive)})
            except Exception as error:
                self.send_json({"ok": False, "message": f"{type(error).__name__}: {error}"}, 500)
            return


        if path == "/api/tts/config":
            try:
                saved = tts_store.save_config(data)
                self.send_json({"ok": True, "message": "Настройки TTS сохранены", "config": saved})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/tts/profiles":
            try:
                saved = tts_store.save_profiles(data)
                self.send_json({"ok": True, "message": "Голосовые профили сохранены", "profiles": saved})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/tts/rules":
            try:
                saved = tts_store.save_rules(data)
                self.send_json({"ok": True, "message": "Правила TTS сохранены", "rules": saved})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/tts/rules/test":
            try:
                result = tts_store.test_routing(data)
                self.send_json(result, 200 if result.get("ok") else 400)
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/tts/enqueue":
            try:
                job, created, message = tts_store.enqueue_job(data)
                self.send_json({"ok": True, "created": created, "message": message, "job": job})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/tts/test":
            payload = {
                "eventType": str(data.get("eventType") or "manual_test"),
                "source": str(data.get("source") or "admin"),
                "username": str(data.get("username") or "TTS Test"),
                "userId": str(data.get("userId") or ""),
                "roles": data.get("roles") or [],
                "rewardId": str(data.get("rewardId") or ""),
                "amount": data.get("amount"),
                "amountForGoal": data.get("amountForGoal"),
                "text": str(data.get("text") or "Это тестовое сообщение VicDonationGoal."),
                "profileId": str(data.get("profileId") or ""),
                "provider": str(data.get("provider") or ""),
                "bypassMinAmount": True,
                "priority": 1,
                "origin": "admin-test"
            }
            try:
                job, created, message = tts_store.enqueue_job(payload)
                self.send_json({"ok": True, "created": created, "message": message, "job": job})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/tts/job/update":
            job_id = data.get("id") or data.get("jobId")
            patch = data.get("patch") if isinstance(data.get("patch"), dict) else {}
            job = tts_store.update_job(job_id, patch)
            self.send_json(
                {"ok": bool(job), "message": "TTS задача обновлена" if job else "TTS задача не найдена", "job": job},
                200 if job else 404
            )
            return

        if path == "/api/tts/job/complete":
            job_id = data.get("id") or data.get("jobId")
            status = str(data.get("status") or "played")
            error = str(data.get("error") or "")
            job = tts_store.complete_job(job_id, status=status, error=error)
            self.send_json(
                {"ok": bool(job), "message": "TTS задача завершена" if job else "TTS задача не найдена", "job": job},
                200 if job else 404
            )
            return

        if path == "/api/tts/job/retry":
            job_id = data.get("id") or data.get("jobId")
            job = tts_store.retry_history_job(job_id)
            self.send_json(
                {"ok": bool(job), "message": "TTS задача повторно поставлена в очередь" if job else "Запись истории не найдена", "job": job},
                200 if job else 404
            )
            return

        if path == "/api/tts/job/delete":
            job_id = data.get("id") or data.get("jobId")
            job = tts_store.remove_job(job_id)
            self.send_json(
                {"ok": bool(job), "message": "TTS задача удалена" if job else "TTS задача не найдена", "job": job},
                200 if job else 404
            )
            return

        if path == "/api/tts/history/delete":
            job_id = data.get("id") or data.get("jobId")
            job = tts_store.delete_history_job(job_id)
            self.send_json(
                {"ok": bool(job), "message": "Запись TTS удалена" if job else "Запись истории не найдена", "job": job},
                200 if job else 404
            )
            return

        if path == "/api/tts/history/clear":
            count = tts_store.clear_history()
            self.send_json({"ok": True, "message": f"История TTS очищена: {count}", "count": count})
            return

        if path == "/api/tts/clear":
            count = tts_store.clear_queue()
            self.send_json({"ok": True, "message": f"Очередь очищена: {count}", "count": count})
            return

        if path == "/api/tts/control":
            try:
                action = str(data.get("action") or "")
                command = tts_store.enqueue_command(action)
                self.send_json({"ok": True, "message": f"TTS команда: {action}", "command": command, "control": tts_store.get_control()})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/tts/control/consume":
            command_id = data.get("id") or data.get("commandId")
            ok = tts_store.consume_command(command_id)
            self.send_json({"ok": ok, "message": "Команда обработана" if ok else "Команда не найдена"}, 200 if ok else 404)
            return

        if path == "/api/tts/player-heartbeat":
            try:
                status = tts_store.update_player_status(data)
                self.send_json({"ok": True, "player": status})
            except Exception as error:
                self.send_json({"ok": False, "message": str(error)}, 400)
            return

        if path == "/api/tts/done":
            task_id = data.get("id") or data.get("taskId")
            job = tts_store.complete_job(task_id, status="played")
            self.send_json(
                {"ok": bool(job), "message": "TTS проигран" if job else "TTS задача не найдена", "job": job},
                200 if job else 404
            )
            return

        if path == "/api/tts/fail":
            task_id = str(data.get("id") or data.get("taskId") or "")
            error_message = str(data.get("error") or "Ошибка проигрывания")
            queue = tts_store.get_queue()
            job = next((item for item in queue if str(item.get("id")) == task_id), None)
            if not job:
                self.send_json({"ok": False, "message": "TTS задача не найдена"}, 404)
                return

            config = tts_store.get_config()
            max_attempts = int(max(1, to_number(config.get("queue", {}).get("browserMaxPlayAttempts"), 3)))
            attempts = int(max(0, to_number(job.get("playAttempts"), 0))) + 1
            if attempts >= max_attempts:
                completed = tts_store.complete_job(task_id, status="error", error=error_message)
                self.send_json({"ok": True, "removed": True, "attempts": attempts, "job": completed})
            else:
                updated = tts_store.update_job(task_id, {
                    "status": "ready",
                    "playAttempts": attempts,
                    "error": error_message,
                    "lastPlayErrorAt": now_iso()
                })
                self.send_json({"ok": True, "removed": False, "attempts": attempts, "job": updated})
            return

        if path == "/api/tts/skip":
            task_id = data.get("id") or data.get("taskId")
            job = tts_store.complete_job(task_id, status="cancelled", error="Пропущено вручную")
            self.send_json(
                {"ok": bool(job), "message": "TTS задача пропущена" if job else "TTS задача не найдена", "job": job},
                200 if job else 404
            )
            return

        if path == "/api/donations/bulk-update":
            ok, message, count = bulk_update_donations(data)
            self.send_json({"ok": ok, "message": message, "count": count}, 200 if ok else 400)
            return

        if path == "/api/donors/update":
            profile_id = str(data.get("id") or data.get("donorId") or "")
            profile = donor_store.update_profile(profile_id, data)
            self.send_json({"ok": bool(profile), "message": "Профиль донатера обновлён" if profile else "Донатер не найден", "profile": profile}, 200 if profile else 404)
            return

        if path == "/api/donors/adjustment/add":
            profile_id = str(data.get("id") or data.get("donorId") or "")
            amount = to_number(data.get("amount"), 0)
            currency = normalize_currency(data.get("currency") or donor_store.TOP_CURRENCY)
            if amount == 0:
                self.send_json({"ok": False, "message": "Сумма корректировки не может быть нулевой"}, 400)
                return
            amount_for_top = convert_to_goal_currency(amount, currency, donor_store.TOP_CURRENCY)
            item = donor_store.add_adjustment(profile_id, amount, currency, amount_for_top, data.get("note"), data.get("createdAt"))
            self.send_json({"ok": bool(item), "message": "Корректировка добавлена" if item else "Донатер не найден", "adjustment": item}, 200 if item else 404)
            return

        if path == "/api/donors/adjustment/delete":
            ok = donor_store.delete_adjustment(data.get("id") or data.get("adjustmentId"))
            self.send_json({"ok": ok, "message": "Корректировка удалена" if ok else "Корректировка не найдена"}, 200 if ok else 404)
            return

        if path == "/api/donors/merge":
            target_id = str(data.get("targetId") or "")
            source_id = str(data.get("sourceId") or "")
            with FILE_LOCK:
                state = normalize_state(load_json(STATE_FILE, {}))
                donations = load_json(DONATIONS_FILE, [])
                if not isinstance(donations, list):
                    donations = []
                donations = [normalize_donation_record(item, state) for item in donations if isinstance(item, dict)]
                donations, target = donor_store.merge_profiles(target_id, source_id, donations)
                if not target:
                    self.send_json({"ok": False, "message": "Не удалось объединить профили"}, 400)
                    return
                save_json(DONATIONS_FILE, donations)
            self.send_json({"ok": True, "message": "Донатеры объединены", "profile": target})
            return

        if path == "/api/donors/delete-all":
            profile_id = str(data.get("id") or data.get("donorId") or "")
            with FILE_LOCK:
                state = normalize_state(load_json(STATE_FILE, {}))
                donations = load_json(DONATIONS_FILE, [])
                if not isinstance(donations, list):
                    donations = []
                donations = [normalize_donation_record(item, state) for item in donations if isinstance(item, dict)]
                donations, removed = donor_store.delete_all_for_profile(profile_id, donations)
                if removed <= 0:
                    self.send_json({"ok": False, "message": "У донатера не найдено донатов"}, 404)
                    return
                recalc_goal_current(state, donations)
                save_json(DONATIONS_FILE, donations)
                save_json(STATE_FILE, state)
            self.send_json({"ok": True, "message": f"Удалено донатов: {removed}", "removed": removed, "state": state})
            return

        if path == "/api/donation":
            state, ok, message = add_donation(data)
            self.send_json({"ok": ok, "message": message, "state": state}, 200 if ok else 400)
            return

        if path == "/api/donation/update":
            state, ok, message = update_donation(data)
            self.send_json({"ok": ok, "message": message, "state": state}, 200 if ok else 400)
            return

        if path == "/api/donation/delete":
            state, ok, message = delete_donation(data)
            self.send_json({"ok": ok, "message": message, "state": state}, 200 if ok else 400)
            return

        if path == "/api/donation/replay":
            state, ok, message = replay_donation(data)
            self.send_json({"ok": ok, "message": message, "state": state}, 200 if ok else 400)
            return

        if path == "/api/rates":
            with FILE_LOCK:
                rates = save_rates(data)
                state = normalize_state(load_json(STATE_FILE, {}))
                donations = load_json(DONATIONS_FILE, [])
                if not isinstance(donations, list):
                    donations = []
                donations = [normalize_donation_record(d, state) for d in donations if isinstance(d, dict)]
                recalc_goal_current(state, donations)
                save_json(DONATIONS_FILE, donations)
                save_json(STATE_FILE, state)
            self.send_json({"ok": True, "message": "Курсы сохранены", "rates": rates, "state": state})
            return

        if path == "/api/set-goal":
            with FILE_LOCK:
                state = normalize_state(load_json(STATE_FILE, {}))
                donations = load_json(DONATIONS_FILE, [])
                if not isinstance(donations, list):
                    donations = []

                if "title" in data:
                    state["title"] = str(data.get("title") or "Сбор на цель")
                if "baseAmount" in data:
                    state["baseAmount"] = max(0, to_number(data.get("baseAmount"), 0))
                elif "current" in data:
                    included_total = sum(
                        to_number(d.get("amountForGoal"), 0)
                        for d in donations
                        if bool_from_any(d.get("includeInGoal"), True)
                    )
                    state["baseAmount"] = max(0, to_number(data.get("current"), 0) - included_total)
                if "goal" in data:
                    state["goal"] = max(1, to_number(data.get("goal"), 1))
                if "currency" in data:
                    state["currency"] = normalize_currency(data.get("currency"))
                    donations = [normalize_donation_record(d, state) for d in donations if isinstance(d, dict)]

                recalc_goal_current(state, donations)
                save_json(DONATIONS_FILE, donations)
                save_json(STATE_FILE, state)

            self.send_json({"ok": True, "message": "Цель обновлена", "state": state})
            return

        if path == "/api/reset":
            state = reset_goal_progress_keep_history()
            self.send_json({"ok": True, "message": "Прогресс сброшен, история сохранена", "state": state})
            return

        if path == "/api/undo-last":
            with FILE_LOCK:
                state = normalize_state(load_json(STATE_FILE, {}))
                donations = load_json(DONATIONS_FILE, [])
                if not isinstance(donations, list):
                    donations = []

                if not donations:
                    self.send_json({"ok": False, "message": "Донатов пока нет", "state": state}, 400)
                    return

                donations.pop()
                donations = [normalize_donation_record(d, state) for d in donations if isinstance(d, dict)]
                recalc_goal_current(state, donations)
                save_json(DONATIONS_FILE, donations)
                save_json(STATE_FILE, state)

            self.send_json({"ok": True, "message": "Последний донат удалён", "state": state})
            return

        if path.startswith("/api/integrations/"):
            manager = get_integration_manager()
            integration_id = str(data.get("id") or "")
            try:
                if path == "/api/integrations/config":
                    result = manager.save_config(integration_id, data.get("config") or {})
                    self.send_json(result)
                elif path == "/api/integrations/enable":
                    self.send_json(manager.set_enabled(integration_id, bool_from_any(data.get("enabled"), False)))
                elif path == "/api/integrations/start":
                    self.send_json(manager.start(integration_id))
                elif path == "/api/integrations/stop":
                    self.send_json(manager.stop(integration_id))
                elif path == "/api/integrations/restart":
                    self.send_json(manager.restart(integration_id))
                elif path == "/api/integrations/test":
                    result = manager.test(integration_id, cancel=bool_from_any(data.get("cancel"), False))
                    self.send_json(result, 200 if result.get("ok") else 400)
                elif path == "/api/integrations/clear-auth":
                    result = manager.clear_auth(integration_id)
                    self.send_json(result, 200 if result.get("ok") else 400)
                elif path == "/api/integrations/onboarding":
                    self.send_json(manager.save_onboarding(data))
                else:
                    self.send_json({"ok": False, "message": "Неизвестная команда Integration Hub"}, 404)
            except KeyError as error:
                self.send_json({"ok": False, "message": str(error)}, 404)
            except Exception as error:
                self.send_json({"ok": False, "message": f"{type(error).__name__}: {error}"}, 400)
            return

        if path == "/api/da/start":
            self.send_json(get_integration_manager().start("donationalerts"))
            return

        if path == "/api/da/stop":
            self.send_json(get_integration_manager().stop("donationalerts"))
            return

        self.send_json({"ok": False, "message": "Неизвестный адрес"}, 404)

    def da_auth_start(self):
        try:
            target = get_da_integration().begin_oauth()
            self.redirect(target)
        except Exception as error:
            self.send_html(html_page(
                "DonationAlerts не готов",
                f"<h1>Не удалось начать авторизацию</h1><p><code>{type(error).__name__}: {error}</code></p><p>Откройте <a href='/admin.html'>Integration Hub</a>, заполните настройки и повторите.</p>"
            ), 400)

    def da_auth_callback(self, parsed):
        qs = parse_qs(parsed.query)
        error = qs.get("error", [None])[0]
        code = qs.get("code", [None])[0]
        state = qs.get("state", [None])[0]
        if error:
            self.send_html(html_page("Ошибка DonationAlerts", f"<h1>DonationAlerts вернул ошибку</h1><p><code>{error}</code></p>"), 400)
            return
        try:
            get_da_integration().finish_oauth(code, state)
            self.send_html(html_page(
                "DonationAlerts подключен",
                "<h1>DonationAlerts подключен</h1><p>Токены сохранены локально, listener запущен.</p><p><a href='/admin.html'>Вернуться в Integration Hub</a></p>"
            ))
        except Exception as error:
            self.send_html(html_page(
                "Ошибка DonationAlerts",
                f"<h1>Не удалось завершить авторизацию</h1><p><code>{type(error).__name__}: {error}</code></p><p><a href='/admin.html'>Вернуться в Integration Hub</a></p>"
            ), 500)

    def streamlabs_auth_start(self):
        try:
            target = get_streamlabs_integration().begin_oauth()
            self.redirect(target)
        except Exception as error:
            self.send_html(html_page(
                "Streamlabs не готов",
                f"<h1>Не удалось начать авторизацию</h1><p><code>{type(error).__name__}: {error}</code></p><p>Откройте <a href='/admin.html'>Integration Hub</a>, заполните настройки и повторите.</p>"
            ), 400)

    def streamlabs_auth_callback(self, parsed):
        qs = parse_qs(parsed.query)
        error = qs.get("error", [None])[0]
        code = qs.get("code", [None])[0]
        state = qs.get("state", [None])[0]
        if error:
            self.send_html(html_page("Ошибка Streamlabs", f"<h1>Streamlabs вернул ошибку</h1><p><code>{error}</code></p>"), 400)
            return
        try:
            get_streamlabs_integration().finish_oauth(code, state)
            self.send_html(html_page(
                "Streamlabs подключён",
                "<h1>Streamlabs подключён</h1><p>OAuth-токены сохранены локально, listener запущен.</p><p><a href='/admin.html'>Вернуться в Integration Hub</a></p>"
            ))
        except Exception as error:
            self.send_html(html_page(
                "Ошибка Streamlabs",
                f"<h1>Не удалось завершить авторизацию</h1><p><code>{type(error).__name__}: {error}</code></p><p><a href='/admin.html'>Вернуться в Integration Hub</a></p>"
            ), 500)

    def redirect(self, target):
        self.send_response(302)
        self.send_header("Location", target)
        self.end_headers()

    def serve_static(self, path):
        safe_path = unquote(path).replace("\\", "/").lstrip("/")
        file_path = None
        if portability._safe_relative_path(safe_path):
            try:
                public_root = PUBLIC.resolve()
                candidate = (public_root / safe_path).resolve()
                if candidate.is_relative_to(public_root):
                    file_path = candidate
            except (OSError, ValueError, RuntimeError):
                pass
        if file_path is None or not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            self.wfile.write("Not found".encode("utf-8"))
            return

        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        body = file_path.read_bytes()

        self.send_response(200)
        if content_type.startswith("text/") or content_type == "application/javascript":
            self.send_header("Content-Type", content_type + "; charset=utf-8")
        else:
            self.send_header("Content-Type", content_type)
        if content_type.startswith("text/") or content_type == "application/javascript":
            self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class VicThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    ensure_files()
    normalize_storage()
    WASHINGTON.start()
    manager = get_integration_manager()

    print("")
    print("==============================================")
    print(f" VicDonationGoal v{APP_VERSION} запущен")
    print("==============================================")
    print(f" Health check:       http://{HOST}:{PORT}/api/health")
    print(f" Виджет для OBS:     http://{HOST}:{PORT}/widget.html")
    print(f" TTS Browser Source: http://{HOST}:{PORT}/tts.html")
    print(f" Админка:            http://{HOST}:{PORT}/admin.html")
    print(f" Integration Hub:    http://{HOST}:{PORT}/admin.html#integrationsPanel")
    print("")
    print(" Чтобы остановить сервер: закрой это окно или нажми Ctrl+C")
    print("")

    try:
        server = VicThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as error:
        print(f"[SERVER] Не удалось запустить {HOST}:{PORT}: {error}")
        print("[SERVER] Возможно, сервер уже запущен или порт занят другой программой.")
        return

    # External integrations start only after Core is ready to accept their events.
    manager.start_enabled()
    atexit.register(manager.stop_all)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] Остановка...")
    finally:
        WASHINGTON.stop.set()
        manager.stop_all()
        server.server_close()
        print("[SERVER] Остановлено.")


if __name__ == "__main__":
    main()
