from __future__ import annotations

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
    deep_get,
    extract_donations,
    load_json,
    post_donation,
    redact_url,
    save_json,
)

try:
    import requests
except ImportError:
    requests = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

CONFIG_FILE = ROOT / "donatex_config.json"
STATUS_FILE = PROJECT_ROOT / "runtime/integrations/donatex_status.json"
SEEN_FILE = ROOT / "donatex_seen.json"
OFFICIAL_API_URL = "https://donatex.gg/api/v1/donations"
STATUS = StatusWriter(
    STATUS_FILE,
    "donatex",
    mode=None,
    eventsSeen=0,
    endpoint=None,
    responseShape=None,
)


def log(message: str, level: str = "INFO") -> None:
    print(f"[DonateX] {level} {message}", flush=True)


def config() -> dict[str, Any]:
    return load_json(CONFIG_FILE, {})


def headers(cfg: dict[str, Any]) -> dict[str, str]:
    token = str(cfg.get("api_token") or "")
    mode = cfg.get("auth_mode", "query")
    if mode == "bearer":
        return {"Authorization": f"Bearer {token}"}
    if mode == "x-api-key":
        return {"X-API-Key": token}
    if mode == "api-key":
        return {"Api-Key": token}
    return {}


def list_items(payload: Any, path: str) -> list[Any]:
    value = deep_get(payload, path) if path else payload
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in (
            "data",
            "rows",
            "items",
            "donations",
            "transactions",
            "events",
            "result",
        ):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
            if isinstance(nested, dict):
                for sub_key in ("data", "items", "rows", "donations"):
                    sub_value = nested.get(sub_key)
                    if isinstance(sub_value, list):
                        return sub_value
    return []


def response_shape(payload: Any) -> str:
    if isinstance(payload, list):
        return f"list[{len(payload)}]"
    if isinstance(payload, dict):
        return "dict keys: " + ", ".join(map(str, list(payload.keys())[:20]))
    return type(payload).__name__


def poll(cfg: dict[str, Any]):
    if requests is None:
        raise RuntimeError("Не установлена requests")

    url = str(cfg.get("api_url") or "").strip() or OFFICIAL_API_URL
    params: dict[str, Any] = {
        "skip": max(0, int(cfg.get("skip", 0))),
        "take": max(1, min(int(cfg.get("take", 20)), 100)),
    }

    if cfg.get("auth_mode", "query") == "query":
        parameter_name = str(cfg.get("query_token_name") or "token").strip() or "token"
        params[parameter_name] = cfg["api_token"]

    response = requests.get(
        url,
        headers=headers(cfg),
        params=params,
        timeout=int(cfg.get("request_timeout_seconds", 15)),
    )
    response.raise_for_status()
    return response.json(), url


def load_seen() -> tuple[bool, set[str]]:
    payload = load_json(SEEN_FILE, {})
    return bool(payload.get("initialized")), set(map(str, payload.get("ids") or []))


def save_seen(initialized: bool, seen: set[str]) -> None:
    save_json(
        SEEN_FILE,
        {
            "initialized": initialized,
            "ids": list(seen)[-5000:],
            "updatedAt": time.time(),
        },
    )


