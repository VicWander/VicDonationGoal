import argparse
import json
import time
import hashlib
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent.parent
RUNTIME_DIR = PROJECT_ROOT / "runtime"

CONFIG_FILE = ROOT / "streamerbot_config.json"
DONATIONS_FILE = PROJECT_ROOT / "core" / "data" / "donations.json"
SENT_FILE = ROOT / "streamerbot_sent.json"
STATUS_FILE = RUNTIME_DIR / "streamerbot_status.json"


DEFAULT_CONFIG = {
    "enabled": True,
    "streamerbot_http_url": "http://127.0.0.1:7474/DoAction",

    "action_name": "оповещение о донате",
    "action_id": "",

    "poll_interval_seconds": 0.5,

    "send_existing_on_first_start": False,
    "send_manual_donations": False,

    "send_sources": [
        "donationalerts",
        "donatty"
    ],

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


def ensure_config():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, DEFAULT_CONFIG)


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_status(status="running", running=True, last_error=None, last_event=None):
    payload = {
        "service": "streamerbot",
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

    return merged


def load_donations():
    if not DONATIONS_FILE.exists():
        return []

    # Иногда server.py может прямо в этот момент перезаписывать JSON.
    # Поэтому делаем несколько попыток.
    for _ in range(5):
        try:
            data = json.loads(DONATIONS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            time.sleep(0.08)

    return []


def load_sent():
    data = load_json(SENT_FILE, {"sent": []})

    if isinstance(data, list):
        return set(str(x) for x in data)

    return set(str(x) for x in data.get("sent", []))


def save_sent(sent):
    save_json(SENT_FILE, {
        "sent": sorted(sent)
    })


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
    source = str(donation.get("source") or "unknown")

    # Для ручных донатов решает персональная галочка из админки:
    # notifyStreamerBot=true — отправить оповещение, false — просто сохранить в истории.
    # Старый глобальный параметр send_manual_donations оставлен как fallback для старых записей.
    if source == "manual":
        return bool_from_any(
            donation.get("notifyStreamerBot"),
            bool(config.get("send_manual_donations", False))
        )

    allowed_sources = config.get("send_sources", [])
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


def send_to_streamerbot(donation, config):
    if requests is None:
        print("[SB] requests не установлен. Запусти 00_INSTALL_ALL.bat")
        return False

    url = str(config.get("streamerbot_http_url") or "").strip()
    if not url:
        print("[SB] В streamerbot_config.json не указан streamerbot_http_url")
        return False

    payload = {
        "action": streamerbot_action_object(config),
        "args": build_args(donation, config)
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=6
        )

        if 200 <= response.status_code < 300:
            args = payload["args"]
            last_event = f"{args['user']} — {args['amount']}{args['currency']}"
            write_status("sent", running=True, last_event=last_event)
            print(f"[SB] Отправлено в Streamer.bot: {args['user']} — {args['amount']}{args['currency']} | {args['message']}")
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


def run_loop():
    config = load_config()

    print("")
    print("================================================")
    print(" Streamer.bot Bridge для Donation Goal Widget")
    print("================================================")
    print(f" Action: {config.get('action_name')}")
    print(f" HTTP:   {config.get('streamerbot_http_url')}")
    print(" Остановить: Ctrl+C или закрыть окно")
    print("")

    if not config.get("enabled", True):
        write_status("disabled", running=False)
        print("[SB] Bridge выключен в streamerbot_config.json: enabled=false")
        return

    sent = mark_existing_if_needed(config)
    write_status("running", running=True)

    while True:
        config = load_config()
        sent = load_sent()

        if not config.get("enabled", True):
            write_status("disabled", running=True)
            time.sleep(1)
            continue

        write_status("running", running=True)
        donations = load_donations()

        for donation in donations:
            key = donation_key(donation)

            if key in sent:
                continue

            if not should_send(donation, config):
                # Важный момент: ручные донаты с notifyStreamerBot=false НЕ помечаем как отправленные.
                # Тогда можно позже включить галочку "Опов." в истории, и bridge отправит уведомление.
                # Остальные отключённые источники помечаем, чтобы не проверять их бесконечно.
                if str(donation.get("source") or "unknown") != "manual":
                    sent.add(key)
                    save_sent(sent)
                continue

            ok = send_to_streamerbot(donation, config)

            if ok:
                sent.add(key)
                save_sent(sent)
            else:
                # Не помечаем как отправленный, чтобы повторить позже.
                # Но выходим из цикла, чтобы не спамить HTTP-запросами.
                break

        time.sleep(float(config.get("poll_interval_seconds") or 0.5))


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
