import json
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote, urlencode

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
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

from safe_json import load_json as _robust_load_json, save_json as _robust_save_json

BROKEN_JSON_DIR = PROJECT_ROOT / "backups" / "broken_json"
_BROKEN_JSON_BACKED_UP = set()
RUNTIME_DIR = PROJECT_ROOT / "runtime"
CONFIG_FILE = ROOT / "donatty_config.json"
STATUS_FILE = RUNTIME_DIR / "donatty_status.json"
VERSION_FILE = PROJECT_ROOT / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "dev"

DEFAULT_CONFIG = {
    "enabled": True,

    "widget_url": "ВСТАВЬ_ОБЫЧНУЮ_ССЫЛКУ_DONATTY_ДЛЯ_OBS_СЮДА",

    "sse_url": "",

    "widget_api_url": "http://127.0.0.1:3333/api/donation",

    "headless_browser": True,
    "use_system_proxy": False,
    "sse_capture_timeout_seconds": 35,

    "prefer_auto_sse": True,
    "use_old_sse_if_auto_failed": True,

    "reconnect_delay_seconds": 5,
    "max_reconnect_delay_seconds": 60,

    "widget_send_attempts": 3,
    "widget_send_retry_seconds": 1.0
}


def ensure_config():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, DEFAULT_CONFIG)


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
    return _robust_load_json(path, fallback, retries=16, backup_dir=BROKEN_JSON_DIR)


def save_json(path, data):
    _robust_save_json(path, data, retries=120)


