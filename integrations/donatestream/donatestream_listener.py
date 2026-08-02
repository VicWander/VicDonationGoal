from __future__ import annotations

import json
import queue
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.base.common import (
    StatusWriter,
    extract_donations,
    load_json,
    normalize_time,
    post_donation,
    redact_url,
    save_json,
    to_number,
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

SERVICE = "donatestream"
CONFIG_FILE = ROOT / "donatestream_config.json"
STATUS_FILE = PROJECT_ROOT / "runtime/integrations/donatestream_status.json"
SEEN_FILE = ROOT / "donatestream_seen.json"
STATUS = StatusWriter(
    STATUS_FILE,
    SERVICE,
    frames=0,
    socketIoEvents=0,
    reconnects=0,
    parser="socket.io-alert-v1",
)


def log(message: str, level: str = "INFO") -> None:
    print(f"[Donate.Stream] {level} {message}", flush=True)


def load_seen() -> set[str]:
    payload = load_json(SEEN_FILE, {"ids": []})
    return set(map(str, payload.get("ids") or []))


def save_seen(ids: set[str]) -> None:
    save_json(SEEN_FILE, {"ids": list(ids)[-5000:], "updatedAt": time.time()})


def parse_socketio_alert(raw: Any, default_currency: str = "RUB") -> dict[str, Any] | None:
    """Parse Donate.Stream Socket.IO frames.

    Live inspector data confirmed that alerts arrive as:
      42["alert", { ... donation payload ... }]
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    text = str(raw or "").strip()
    if not text.startswith("42"):
        return None

    try:
        packet = json.loads(text[2:])
    except Exception:
        return None

    if not isinstance(packet, list) or len(packet) < 2 or packet[0] != "alert":
        return None
    candidate = packet[1]
    if not isinstance(candidate, dict):
        return None

    external_id = candidate.get("message_uid") or candidate.get("id") or candidate.get("uid")
    amount = candidate.get("sum")
    if amount in (None, ""):
        amount = candidate.get("payment_sum")
    amount_number = to_number(amount, 0)
    if not external_id or amount_number <= 0:
        return None

    return {
        "source": "donatestream",
        "externalId": str(external_id),
        "username": str(candidate.get("nickname") or candidate.get("name") or "Аноним"),
        "amount": amount_number,
        "currency": str(candidate.get("currency") or default_currency).upper(),
        "message": str(candidate.get("message") or ""),
        "createdAt": normalize_time(
            candidate.get("created_at")
            or candidate.get("createdAt")
            or candidate.get("date")
            or candidate.get("timestamp")
        ),
        "note": "Donate.Stream Socket.IO alert",
    }


def donations_from_event(raw: Any, default_currency: str) -> list[dict[str, Any]]:
    direct = parse_socketio_alert(raw, default_currency)
    if direct:
        return [direct]
    return extract_donations(raw, "donatestream", default_currency, "Donate.Stream widget")


def main() -> None:
    if sync_playwright is None:
        raise SystemExit("Playwright не установлен. Запусти 00_INSTALL_ALL.bat")

    cfg = load_json(CONFIG_FILE, {})
    if not cfg.get("enabled"):
        raise SystemExit("Donate.Stream выключен")
    widget = str(cfg.get("widget_url") or "").strip()
    if not widget:
        raise SystemExit("Не указана ссылка виджета Donate.Stream")

    delay = max(2, int(cfg.get("reconnect_delay_seconds", 5)))
    seen = load_seen()

    while True:
        browser = None
        try:
            STATUS.update(running=True, connected=False, status="starting_browser", lastError=None)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=bool(cfg.get("headless_browser", True)))
                context = browser.new_context(
                    ignore_https_errors=True,
                    viewport={"width": 800, "height": 600},
                )
                page = context.new_page()
                events: queue.Queue[dict[str, Any]] = queue.Queue()

                def capture(payload):
                    events.put(payload)

                page.expose_function("vicCapture", capture)
                page.add_init_script(
                    r"""
                    (() => {
                      const send = (kind, data) => {
                        try { window.vicCapture({kind, data: String(data)}); } catch (_) {}
                      };
                      const OriginalWebSocket = window.WebSocket;
                      class VicWebSocket extends OriginalWebSocket {
                        constructor(...args) {
                          super(...args);
                          this.addEventListener('message', e => send('websocket', e.data));
                        }
                      }
                      Object.defineProperties(VicWebSocket, {
                        CONNECTING: {value: OriginalWebSocket.CONNECTING},
                        OPEN: {value: OriginalWebSocket.OPEN},
                        CLOSING: {value: OriginalWebSocket.CLOSING},
                        CLOSED: {value: OriginalWebSocket.CLOSED}
                      });
                      window.WebSocket = VicWebSocket;
                    })();
                    """
                )

                def attach_websocket(ws):
                    ws.on(
                        "framereceived",
                        lambda data: events.put({"kind": "pw-websocket", "data": data}),
                    )

                page.on("websocket", attach_websocket)
                if cfg.get("capture_console", True):
                    page.on(
                        "console",
                        lambda message: events.put({"kind": "console", "data": message.text}),
                    )

                try:
                    page.goto(widget, wait_until="domcontentloaded", timeout=60000)
                except Exception as error:
                    log(f"Страница открылась с предупреждением: {error}", "WARN")

                STATUS.update(
                    connected=True,
                    status="listening",
                    widget=redact_url(widget),
                    lastError=None,
                )
                log("Виджет открыт; ожидаю Socket.IO событие alert")

                while True:
                    try:
                        event = events.get(timeout=1)
                    except queue.Empty:
                        page.wait_for_timeout(50)
                        continue

                    raw = event.get("data")
                    STATUS.update(frames=int(STATUS.data.get("frames", 0)) + 1)
                    parsed = donations_from_event(raw, cfg.get("default_currency", "RUB"))
                    if parse_socketio_alert(raw, cfg.get("default_currency", "RUB")):
                        STATUS.update(
                            socketIoEvents=int(STATUS.data.get("socketIoEvents", 0)) + 1
                        )

                    for donation in parsed:
                        key = str(donation["externalId"])
                        if key in seen:
                            continue
                        try:
                            result = post_donation(
                                cfg.get("widget_api_url", "http://127.0.0.1:3333/api/donation"),
                                donation,
                                int(cfg.get("request_timeout_seconds", 12)),
                            )
                            seen.add(key)
                            save_seen(seen)
                            STATUS.update(lastEvent=key, lastError=None)
                            log(f"Донат {key} учтён: {result.get('message', 'OK')}")
                        except Exception as error:
                            STATUS.update(lastError=f"{type(error).__name__}: {error}")
                            log(str(error), "ERROR")

        except KeyboardInterrupt:
            break
        except Exception as error:
            STATUS.update(
                connected=False,
                status="restarting",
                lastError=f"{type(error).__name__}: {error}",
                reconnects=int(STATUS.data.get("reconnects", 0)) + 1,
            )
            log(f"{type(error).__name__}: {error}", "ERROR")
            time.sleep(delay)
            cfg = load_json(CONFIG_FILE, cfg)
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

    STATUS.update(running=False, connected=False, status="stopped")


if __name__ == "__main__":
    main()
