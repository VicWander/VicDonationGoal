import csv
import io
import json
import mimetypes
import secrets
import time
import threading
import uuid
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

try:
    import requests
    import websocket
except ImportError:
    requests = None
    websocket = None


ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent
PUBLIC = ROOT / "public"

DATA_DIR = ROOT / "data"
DA_DIR = ROOT / "integrations" / "donationalerts"
RUNTIME_DIR = PROJECT_ROOT / "runtime"

STATE_FILE = DATA_DIR / "state.json"
DONATIONS_FILE = DATA_DIR / "donations.json"
RATES_FILE = DATA_DIR / "rates.json"

DA_CONFIG_FILE = DA_DIR / "da_config.json"
DA_TOKENS_FILE = DA_DIR / "da_tokens.json"
DA_OAUTH_STATE_FILE = DA_DIR / "da_oauth_state.txt"

DONATTY_STATUS_FILE = RUNTIME_DIR / "donatty_status.json"
STREAMERBOT_STATUS_FILE = RUNTIME_DIR / "streamerbot_status.json"
STREAMERBOT_SENT_FILE = PROJECT_ROOT / "integrations" / "streamerbot" / "streamerbot_sent.json"

HOST = "127.0.0.1"
PORT = 3333

DA_AUTH_URL = "https://www.donationalerts.com/oauth/authorize"
DA_TOKEN_URL = "https://www.donationalerts.com/oauth/token"
DA_API_BASE = "https://www.donationalerts.com/api/v1"
DA_WS_URL = "wss://centrifugo.donationalerts.com/connection/websocket"

FILE_LOCK = threading.RLock()

DA_STATUS = {
    "configured": False,
    "authorized": False,
    "connected": False,
    "running": False,
    "channel": None,
    "last_error": None,
    "last_event": None,
}

DA_THREAD = None
DA_STOP = threading.Event()


DEFAULT_RATES = {
    "baseCurrency": "RUB",
    "ratesToRUB": {
        "RUB": 1,
        "USD": 90,
        "EUR": 100,
        "KZT": 0.18
    }
}


