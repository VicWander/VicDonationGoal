import argparse
import json
import os
import shutil
import time
import hashlib
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent.parent
BROKEN_JSON_DIR = PROJECT_ROOT / "backups" / "broken_json"
_BROKEN_JSON_BACKED_UP = set()
RUNTIME_DIR = PROJECT_ROOT / "runtime"

CONFIG_FILE = ROOT / "streamerbot_config.json"
DONATIONS_FILE = PROJECT_ROOT / "core" / "data" / "donations.json"
SENT_FILE = ROOT / "streamerbot_sent.json"

# Rules for additional donation events, for example:
# 10 RUB -> poke hand action, 20 RUB -> pet hand action.
EVENT_RULES_FILE = ROOT / "donation_event_rules.json"
EVENT_RULES_SENT_FILE = ROOT / "streamerbot_event_rules_sent.json"

STATUS_FILE = RUNTIME_DIR / "streamerbot_status.json"
VERSION_FILE = PROJECT_ROOT / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "dev"

import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from safe_json import load_json as _robust_load_json, save_json as _robust_save_json
from source_registry import AUTOMATIC_SOURCE_IDS


DEFAULT_CONFIG = {
    "enabled": True,
    "streamerbot_http_url": "http://127.0.0.1:7474/DoAction",

    "action_name": "оповещение о донате",
    "action_id": "",

    "poll_interval_seconds": 0.5,

    "send_existing_on_first_start": False,
    "send_manual_donations": False,

    # Empty list means every automatic donation service. Manual donations still
    # obey their per-donation "Опов." checkbox.
    "send_sources": [],

    "currency_mode_for_currency_arg": "symbol",

    "currency_symbols": {
        "RUB": "₽",
        "USD": "$",
        "EUR": "€",
        "KZT": "₸",
        "UAH": "₴",
        "BYN": "Br"
    },

    "extra_args": {
        "integration": "VicWanderDonationGoal"
    }
}

KNOWN_SERVICE_SOURCES = set(AUTOMATIC_SOURCE_IDS)
LEGACY_SOURCE_WHITELIST = {"donationalerts", "donatty"}


DEFAULT_EVENT_RULES = {
    "enabled": True,
    "process_existing_on_first_start": False,
    "rules": []
}


def ensure_config():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, DEFAULT_CONFIG)
    if not EVENT_RULES_FILE.exists():
        save_json(EVENT_RULES_FILE, DEFAULT_EVENT_RULES)


def _backup_broken_json(path, error):
    try:
        path = Path(path)
        marker = str(path.resolve())
        if marker in _BROKEN_JSON_BACKED_UP or not path.exists() or path.stat().st_size == 0:
            return
        BROKEN_JSON_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BROKEN_JSON_DIR / f"{path.stem}_{stamp}{path.suffix}.broken.bak"
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


def write_status(status="running", running=True, last_error=None, last_event=None):
    payload = {
        "service": "streamerbot",
        "version": APP_VERSION,
        "status": status,
        "running": running,
        "updatedAt": time.time(),
        "lastError": last_error,
        "lastEvent": last_event
    }
    try:
        save_json(STATUS_FILE, payload)
    except Exception:
        pass


def load_config():
    ensure_config()
    config = load_json(CONFIG_FILE, {})
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)

    merged["currency_symbols"] = {
        **DEFAULT_CONFIG["currency_symbols"],
        **config.get("currency_symbols", {})
    }

    merged["extra_args"] = {
        **DEFAULT_CONFIG["extra_args"],
        **config.get("extra_args", {})
    }

    # v1.4.0-v1.4.2 shipped a hard-coded whitelist containing only DA and
    # Donatty. That silently discarded all new normalized services. Migrate only
    # that exact legacy value; custom user whitelists remain untouched.
    configured_sources = normalize_source_list(config.get("send_sources", []))
    if set(configured_sources) == LEGACY_SOURCE_WHITELIST:
        merged["send_sources"] = []
        config["send_sources"] = []
        try:
            save_json(CONFIG_FILE, config)
            print("[SB] Источник-миграция v1.4.3: новые сервисы разрешены автоматически.")
        except Exception:
            pass

    return merged