def write_status(status="starting", running=True, connected=False, last_error=None, last_event=None):
    previous = load_json(STATUS_FILE, {})
    if not isinstance(previous, dict):
        previous = {}
    payload = {
        "service": "donatty",
        "version": APP_VERSION,
        "status": status,
        "running": running,
        "connected": connected,
        "updatedAt": time.time(),
        "lastError": last_error,
        "lastEvent": last_event if last_event is not None else previous.get("lastEvent")
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


def capture_sse_url_from_widget(config):
    """Use the same token exchange as Donatty's standard donations widget.

    The public widget Script.js obtains response.accessToken from /auth/tokens/,
    then opens /widgets/<ref>/sse. Its API shard is 1 + last_ref_byte % 29.
    Other link formats keep the browser discovery path.
    """
    widget_url = str(config.get("widget_url") or "").strip()
    parsed = urlparse(widget_url)
    if parsed.scheme != "https" or parsed.hostname != "widgets.donatty.com":
        return None
    if parsed.path.rstrip("/") != "/donations":
        return None
    query = parse_qs(parsed.query)
    ref = (query.get("ref") or [""])[0]
    widget_token = (query.get("token") or [""])[0]
    try:
        uuid.UUID(ref)
        shard = 1 + int(ref[-2:], 16) % 29
    except (ValueError, AttributeError):
        return None
    if not widget_token:
        return None
    if requests is None:
        raise RuntimeError("requests не установлен. Запусти 00_INSTALL_ALL.bat")

    api_url = f"https://api-{shard:03d}.donatty.com"
    write_status("authorizing", running=True, connected=False)
    print("[DONATTY] Получаю свежий SSE URL через API виджета, без браузера...")
    try:
        with requests.Session() as session:
            session.trust_env = bool(config.get("use_system_proxy", False))
            response = session.get(
                f"{api_url}/auth/tokens/{quote(widget_token, safe='')}",
                headers={"Accept": "application/json"},
                timeout=(10, 20),
            )
            status_code = response.status_code
            payload = response.json() if status_code == 200 else None
    except Exception as error:
        raise RuntimeError(f"Donatty: получение токена не выполнено ({type(error).__name__})") from None
    if status_code != 200:
        # Do not include the request URL: its path contains the secret.
        raise RuntimeError(f"Donatty: получение токена вернуло HTTP {status_code}")
    data = payload.get("response") if isinstance(payload, dict) else None
    token = data.get("accessToken") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("Donatty: API виджета не вернул accessToken")

    offset = datetime.now().astimezone().utcoffset()
    zone_offset = int(-offset.total_seconds() / 60) if offset is not None else 0
    sse_url = f"{api_url}/widgets/{quote(ref, safe='')}/sse?" + urlencode({
        "jwt": token,
        "zoneOffset": zone_offset,
    })
    write_status("sse_captured", running=True, connected=False)
    print("[DONATTY] Свежий SSE URL получен напрямую через API виджета.")
    return sse_url


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
        browser = p.chromium.launch(
            headless=headless,
            args=[] if config.get("use_system_proxy", False) else ["--no-proxy-server"],
        )
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

    if not prefer_auto and old_sse_available:
        return old_sse_url

    try:
        try:
            native_url = capture_sse_url_from_widget(config)
            if native_url:
                return native_url
        except Exception as error:
            print(f"[DONATTY] Прямое получение SSE URL не удалось: {error}")
            print("[DONATTY] Проверяю резервный способ через браузер.")
        return capture_sse_url_with_browser(config)
    except Exception as error:
        print(f"[DONATTY] Автополучение SSE URL не удалось: {type(error).__name__}: {error}")
        if use_old_if_failed and old_sse_available:
            print("[DONATTY] Использую старый sse_url из donatty_config.json как fallback.")
            return old_sse_url
        raise


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
    attempts = max(1, int(float(config.get("widget_send_attempts") or 3)))
    retry_delay = max(0.2, float(config.get("widget_send_retry_seconds") or 1.0))
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            # Local Core must never be sent through a browser/VPN HTTP proxy.
            with requests.Session() as session:
                session.trust_env = False
                response = session.post(url, json=donation, timeout=8)

            if 200 <= response.status_code < 300:
                last_event = f"{donation['username']} — {donation['amount']} {donation['currency']}"
                write_status("connected", running=True, connected=True, last_event=last_event)
                print(f"[DONATTY] Донат: {donation['username']} — {donation['amount']} {donation['currency']} | отправлено в виджет")
                return True

            # Дубль безопасен: уникальный refId уже был сохранён сервером.
            if response.status_code == 400 and "уже" in response.text.lower():
                print(f"[DONATTY] Донат уже был учтён: {donation.get('externalId')}")
                return True

            last_error = f"Виджет ответил HTTP {response.status_code}: {response.text[:300]}"
            # 4xx обычно не исправятся повтором, кроме временных 408/429.
            if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                break

        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"

        if attempt < attempts:
            print(f"[DONATTY] Не удалось отправить донат (попытка {attempt}/{attempts}): {last_error}")
            time.sleep(retry_delay * attempt)

    error_text = last_error or "Неизвестная ошибка отправки доната"
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
    print("[DONATTY] Ожидаю подтверждение потока и первые данные.")

    with requests.Session() as session:
        session.trust_env = bool(config.get("use_system_proxy", False))
        with session.get(
            sse_url,
            stream=True,
            headers=headers,
            timeout=(15, 90)
        ) as response:
            _read_sse_response(response, config)


def _read_sse_response(response, config):
    if response.status_code in (401, 403):
        raise PermissionError(f"Donatty SSE вернул {response.status_code}; доступ отклонён")

    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "text/event-stream":
        raise ConnectionError("Donatty ответил без потока text/event-stream")
    response.encoding = "utf-8"
    write_status("connecting_sse", running=True, connected=False)
    print("[DONATTY] HTTP-подключение открыто. Ожидаю данные SSE...")

    data_lines = []
    last_heartbeat = 0
    received_data = False

    # Default iter_lines buffers 512 bytes and can hold a short donation until
    # the next event (or lose it when the read timeout expires).
    for raw_line in response.iter_lines(chunk_size=1, decode_unicode=True):
        if raw_line is None:
            continue
        if not received_data and raw_line:
            received_data = True
            print("[DONATTY] Поток SSE передаёт данные. Слушаю события Donatty.")
        if received_data and time.time() - last_heartbeat > 10:
            write_status("connected", running=True, connected=True)
            last_heartbeat = time.time()

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

    raise ConnectionError("Donatty закрыл поток SSE; требуется переподключение")


def main():
    ensure_config()

    print("")
    print("================================================")
    print(f" Donatty Auto Listener v{APP_VERSION} для VicDonationGoal")
    print("================================================")
    print(" Получает поток Donatty через API OBS-виджета.")
    print(" Для старых ссылок использует резервный способ через браузер.")
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