def api_loop(cfg: dict[str, Any]) -> None:
    initialized, seen = load_seen()
    interval = max(10, int(cfg.get("poll_interval_seconds", 20)))
    endpoint = str(cfg.get("api_url") or "").strip() or OFFICIAL_API_URL
    consecutive_errors = 0
    last_success_at = None
    STATUS.update(
        running=True,
        connected=False,
        status="starting_poll",
        mode="api",
        endpoint=redact_url(endpoint),
        lastError=None,
        consecutiveErrors=0,
        lastSuccessAt=None,
    )

    while True:
        cfg = config()
        interval = max(10, int(cfg.get("poll_interval_seconds", 20)))
        try:
            payload, used_url = poll(cfg)
            last_success_at = time.time()
            consecutive_errors = 0
            STATUS.update(
                connected=True,
                status="polling",
                endpoint=redact_url(used_url),
                responseShape=response_shape(payload),
                lastError=None,
                lastWarning=None,
                consecutiveErrors=0,
                lastSuccessAt=last_success_at,
                nextPollAt=last_success_at + interval,
            )
            items = list_items(payload, str(cfg.get("items_path") or "").strip())
            donations: list[dict[str, Any]] = []
            for item in items:
                donations.extend(
                    extract_donations(item, "donatex", cfg.get("default_currency", "RUB"), "DonateX API")
                )

            if items and not donations:
                STATUS.update(unrecognizedItems=len(items))
                log(
                    "API вернул записи, но поля доната пока не распознаны. "
                    f"Форма ответа: {response_shape(payload)}",
                    "WARN",
                )
            else:
                STATUS.update(unrecognizedItems=0)

            if not initialized and not cfg.get("import_existing_first_run", False):
                seen.update(str(item["externalId"]) for item in donations)
                initialized = True
                save_seen(initialized, seen)
                log(f"Первый запуск: запомнено событий — {len(donations)}")
            else:
                for donation in reversed(donations):
                    key = str(donation["externalId"])
                    if key in seen:
                        continue
                    try:
                        result = post_donation(
                            cfg.get("widget_api_url", "http://127.0.0.1:3333/api/donation"),
                            donation,
                            int(cfg.get("request_timeout_seconds", 15)),
                        )
                    except Exception as error:
                        # API is still connected; Core delivery will be retried on the
                        # next poll because the event is not marked as seen.
                        STATUS.update(
                            connected=True,
                            status="polling_delivery_retry",
                            lastDeliveryError=f"{type(error).__name__}: {redact_url(str(error))}",
                        )
                        log(f"Core delivery {key}: {type(error).__name__}: {redact_url(str(error))}", "WARN")
                        continue
                    seen.add(key)
                    save_seen(True, seen)
                    STATUS.update(
                        lastEvent=key,
                        eventsSeen=int(STATUS.data.get("eventsSeen", 0)) + 1,
                        lastError=None,
                        lastDeliveryError=None,
                    )
                    log(f"Донат {key} учтён: {result.get('message', 'OK')}")

            time.sleep(interval)

        except KeyboardInterrupt:
            raise
        except Exception as error:
            consecutive_errors += 1
            error_text = f"{type(error).__name__}: {redact_url(str(error))}"
            # A polling service is not a persistent socket. Once at least one poll
            # succeeded, a temporary HTTP failure means degraded connection, not a
            # full disconnect/restart.
            if last_success_at:
                STATUS.update(
                    running=True,
                    connected=True,
                    status="polling_degraded",
                    lastError=None,
                    lastWarning=error_text,
                    consecutiveErrors=consecutive_errors,
                    lastSuccessAt=last_success_at,
                )
            else:
                STATUS.update(
                    running=True,
                    connected=False,
                    status="retrying",
                    lastError=error_text,
                    lastWarning=None,
                    consecutiveErrors=consecutive_errors,
                    lastSuccessAt=None,
                )
            log(error_text, "WARN")
            wait = min(60, max(interval, 10) * min(consecutive_errors, 3))
            STATUS.update(nextPollAt=time.time() + wait)
            time.sleep(wait)


def widget_loop(cfg: dict[str, Any]) -> None:
    if sync_playwright is None:
        raise RuntimeError("Playwright не установлен")
    url = str(cfg.get("widget_url") or "").strip()
    if not url:
        raise RuntimeError("Укажите widget_url DonateX")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=bool(cfg.get("headless_browser", True)))
        page = browser.new_page()
        event_queue: queue.Queue[Any] = queue.Queue()
        page.on("websocket", lambda ws: ws.on("framereceived", lambda data: event_queue.put(data)))
        page.on("console", lambda message: event_queue.put(message.text))
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        STATUS.update(
            running=True,
            connected=True,
            status="listening",
            mode="widget",
            endpoint=redact_url(url),
            lastError=None,
        )
        seen: set[str] = set()

        try:
            while True:
                try:
                    raw = event_queue.get(timeout=1)
                except queue.Empty:
                    page.wait_for_timeout(50)
                    continue
                for donation in extract_donations(
                    raw,
                    "donatex",
                    cfg.get("default_currency", "RUB"),
                    "DonateX widget",
                ):
                    key = str(donation["externalId"])
                    if key in seen:
                        continue
                    result = post_donation(
                        cfg.get("widget_api_url", "http://127.0.0.1:3333/api/donation"),
                        donation,
                        int(cfg.get("request_timeout_seconds", 15)),
                    )
                    seen.add(key)
                    STATUS.update(lastEvent=key, lastError=None)
                    log(f"Донат {key} учтён: {result.get('message', 'OK')}")
        finally:
            browser.close()


def main() -> None:
    cfg = config()
    if not cfg.get("enabled"):
        raise SystemExit("DonateX выключен")
    if not str(cfg.get("api_token") or "").strip():
        raise SystemExit("Не указан API-токен DonateX")

    while True:
        try:
            if cfg.get("mode", "api") == "widget":
                widget_loop(cfg)
            else:
                api_loop(cfg)
        except KeyboardInterrupt:
            break
        except Exception as error:
            STATUS.update(
                running=True,
                connected=False,
                status="retrying",
                lastError=f"{type(error).__name__}: {redact_url(str(error))}",
            )
            log(f"{type(error).__name__}: {redact_url(str(error))}", "ERROR")
            time.sleep(10)
            cfg = config()

    STATUS.update(running=False, connected=False, status="stopped")


if __name__ == "__main__":
    main()