def load_event_rules():
    ensure_config()
    data = load_json(EVENT_RULES_FILE, DEFAULT_EVENT_RULES)

    # Backward/quick format support: file may contain just a list of rules.
    if isinstance(data, list):
        data = {"enabled": True, "rules": data}

    if not isinstance(data, dict):
        data = {}

    merged = dict(DEFAULT_EVENT_RULES)
    merged.update(data)

    rules = merged.get("rules", [])
    if not isinstance(rules, list):
        rules = []

    merged["rules"] = rules
    return merged


def load_donations():
    data = _robust_load_json(DONATIONS_FILE, [], retries=24, delay=0.035)
    return data if isinstance(data, list) else []


def load_sent():
    data = load_json(SENT_FILE, {"sent": []})

    if isinstance(data, list):
        return set(str(x) for x in data)

    return set(str(x) for x in data.get("sent", []))


def save_sent(sent):
    save_json(SENT_FILE, {
        "sent": sorted(sent)
    })


def load_event_rules_sent():
    data = load_json(EVENT_RULES_SENT_FILE, {"sent": []})

    if isinstance(data, list):
        return set(str(x) for x in data)

    return set(str(x) for x in data.get("sent", []))


def save_event_rules_sent(sent):
    save_json(EVENT_RULES_SENT_FILE, {
        "sent": sorted(sent)
    })


def to_float(value, default=None):
    try:
        if value is None:
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def normalize_source_list(value):
    if value in (None, "", "any", "*"):
        return []
    if isinstance(value, str):
        return [value.strip().lower()] if value.strip() else []
    if isinstance(value, list):
        return [str(x).strip().lower() for x in value if str(x).strip()]
    return []


def rule_id(rule):
    value = rule.get("id") or rule.get("rule_id") or rule.get("name") or rule.get("action_id") or rule.get("actionId")
    return str(value or "unnamed_rule").strip()


def event_rule_sent_key(donation, rule):
    return f"{donation_key(donation)}::rule::{rule_id(rule)}"


def action_object_from_rule(rule):
    action_id = str(rule.get("action_id") or rule.get("actionId") or "").strip()
    action_name = str(rule.get("action_name") or rule.get("actionName") or "").strip()

    if action_id:
        return {"id": action_id}

    return {"name": action_name}


def amount_value_for_rule(donation, rule):
    field = str(rule.get("amount_field") or rule.get("amountField") or "amount").strip()

    if field in ("amountForGoal", "amount_for_goal", "goal"):
        return to_float(donation.get("amountForGoal"), None)

    return to_float(donation.get("amount"), None)


def event_rule_matches(donation, rule):
    # Отдельная галочка управляет дополнительными донат-ивентами.
    # Обычное оповещение Streamer.bot по-прежнему использует notifyStreamerBot.
    if not bool_from_any(donation.get("triggerDonationEvents"), str(donation.get("source") or "") != "manual"):
        return False

    if not bool_from_any(rule.get("enabled"), True):
        return False

    source = str(donation.get("source") or "unknown").lower()
    allowed_sources = normalize_source_list(rule.get("sources", rule.get("source")))
    if allowed_sources and source not in allowed_sources:
        return False

    currency = str(donation.get("currency") or "RUB").upper()
    rule_currency = str(rule.get("currency") or "").strip().upper()
    if rule_currency and rule_currency not in ("ANY", "*") and currency != rule_currency:
        return False

    amount = amount_value_for_rule(donation, rule)
    if amount is None:
        return False

    match = str(rule.get("match") or rule.get("operator") or "equals").strip().lower()
    target = to_float(rule.get("amount"), None)
    epsilon = to_float(rule.get("epsilon"), 0.001) or 0.001

    if match in ("equals", "equal", "eq", "exact", "=="):
        return target is not None and abs(amount - target) <= epsilon

    if match in ("greater_or_equal", "gte", ">=", "min", "at_least"):
        return target is not None and amount >= target - epsilon

    if match in ("greater", "gt", ">"):
        return target is not None and amount > target

    if match in ("less_or_equal", "lte", "<=", "max", "at_most"):
        return target is not None and amount <= target + epsilon

    if match in ("less", "lt", "<"):
        return target is not None and amount < target

    if match in ("between", "range"):
        min_value = to_float(rule.get("min", rule.get("from")), None)
        max_value = to_float(rule.get("max", rule.get("to")), None)
        if min_value is not None and amount < min_value - epsilon:
            return False
        if max_value is not None and amount > max_value + epsilon:
            return False
        return True

    return False