def ensure_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    if not STATE_FILE.exists():
        STATE_FILE.write_text(json.dumps({
            "title": "Сбор на цель",
            "current": 0,
            "baseAmount": 0,
            "goal": 10000,
            "currency": "RUB",
            "lastDonation": None
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    if not DONATIONS_FILE.exists():
        DONATIONS_FILE.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")

    if not RATES_FILE.exists():
        RATES_FILE.write_text(json.dumps(DEFAULT_RATES, ensure_ascii=False, indent=2), encoding="utf-8")

    if not DA_CONFIG_FILE.exists():
        DA_CONFIG_FILE.write_text(json.dumps({
            "enabled": True,
            "client_id": "ВСТАВЬ_CLIENT_ID_СЮДА",
            "client_secret": "ВСТАВЬ_CLIENT_SECRET_СЮДА",
            "redirect_uri": "http://127.0.0.1:3333/auth/donationalerts/callback",
            "scopes": "oauth-user-show oauth-donation-subscribe oauth-donation-index"
        }, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
        "message": str(donation.get("message") or ""),
        "createdAt": created_at,
        "receivedAt": received_at,
        "note": str(donation.get("note") or "")
    }


def normalize_storage():
    with FILE_LOCK:
        state = normalize_state(load_json(STATE_FILE, {}))
        donations = load_json(DONATIONS_FILE, [])
        if not isinstance(donations, list):
            donations = []

        normalized = []
        seen = set()
        for donation in donations:
            if not isinstance(donation, dict):
                continue
            item = normalize_donation_record(donation, state)
            if item["uniqueKey"] in seen:
                continue
            seen.add(item["uniqueKey"])
            normalized.append(item)

        recalc_goal_current(state, normalized)
        save_json(DONATIONS_FILE, normalized)
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
        recalc_goal_current(state, donations)

        save_json(DONATIONS_FILE, donations)
        save_json(STATE_FILE, state)

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
            if "amount" in update_data:
                old["amount"] = to_number(update_data.get("amount"), old.get("amount", 0))
            if "currency" in update_data:
                old["currency"] = normalize_currency(update_data.get("currency"))

            old["amountForGoal"] = round(convert_to_goal_currency(
                to_number(old.get("amount"), 0),
                old.get("currency", "RUB"),
                state.get("currency", "RUB")
            ), 2)

            donations[index] = old
            changed = old
            break

        if changed is None:
            return state, False, "Донат не найден"

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


def load_da_config():
    config = load_json(DA_CONFIG_FILE, {})
    client_id = str(config.get("client_id", "")).strip()
    client_secret = str(config.get("client_secret", "")).strip()

    configured = (
        bool(config.get("enabled", True)) and
        client_id and
        client_secret and
        "ВСТАВЬ" not in client_id and
        "ВСТАВЬ" not in client_secret
    )

    DA_STATUS["configured"] = configured
    return config


def load_da_tokens():
    tokens = load_json(DA_TOKENS_FILE, {})
    DA_STATUS["authorized"] = bool(tokens.get("access_token"))
    return tokens


def save_da_tokens(tokens):
    if "expires_in" in tokens:
        tokens["expires_at"] = time.time() + int(tokens.get("expires_in", 0)) - 120
    save_json(DA_TOKENS_FILE, tokens)
    DA_STATUS["authorized"] = bool(tokens.get("access_token"))


def clear_da_tokens():
    try:
        DA_TOKENS_FILE.unlink()
    except FileNotFoundError:
        pass
    DA_STATUS["authorized"] = False


def da_libraries_ok():
    return requests is not None and websocket is not None


def get_valid_da_access_token():
    config = load_da_config()
    tokens = load_da_tokens()

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_at = float(tokens.get("expires_at") or 0)

    if not access_token:
        return None

    if time.time() < expires_at:
        return access_token

    if not refresh_token:
        DA_STATUS["last_error"] = "Access token истёк, refresh_token отсутствует. Нужно заново авторизоваться."
        return None

    if requests is None:
        DA_STATUS["last_error"] = "Не установлена библиотека requests. Запусти 00_INSTALL_ALL.bat."
        return None

    try:
        response = requests.post(
            DA_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": config.get("client_id"),
                "client_secret": config.get("client_secret")
            },
            timeout=20
        )
        response.raise_for_status()
        new_tokens = response.json()

        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = refresh_token

        save_da_tokens(new_tokens)
        return new_tokens.get("access_token")
    except Exception as e:
        DA_STATUS["last_error"] = f"Не удалось обновить токен DA: {type(e).__name__}: {e}"
        return None


def da_api_request(method, endpoint, json_data=None):
    if requests is None:
        raise RuntimeError("Не установлена библиотека requests. Запусти 00_INSTALL_ALL.bat.")

    token = get_valid_da_access_token()
    if not token:
        raise RuntimeError("Нет access_token. Открой /auth/donationalerts/start и авторизуйся.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    url = DA_API_BASE + endpoint

    response = requests.request(
        method,
        url,
        headers=headers,
        json=json_data,
        timeout=20
    )

    if response.status_code == 401:
        clear_da_tokens()
        raise RuntimeError("DonationAlerts вернул 401. Нужно заново авторизоваться.")

    response.raise_for_status()

    if not response.text:
        return {}

    return response.json()


def exchange_code_for_token(code):
    config = load_da_config()

    response = requests.post(
        DA_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
            "redirect_uri": config.get("redirect_uri"),
            "code": code
        },
        timeout=20
    )

    response.raise_for_status()
    tokens = response.json()
    save_da_tokens(tokens)
    return tokens


def html_page(title, body):
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #111827;
      color: #f9fafb;
      font-family: Arial, sans-serif;
    }}
    .card {{
      width: min(720px, calc(100% - 32px));
      padding: 28px;
      border-radius: 18px;
      background: #1f2937;
      line-height: 1.55;
    }}
    a {{ color: #67e8f9; }}
    code {{
      background: #111827;
      padding: 2px 6px;
      border-radius: 6px;
    }}
  </style>
</head>
<body>
  <div class="card">
    {body}
  </div>
</body>
</html>"""


def extract_da_donation(message):
    try:
        data = json.loads(message)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    if data == {}:
        return None

    result = data.get("result", {})
    if not isinstance(result, dict):
        return None

    channel = result.get("channel", "")
    if not str(channel).startswith("$alerts:donation_"):
        return None

    outer_data = result.get("data", {})
    if not isinstance(outer_data, dict):
        return None

    donation_data = outer_data.get("data")
    if not isinstance(donation_data, dict):
        return None

    donation_id = donation_data.get("id")
    if donation_id is None:
        return None

    return {
        "source": "donationalerts",
        "externalId": donation_id,
        "username": donation_data.get("username") or donation_data.get("name") or "Аноним",
        "amount": donation_data.get("amount"),
        "currency": donation_data.get("currency") or "RUB",
        "message": donation_data.get("message") or "",
        "createdAt": donation_data.get("created_at") or ""
    }


def da_listener_loop():
    global DA_STATUS

    if not da_libraries_ok():
        DA_STATUS["last_error"] = "Не установлены requests/websocket-client. Запусти 00_INSTALL_ALL.bat."
        return

    reconnect_delay = 5
    DA_STATUS["running"] = True

    while not DA_STOP.is_set():
        ws = None

        try:
            load_da_config()

            if not DA_STATUS["configured"]:
                DA_STATUS["last_error"] = "da_config.json не настроен: вставь client_id и client_secret."
                time.sleep(reconnect_delay)
                continue

            if not load_da_tokens().get("access_token"):
                DA_STATUS["last_error"] = "DonationAlerts не авторизован. Открой http://127.0.0.1:3333/auth/donationalerts/start."
                time.sleep(reconnect_delay)
                continue

            user_response = da_api_request("GET", "/user/oauth")
            user_data = user_response.get("data", {})

            user_id = user_data.get("id")
            socket_token = user_data.get("socket_connection_token")

            if not user_id or not socket_token:
                raise RuntimeError("В /user/oauth нет id или socket_connection_token.")

            channel_name = f"$alerts:donation_{user_id}"
            DA_STATUS["channel"] = channel_name

            print(f"[DA] Подключаюсь к WebSocket: {DA_WS_URL}")
            ws = websocket.create_connection(DA_WS_URL, timeout=30)

            auth_payload = {
                "params": {
                    "token": socket_token
                },
                "id": 1
            }
            ws.send(json.dumps(auth_payload))

            auth_raw = ws.recv()
            auth_response = json.loads(auth_raw)
            client_id = auth_response.get("result", {}).get("client")

            if not client_id:
                raise RuntimeError(f"Не получил client id от Centrifugo: {auth_raw}")

            sub_response = da_api_request(
                "POST",
                "/centrifuge/subscribe",
                json_data={
                    "channels": [channel_name],
                    "client": client_id
                }
            )

            subscription_token = None
            for item in sub_response.get("channels", []):
                if item.get("channel") == channel_name:
                    subscription_token = item.get("token")
                    break

            if not subscription_token:
                raise RuntimeError(f"Не получил subscription token: {sub_response}")

            subscribe_payload = {
                "params": {
                    "channel": channel_name,
                    "token": subscription_token
                },
                "method": 1,
                "id": 2
            }
            ws.send(json.dumps(subscribe_payload))

            confirm_raw = ws.recv()
            print(f"[DA] Ответ подписки: {confirm_raw}")

            DA_STATUS["connected"] = True
            DA_STATUS["last_error"] = None
            reconnect_delay = 5

            print(f"[DA] Готово. Слушаю канал {channel_name}")

            while not DA_STOP.is_set():
                raw = ws.recv()

                if raw.strip() == "{}":
                    ws.send("{}")
                    continue

                donation = extract_da_donation(raw)
                if not donation:
                    continue

                state, ok, message = add_donation(donation)

                DA_STATUS["last_event"] = {
                    "ok": ok,
                    "message": message,
                    "donation": donation,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S")
                }

                print(f"[DA] Донат: {donation['username']} — {donation['amount']} {donation['currency']} | {message}")

        except Exception as e:
            DA_STATUS["connected"] = False
            DA_STATUS["last_error"] = f"{type(e).__name__}: {e}"
            print(f"[DA] Ошибка: {DA_STATUS['last_error']}")

            try:
                if ws:
                    ws.close()
            except Exception:
                pass

            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)

    DA_STATUS["running"] = False
    DA_STATUS["connected"] = False


def start_da_listener():
    global DA_THREAD

    if DA_THREAD and DA_THREAD.is_alive():
        return

    DA_STOP.clear()
    DA_THREAD = threading.Thread(target=da_listener_loop, daemon=True)
    DA_THREAD.start()


def stop_da_listener():
    DA_STOP.set()


def read_json_file_status(path, stale_after=20):
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}

    updated_at = to_number(data.get("updatedAt"), 0)
    age = max(0, time.time() - updated_at) if updated_at else None
    data["stale"] = bool(age is None or age > stale_after)
    data["ageSeconds"] = round(age, 1) if age is not None else None
    return data


def build_system_status():
    load_da_config()
    load_da_tokens()

    return {
        "server": {
            "running": True,
            "updatedAt": time.time(),
            "time": now_iso()
        },
        "donationAlerts": DA_STATUS,
        "donatty": read_json_file_status(DONATTY_STATUS_FILE, stale_after=120),
        "streamerbot": read_json_file_status(STREAMERBOT_STATUS_FILE, stale_after=15)
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


def donations_to_csv_bytes(donations):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
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
        "message",
        "note",
        "uniqueKey",
        "externalId"
    ])

    for donation in donations:
        writer.writerow([
            donation.get("receivedAt", ""),
            donation.get("createdAt", ""),
            donation.get("source", ""),
            donation.get("username", ""),
            donation.get("amount", ""),
            donation.get("currency", ""),
            donation.get("amountForGoal", ""),
            donation.get("includeInGoal", ""),
            donation.get("notifyStreamerBot", ""),
            donation.get("message", ""),
            donation.get("note", ""),
            donation.get("uniqueKey", ""),
            donation.get("externalId", "")
        ])

    return ("\ufeff" + output.getvalue()).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html, code=200):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, content_type="application/octet-stream", code=200, extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def read_body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}

        raw = self.rfile.read(length).decode("utf-8")

        try:
            return json.loads(raw)
        except Exception:
            parsed = parse_qs(raw)
            return {key: values[0] if values else "" for key, values in parsed.items()}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.redirect("/widget.html")
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

        if path == "/api/rates":
            self.send_json(load_rates())
            return

        if path == "/api/status":
            self.send_json(build_system_status())
            return

        if path == "/api/da/status":
            load_da_config()
            load_da_tokens()
            self.send_json(DA_STATUS)
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
                "notifyStreamerBot": qs.get("notifyStreamerBot", ["false"])[0]
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

        self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        data = self.read_body_json()

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
            rates = save_rates(data)
            with FILE_LOCK:
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

        if path == "/api/da/start":
            start_da_listener()
            self.send_json({"ok": True, "message": "DA listener запущен", "status": DA_STATUS})
            return

        if path == "/api/da/stop":
            stop_da_listener()
            self.send_json({"ok": True, "message": "DA listener остановлен", "status": DA_STATUS})
            return

        self.send_json({"ok": False, "message": "Неизвестный адрес"}, 404)

    def da_auth_start(self):
        if not da_libraries_ok():
            self.send_html(html_page(
                "Нужно установить библиотеки",
                """
                <h1>Не установлены библиотеки</h1>
                <p>Закрой сервер, запусти <code>install.bat</code>, потом снова запусти <code>start.bat</code>.</p>
                """
            ), 500)
            return

        config = load_da_config()

        if not DA_STATUS["configured"]:
            self.send_html(html_page(
                "DonationAlerts не настроен",
                """
                <h1>DonationAlerts не настроен</h1>
                <p>Открой файл <code>da_config.json</code> и вставь туда <code>client_id</code> и <code>client_secret</code>.</p>
                <p>Redirect URL в приложении DonationAlerts должен быть точно таким:</p>
                <p><code>http://127.0.0.1:3333/auth/donationalerts/callback</code></p>
                """
            ), 400)
            return

        oauth_state = secrets.token_urlsafe(24)
        DA_OAUTH_STATE_FILE.write_text(oauth_state, encoding="utf-8")

        params = {
            "client_id": config.get("client_id"),
            "redirect_uri": config.get("redirect_uri"),
            "response_type": "code",
            "scope": config.get("scopes", "oauth-user-show oauth-donation-subscribe oauth-donation-index"),
            "state": oauth_state
        }

        self.redirect(DA_AUTH_URL + "?" + urlencode(params))

    def da_auth_callback(self, parsed):
        if requests is None:
            self.send_html(html_page(
                "Ошибка",
                "<h1>Не установлена библиотека requests</h1><p>Запусти <code>install.bat</code>.</p>"
            ), 500)
            return

        qs = parse_qs(parsed.query)
        error = qs.get("error", [None])[0]
        code = qs.get("code", [None])[0]
        state = qs.get("state", [None])[0]

        if error:
            self.send_html(html_page(
                "Ошибка DonationAlerts",
                f"<h1>DonationAlerts вернул ошибку</h1><p><code>{error}</code></p>"
            ), 400)
            return

        expected_state = ""
        try:
            expected_state = DA_OAUTH_STATE_FILE.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            pass

        if not code:
            self.send_html(html_page(
                "Ошибка",
                "<h1>Нет code в callback</h1><p>Авторизация не завершилась.</p>"
            ), 400)
            return

        if not expected_state or state != expected_state:
            self.send_html(html_page(
                "Ошибка state",
                "<h1>Не совпал OAuth state</h1><p>Открой <code>/auth/donationalerts/start</code> ещё раз.</p>"
            ), 400)
            return

        try:
            exchange_code_for_token(code)
            start_da_listener()

            self.send_html(html_page(
                "DonationAlerts подключен",
                """
                <h1>DonationAlerts подключен</h1>
                <p>Токены сохранены в <code>da_tokens.json</code>.</p>
                <p>Сервер уже пытается подключиться к real-time каналу донатов.</p>
                <p>Статус можно проверить тут: <a href="/api/da/status">/api/da/status</a></p>
                <p>Админка: <a href="/admin.html">/admin.html</a></p>
                <p>Виджет: <a href="/widget.html">/widget.html</a></p>
                """
            ))
        except Exception as e:
            self.send_html(html_page(
                "Ошибка токена",
                f"""
                <h1>Не удалось получить токен</h1>
                <p><code>{type(e).__name__}: {e}</code></p>
                <p>Проверь <code>client_id</code>, <code>client_secret</code> и Redirect URL.</p>
                """
            ), 500)

    def redirect(self, target):
        self.send_response(302)
        self.send_header("Location", target)
        self.end_headers()

    def serve_static(self, path):
        safe_path = path.lstrip("/")

        file_path = PUBLIC / safe_path
        if not file_path.exists() or not file_path.is_file():
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
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ensure_files()
    normalize_storage()
    load_da_config()
    load_da_tokens()

    print("")
    print("==============================================")
    print(" Donation Goal Widget запущен")
    print("==============================================")
    print(f" Виджет для OBS:        http://{HOST}:{PORT}/widget.html")
    print(f" Админка:               http://{HOST}:{PORT}/admin.html")
    print(f" DonationAlerts login:  http://{HOST}:{PORT}/auth/donationalerts/start")
    print(f" DonationAlerts status: http://{HOST}:{PORT}/api/da/status")
    print("")
    print(" Чтобы остановить сервер: закрой это окно или нажми Ctrl+C")
    print("")

    if da_libraries_ok() and DA_STATUS["configured"] and DA_STATUS["authorized"]:
        start_da_listener()
    elif not da_libraries_ok():
        print("[DA] Библиотеки не установлены. Запусти 00_INSTALL_ALL.bat.")
    elif not DA_STATUS["configured"]:
        print("[DA] da_config.json ещё не настроен.")
    elif not DA_STATUS["authorized"]:
        print("[DA] Нужно авторизоваться: /auth/donationalerts/start")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
