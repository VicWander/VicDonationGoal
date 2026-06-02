import json
import time
import uuid
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

CONFIG_FILE = Path(__file__).parent / "donatty_config.json"
WIDGET_API_URL = "http://127.0.0.1:3333/api/donation"

STATUS = {
    "configured": False,
    "connected": False,
    "last_error": None,
    "last_event": None,
}


def load_config():
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps({
            "enabled": False,
            "sse_url": "ВСТАВЬ_ПОЛНУЮ_SSE_ССЫЛКУ_ИЗ_NETWORK_СЮДА",
            "widget_api_url": WIDGET_API_URL
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        config = {}

    sse_url = str(config.get("sse_url", "")).strip()
    configured = (
        bool(config.get("enabled", False))
        and sse_url.startswith("http")
        and "ВСТАВЬ" not in sse_url
    )

    STATUS["configured"] = configured
    return config


def extract_donation(payload_text):
    """
    Donatty присылает примерно такое:

    {
      "action":"DATA",
      "data":{
        "streamEventType":"DONATTY_DONATION",
        "streamEventData":"{...}",
        "subscriber":"3223",
        "message":"12313",
        "amount":133,
        "currency":"RUB"
      }
    }
    """
    try:
        payload = json.loads(payload_text)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    action = payload.get("action")
    data = payload.get("data", {})

    if action != "DATA" or not isinstance(data, dict):
        return None

    event_type = data.get("streamEventType")
    if event_type != "DONATTY_DONATION":
        return None

    raw_event_data = data.get("streamEventData")
    event_data = {}

    if isinstance(raw_event_data, str):
        try:
            event_data = json.loads(raw_event_data)
        except Exception:
            event_data = {}
    elif isinstance(raw_event_data, dict):
        event_data = raw_event_data

    # В тестовом донате id часто равен 0, поэтому refId лучше.
    external_id = (
        event_data.get("refId")
        or event_data.get("id")
        or data.get("refId")
        or f"{event_data.get('date')}-{data.get('subscriber')}-{data.get('amount')}-{data.get('message')}"
        or str(uuid.uuid4())
    )

    username = (
        event_data.get("displayName")
        or data.get("subscriber")
        or event_data.get("username")
        or "Аноним"
    )

    amount = event_data.get("amount") if event_data.get("amount") is not None else data.get("amount")
    currency = event_data.get("currency") or data.get("currency") or "RUB"
    message = event_data.get("message") or data.get("message") or ""
    created_at = event_data.get("date") or data.get("date") or ""

    return {
        "source": "donatty",
        "externalId": str(external_id),
        "username": str(username),
        "amount": amount,
        "currency": str(currency),
        "message": str(message),
        "createdAt": str(created_at)
    }


def send_to_widget(donation, widget_api_url):
    response = requests.post(widget_api_url, json=donation, timeout=10)

    try:
        result = response.json()
    except Exception:
        result = {"raw": response.text}

    if response.status_code >= 400:
        raise RuntimeError(f"Widget API вернул {response.status_code}: {result}")

    return result


def process_event(data_lines, widget_api_url):
    if not data_lines:
        return

    payload_text = "\n".join(data_lines).strip()
    if not payload_text:
        return

    donation = extract_donation(payload_text)
    if not donation:
        return

    result = send_to_widget(donation, widget_api_url)

    STATUS["last_event"] = {
        "donation": donation,
        "result": result,
        "time": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    print(f"[DONATTY] Донат: {donation['username']} — {donation['amount']} {donation['currency']} | отправлено в виджет")


def listen_forever():
    if requests is None:
        print("[DONATTY] Не установлена библиотека requests. Запусти install_donatty.bat")
        return

    reconnect_delay = 5

    while True:
        try:
            config = load_config()

            if not STATUS["configured"]:
                print("[DONATTY] donatty_config.json не настроен.")
                print("[DONATTY] Нужно поставить enabled=true и вставить sse_url.")
                time.sleep(reconnect_delay)
                continue

            sse_url = str(config.get("sse_url", "")).strip()
            widget_api_url = str(config.get("widget_api_url") or WIDGET_API_URL).strip()

            print("[DONATTY] Подключаюсь к SSE...")
            print(f"[DONATTY] Виджет API: {widget_api_url}")

            STATUS["connected"] = False
            STATUS["last_error"] = None

            with requests.get(
                sse_url,
                stream=True,
                headers={
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "User-Agent": "Mozilla/5.0 DonationGoalWidgetDonattyListener/1.0"
                },
                timeout=(15, 90)
            ) as response:
                response.raise_for_status()

                STATUS["connected"] = True
                reconnect_delay = 5
                print("[DONATTY] Подключено. Слушаю донаты Donatty.")

                data_lines = []

                for raw_line in response.iter_lines(decode_unicode=True):
                    if raw_line is None:
                        continue

                    line = raw_line.strip()

                    if line == "":
                        process_event(data_lines, widget_api_url)
                        data_lines = []
                        continue

                    if line.startswith(":"):
                        continue

                    if line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                        continue

                    # На случай, если Donatty отдаёт JSON без стандартного data:
                    if line.startswith("{") and line.endswith("}"):
                        process_event([line], widget_api_url)
                        data_lines = []
                        continue

        except KeyboardInterrupt:
            print("\n[DONATTY] Остановлено пользователем.")
            break
        except Exception as e:
            STATUS["connected"] = False
            STATUS["last_error"] = f"{type(e).__name__}: {e}"
            print(f"[DONATTY] Ошибка: {STATUS['last_error']}")
            print(f"[DONATTY] Переподключение через {reconnect_delay} сек...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)


if __name__ == "__main__":
    print("")
    print("==============================================")
    print(" Donatty Listener для Donation Goal Widget")
    print("==============================================")
    print(" Основной сервер виджета должен быть запущен отдельно через start.bat")
    print(" Остановить это окно: Ctrl+C или закрыть окно")
    print("")
    listen_forever()