def matching_event_rules(donation, event_rules_config):
    if not bool_from_any(event_rules_config.get("enabled"), True):
        return []

    result = []
    for rule in event_rules_config.get("rules", []):
        if isinstance(rule, dict) and event_rule_matches(donation, rule):
            result.append(rule)

    return result


def donation_key(donation):
    for field in ("uniqueKey", "accountingId", "id"):
        value = donation.get(field)
        if value not in (None, ""):
            return str(value)

    source = str(donation.get("source") or "unknown")
    external_id = donation.get("externalId") or donation.get("external_id")

    if external_id not in (None, ""):
        return f"{source}:{external_id}"

    raw = json.dumps(donation, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"hash:{digest}"


def format_amount(value):
    try:
        number = float(str(value).replace(",", "."))
    except Exception:
        return str(value)

    if number.is_integer():
        return str(int(number))

    return f"{number:.2f}".rstrip("0").rstrip(".")


def currency_arg(currency_code, config):
    code = str(currency_code or "RUB").upper()

    if config.get("currency_mode_for_currency_arg") == "code":
        return code

    return config.get("currency_symbols", {}).get(code, code)



def bool_from_any(value, default=False):
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


def should_send(donation, config):
    source = str(donation.get("source") or "unknown").strip().lower()

    # The per-donation checkbox is authoritative for every source. Automatic
    # service donations default to true in Core; manual entries default to false.
    default_notify = source != "manual"
    if not bool_from_any(donation.get("notifyStreamerBot"), default_notify):
        return False

    allowed_sources = normalize_source_list(config.get("send_sources", []))
    if allowed_sources and source not in allowed_sources:
        return False

    return True


def build_args(donation, config):
    username = (
        donation.get("username")
        or donation.get("user")
        or donation.get("name")
        or "Аноним"
    )

    amount = donation.get("amount")
    currency_code = str(donation.get("currency") or "RUB").upper()
    currency = currency_arg(currency_code, config)
    message = donation.get("message") or ""

    amount_text = format_amount(amount)

    args = {
        # Твои текущие переменные в Streamer.bot:
        "user": str(username),
        "amount": amount_text,
        "currency": currency,
        "message": str(message),

        # Дополнительные переменные на будущее:
        "username": str(username),
        "donationUser": str(username),
        "donor": str(username),

        "currencyCode": currency_code,
        "currencySymbol": currency_arg(currency_code, {**config, "currency_mode_for_currency_arg": "symbol"}),

        "amountRaw": amount,
        "amountText": amount_text,
        "amountWithCurrency": f"{amount_text}{currency}",
        "amountForGoalRaw": donation.get("amountForGoal"),
        "amountForGoal": format_amount(donation.get("amountForGoal")),

        "source": str(donation.get("source") or "unknown"),
        "donationId": donation_key(donation),
        "externalId": str(donation.get("externalId") or donation.get("external_id") or ""),
        "createdAt": str(donation.get("createdAt") or donation.get("created_at") or ""),
        "receivedAt": str(donation.get("receivedAt") or donation.get("received_at") or "")
    }

    args.update(config.get("extra_args", {}))
    return args


def streamerbot_action_object(config):
    action_id = str(config.get("action_id") or "").strip()
    action_name = str(config.get("action_name") or "").strip()

    if action_id:
        return {"id": action_id}

    return {"name": action_name}


def send_action_to_streamerbot(donation, config, action_object, label="main", extra_args=None):
    if requests is None:
        print("[SB] requests не установлен. Запусти 00_INSTALL_ALL.bat")
        return False

    url = str(config.get("streamerbot_http_url") or "").strip()
    if not url:
        print("[SB] В streamerbot_config.json не указан streamerbot_http_url")
        return False

    args = build_args(donation, config)
    if extra_args:
        args.update(extra_args)

    payload = {
        "action": action_object,
        "args": args
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=6
        )

        if 200 <= response.status_code < 300:
            last_event = f"{args['user']} — {args['amount']}{args['currency']}"
            write_status("sent", running=True, last_event=last_event)

            if label == "main":
                print(f"[SB] Отправлено в Streamer.bot: {args['user']} — {args['amount']}{args['currency']} | {args['message']}")
            else:
                print(f"[SB] Донат-ивент отправлен: {label} | {args['user']} — {args['amount']}{args['currency']}")

            return True

        error_text = f"HTTP {response.status_code}: {response.text[:300]}"
        write_status("error", running=True, last_error=error_text)
        print(f"[SB] Ошибка Streamer.bot {error_text}")
        return False

    except Exception as error:
        error_text = f"{type(error).__name__}: {error}"
        write_status("error", running=True, last_error=error_text)
        print(f"[SB] Не удалось отправить в Streamer.bot: {error_text}")
        return False


def send_to_streamerbot(donation, config):
    return send_action_to_streamerbot(
        donation,
        config,
        streamerbot_action_object(config),
        label="main"
    )


def send_event_rule_to_streamerbot(donation, config, rule):
    name = str(rule.get("name") or rule_id(rule))
    action_object = action_object_from_rule(rule)

    if not action_object.get("id") and not action_object.get("name"):
        print(f"[SB] Правило '{name}' пропущено: не указан action_id/action_name")
        return False

    extra_args = {
        "isDonationEvent": True,
        "donationEventRuleId": rule_id(rule),
        "donationEventRuleName": name,
        "donationEventMatch": str(rule.get("match") or rule.get("operator") or "equals"),
        "donationEventAmount": rule.get("amount", ""),
        "donationEventCurrency": str(rule.get("currency") or ""),
        "donationEventAmountField": str(rule.get("amount_field") or rule.get("amountField") or "amount")
    }

    return send_action_to_streamerbot(
        donation,
        config,
        action_object,
        label=name,
        extra_args=extra_args
    )


def mark_existing_if_needed(config):
    sent = load_sent()

    if SENT_FILE.exists():
        return sent

    if config.get("send_existing_on_first_start", False):
        save_sent(sent)
        return sent

    donations = load_donations()
    for donation in donations:
        sent.add(donation_key(donation))

    save_sent(sent)
    print(f"[SB] Первый запуск: старые донаты помечены как уже обработанные ({len(sent)} шт.)")
    return sent


def mark_existing_event_rules_if_needed(event_rules_config):
    sent = load_event_rules_sent()

    if EVENT_RULES_SENT_FILE.exists():
        return sent

    if event_rules_config.get("process_existing_on_first_start", False):
        save_event_rules_sent(sent)
        return sent

    donations = load_donations()
    marked = 0
    for donation in donations:
        for rule in matching_event_rules(donation, event_rules_config):
            sent.add(event_rule_sent_key(donation, rule))
            marked += 1

    save_event_rules_sent(sent)
    if marked:
        print(f"[SB] Первый запуск: старые донат-ивенты помечены как уже обработанные ({marked} шт.)")
    return sent


def run_loop():
    config = load_config()
    event_rules_config = load_event_rules()

    print("")
    print("================================================")
    print(f" Streamer.bot Bridge v{APP_VERSION} для VicDonationGoal")
    print("================================================")
    print(f" Action: {config.get('action_name')}")
    print(f" HTTP:   {config.get('streamerbot_http_url')}")
    print(f" Event rules: {'on' if event_rules_config.get('enabled', True) else 'off'} ({len(event_rules_config.get('rules', []))} rules)")
    print(" Остановить: Ctrl+C или закрыть окно")
    print("")

    if not config.get("enabled", True):
        write_status("disabled", running=False)
        print("[SB] Bridge выключен в streamerbot_config.json: enabled=false")
        return

    sent = mark_existing_if_needed(config)
    event_rules_sent = mark_existing_event_rules_if_needed(event_rules_config)
    write_status("running", running=True)

    try:
        while True:
            try:
                config = load_config()
                event_rules_config = load_event_rules()
                sent = load_sent()
                event_rules_sent = load_event_rules_sent()

                if not config.get("enabled", True):
                    write_status("disabled", running=True)
                    time.sleep(1)
                    continue

                write_status("running", running=True)
                donations = load_donations()

                should_break = False

                for donation in donations:
                    key = donation_key(donation)
                    main_failed = False

                    if key not in sent:
                        if should_send(donation, config):
                            ok = send_to_streamerbot(donation, config)

                            if ok:
                                sent.add(key)
                                save_sent(sent)
                            else:
                                # Не помечаем как отправленный, чтобы повторить позже.
                                # Но выходим из цикла, чтобы не спамить HTTP-запросами.
                                main_failed = True
                                should_break = True
                        else:
                            # Do not mark skipped donations as sent. The user may later
                            # enable the per-donation "Опов." checkbox or expand a
                            # source whitelist, and the bridge should then deliver it.
                            pass

                    if main_failed:
                        break

                    # Дополнительные донат-ивенты имеют отдельную защиту от дублей:
                    # donation_unique_key + rule_id.
                    for rule in matching_event_rules(donation, event_rules_config):
                        rule_key = event_rule_sent_key(donation, rule)

                        if rule_key in event_rules_sent:
                            continue

                        ok = send_event_rule_to_streamerbot(donation, config, rule)

                        if ok:
                            event_rules_sent.add(rule_key)
                            save_event_rules_sent(event_rules_sent)
                        else:
                            should_break = True
                            break

                    if should_break:
                        break

            except Exception as error:
                error_text = f"{type(error).__name__}: {error}"
                write_status("error", running=True, last_error=error_text)
                print(f"[SB] Ошибка рабочего цикла: {error_text}")
                time.sleep(2)

            time.sleep(max(0.2, float(config.get("poll_interval_seconds") or 0.5)))
    except KeyboardInterrupt:
        write_status("stopped", running=False)
        print("\n[SB] Остановлено пользователем.")


def send_test():
    config = load_config()

    test_donation = {
        "source": "test",
        "externalId": f"test-{int(time.time())}",
        "username": "TestUser",
        "amount": 133,
        "currency": "RUB",
        "message": "Тестовое сообщение доната",
        "createdAt": "",
        "receivedAt": ""
    }

    ok = send_to_streamerbot(test_donation, config)
    if ok:
        print("[SB] Тестовый action отправлен.")
    else:
        print("[SB] Тест не прошёл.")


def reset_sent():
    if SENT_FILE.exists():
        SENT_FILE.unlink()
        print("[SB] streamerbot_sent.json удалён.")
    else:
        print("[SB] streamerbot_sent.json и так отсутствует.")


def main():
    ensure_config()

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Отправить тестовый донат в Streamer.bot")
    parser.add_argument("--reset-sent", action="store_true", help="Сбросить список уже отправленных донатов")
    args = parser.parse_args()

    if args.reset_sent:
        reset_sent()
        return

    if args.test:
        send_test()
        return

    run_loop()


if __name__ == "__main__":
    main()
