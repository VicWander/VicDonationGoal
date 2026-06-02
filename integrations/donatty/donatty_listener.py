import json
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent.parent
RUNTIME_DIR = PROJECT_ROOT / "runtime"
CONFIG_FILE = ROOT / "donatty_config.json"
STATUS_FILE = RUNTIME_DIR / "donatty_status.json"

DEFAULT_CONFIG = {
    "enabled": True,

    "widget_url": "ВСТАВЬ_ОБЫЧНУЮ_ССЫЛКУ_DONATTY_ДЛЯ_OBS_СЮДА",

    "sse_url": "",

    "widget_api_url": "http://127.0.0.1:3333/api/donation",

    "headless_browser": True,
    "sse_capture_timeout_seconds": 35,

    "prefer_auto_sse": True,
    "use_old_sse_if_auto_failed": True,

    "reconnect_delay_seconds": 5,
    "max_reconnect_delay_seconds": 60
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


def write_status(status="starting", running=True, connected=False, last_error=None, last_event=None):
    payload = {
        "service": "donatty",
        "status": status,
        "running": running,
        "connected": connected,
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
    return merged


def is_placeholder(value):
    text = str(value or "")
    return not text or "ВСТАВЬ" in text or "DONATTY" in text and "http" not in text


def is_sse_url(url):
    if not url:
        return False

    text = str(url)

    return (
        "donatty.com" in text
        and "/sse" in text
        and "jwt=" in text
    )


def get_origin(url):
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "https://widgets.donatty.com"
    return f"{parsed.scheme}://{parsed.netloc}"


def capture_sse_url_with_browser(config):
    if sync_playwright is None:
        raise RuntimeError("Playwright не установлен. Запусти 00_INSTALL_ALL.bat")

    widget_url = str(config.get("widget_url") or "").strip()

    if is_placeholder(widget_url):
        raise RuntimeError("В donatty_config.json не указана обычная ссылка widget_url")

    timeout_seconds = float(config.get("sse_capture_timeout_seconds") or 35)
    headless = bool(config.get("headless_browser", True))

    captured = {"url": None}

    write_status("capturing_sse", running=True, connected=False)
    print("[DONATTY] Открываю Donatty-виджет в скрытом браузере, чтобы получить свежий SSE URL...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 800, "height": 600},
            ignore_https_errors=True
        )
        page = context.new_page()

        def remember_url(url):
            if is_sse_url(url) and not captured["url"]:
                captured["url"] = url
                write_status("sse_captured", running=True, connected=False)
                print("[DONATTY] Свежий SSE URL пойман из Network.")

        page.on("request", lambda request: remember_url(request.url))
        page.on("response", lambda response: remember_url(response.url))

        try:
            page.goto(widget_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[DONATTY] Виджет открылся не идеально, но продолжаю искать SSE: {type(e).__name__}: {e}")

        start = time.time()

        while time.time() - start < timeout_seconds:
            if captured["url"]:
                break

            try:
                resource_url = page.evaluate("""
                    () => {
                      const entries = performance.getEntriesByType('resource') || [];
                      const item = entries.find(e => String(e.name).includes('/sse') && String(e.name).includes('jwt='));
                      return item ? item.name : null;
                    }
                """)
                remember_url(resource_url)
            except Exception:
                pass

            time.sleep(0.2)

        browser.close()

    if not captured["url"]:
        raise RuntimeError("Не удалось поймать sse?jwt=... из Network Donatty")

    return captured["url"]


def resolve_sse_url(config):
    prefer_auto = bool(config.get("prefer_auto_sse", True))
    use_old_if_failed = bool(config.get("use_old_sse_if_auto_failed", True))

    old_sse_url = str(config.get("sse_url") or "").strip()
    old_sse_available = is_sse_url(old_sse_url)

    if prefer_auto:
        try:
            return capture_sse_url_with_browser(config)
        except Exception as e:
            print(f"[DONATTY] Автополучение SSE URL не удалось: {type(e).__name__}: {e}")

            if use_old_if_failed and old_sse_available:
                print("[DONATTY] Использую старый sse_url из donatty_config.json как fallback.")
                return old_sse_url

            raise

    if old_sse_available:
        return old_sse_url

    return capture_sse_url_with_browser(config)


def extract_donatty_donation(payload_text):
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

    amount = (
        event_data.get("amount")
        if event_data.get("amount") is not None
        else data.get("amount")
    )

    currency = (
        event_data.get("currency")
        or data.get("currency")
        or "RUB"
    )

    message = (
        event_data.get("message")
        or data.get("message")
        or ""
    )

    created_at = (
        event_data.get("date")
        or data.get("date")
        or ""
    )

    return {
        "source": "donatty",
        "externalId": external_id,
        "username": username,
        "amount": amount,
        "currency": currency,
        "message": message,
        "createdAt": created_at,
        "includeInGoal": True,
        "notifyStreamerBot": True
    }


def send_donation_to_widget(donation, config):
    if requests is None:
        print("[DONATTY] requests не установлен. Запусти 00_INSTALL_ALL.bat")
        return False

    url = str(config.get("widget_api_url") or "http://127.0.0.1:3333/api/donation").strip()

    try:
        response = requests.post(url, json=donation, timeout=8)

        if 200 <= response.status_code < 300:
            last_event = f"{donation['username']} — {donation['amount']} {donation['currency']}"
            write_status("connected", running=True, connected=True, last_event=last_event)
            print(f"[DONATTY] Донат: {donation['username']} — {donation['amount']} {donation['currency']} | отправлено в виджет")
            return True

        # Дубль — не критичная проблема: значит сервер уже видел этот refId.
        if response.status_code == 400 and "уже" in response.text.lower():
            print(f"[DONATTY] Донат уже был учтён: {donation.get('externalId')}")
            return True

        error_text = f"Виджет ответил HTTP {response.status_code}: {response.text[:300]}"
        write_status("error", running=True, connected=True, last_error=error_text)
        print(f"[DONATTY] {error_text}")
        return False

    except Exception as e:
        error_text = f"{type(e).__name__}: {e}"
        write_status("error", running=True, connected=True, last_error=error_text)
        print(f"[DONATTY] Не удалось отправить донат в виджет: {error_text}")
        return False


def process_sse_event(data_lines, config):
    if not data_lines:
        return

    payload_text = "\n".join(data_lines).strip()
    if not payload_text:
        return

    donation = extract_donatty_donation(payload_text)
    if not donation:
        return

    send_donation_to_widget(donation, config)


def listen_sse(sse_url, config):
    if requests is None:
        raise RuntimeError("requests не установлен. Запусти 00_INSTALL_ALL.bat")

    widget_url = str(config.get("widget_url") or "").strip()
    origin = get_origin(widget_url)

    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
        "User-Agent": "Mozilla/5.0 DonationGoalWidget/DonattyAutoListener",
        "Origin": origin,
        "Referer": widget_url if widget_url.startswith("http") else "https://widgets.donatty.com/"
    }

    write_status("connecting_sse", running=True, connected=False)
    print("[DONATTY] Подключаюсь к SSE...")
    print("[DONATTY] Если тут сразу ошибка 401/403 — токен протух, попробую получить новый.")

    with requests.get(
        sse_url,
        stream=True,
        headers=headers,
        timeout=(15, 90)
    ) as response:
        if response.status_code in (401, 403):
            raise PermissionError(f"Donatty SSE вернул {response.status_code}; нужен новый jwt")

        response.raise_for_status()

        write_status("connected", running=True, connected=True)
        print("[DONATTY] Подключено. Слушаю донаты Donatty.")

        data_lines = []
        last_heartbeat = 0

        for raw_line in response.iter_lines(decode_unicode=True):
            if time.time() - last_heartbeat > 10:
                write_status("connected", running=True, connected=True)
                last_heartbeat = time.time()

            if raw_line is None:
                continue

            line = raw_line.strip()

            if line == "":
                process_sse_event(data_lines, config)
                data_lines = []
                continue

            if line.startswith(":"):
                continue

            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
                continue

            # На случай, если Donatty отдаст JSON без стандартного префикса data:
            if line.startswith("{") and line.endswith("}"):
                process_sse_event([line], config)
                data_lines = []
                continue


def main():
    ensure_config()

    print("")
    print("================================================")
    print(" Donatty Auto Listener для Donation Goal Widget")
    print("================================================")
    print(" Этот listener сам открывает Donatty-виджет,")
    print(" ловит свежий sse?jwt=... из Network и слушает донаты.")
    print(" Остановить: Ctrl+C или закрыть окно")
    print("")

    reconnect_delay = 5
    write_status("starting", running=True, connected=False)

    while True:
        config = load_config()

        if not config.get("enabled", True):
            write_status("disabled", running=True, connected=False)
            print("[DONATTY] Listener выключен в donatty_config.json: enabled=false")
            time.sleep(3)
            continue

        try:
            sse_url = resolve_sse_url(config)
            reconnect_delay = float(config.get("reconnect_delay_seconds") or 5)

            listen_sse(sse_url, config)

        except KeyboardInterrupt:
            write_status("stopped", running=False, connected=False)
            print("\n[DONATTY] Остановлено пользователем.")
            break

        except Exception as e:
            error_text = f"{type(e).__name__}: {e}"
            write_status("error", running=True, connected=False, last_error=error_text)
            print(f"[DONATTY] Ошибка: {error_text}")
            print(f"[DONATTY] Повтор через {reconnect_delay:.0f} сек.")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, float(config.get("max_reconnect_delay_seconds") or 60))


if __name__ == "__main__":
    main()
