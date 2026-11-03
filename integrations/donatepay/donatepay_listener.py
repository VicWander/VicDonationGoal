from __future__ import annotations

import hashlib
import json
import socket
import sys
import time
from urllib.parse import urlsplit
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.base.common import (
    StatusWriter,
    deep_get,
    donation_from_candidate,
    extract_donations,
    load_json,
    post_donation,
    redact_url,
    save_json,
)

try:
    import requests
    import websocket
except ImportError:
    requests = None
    websocket = None

CONFIG_FILE = ROOT / "donatepay_config.json"
STATUS_FILE = PROJECT_ROOT / "runtime/integrations/donatepay_status.json"
SEEN_FILE = ROOT / "donatepay_seen.json"
CATCH_UP_STATE_FILE = ROOT / "donatepay_catch_up_state.json"
RUNTIME_STATE_FILE = ROOT / "donatepay_runtime_state.json"

STATUS = StatusWriter(
    STATUS_FILE,
    "donatepay",
    subscribed=False,
    channel=None,
    userId=None,
    reconnects=0,
    catchUpStatus="idle",
    catchUpRetryAt=None,
    catchUpLastSuccessAt=None,
    framesReceived=0,
    unrecognizedFrames=0,
)


def log(message: str, level: str = "INFO") -> None:
    print(f"[DonatePay] {level} {message}", flush=True)


def config() -> dict[str, Any]:
    cfg=load_json(CONFIG_FILE, {})
    if 'eu_region' in cfg:
        domain='donatepay.eu' if cfg['eu_region'] else 'donatepay.ru'
        cfg.update(api_v1_url='https://'+domain+'/api/v1',socket_token_url='https://'+domain+'/api/v2/socket/token',websocket_url='wss://centrifugo.'+domain+':443/connection/websocket')
    return cfg


def safe_error(error: BaseException | str) -> str:
    return redact_url(str(error))


def _request_timeout(cfg: dict[str, Any]) -> int:
    return max(5, int(cfg.get("request_timeout_seconds", 15)))


def http_request(method, url, **kwargs):
    with requests.Session() as session:
        session.trust_env=bool(config().get('use_system_proxy',False))
        return session.request(method,url,**kwargs)


def api_get(cfg: dict[str, Any], path: str, params: dict[str, Any] | None = None):
    params = dict(params or {})
    params["access_token"] = cfg["api_key"]
    response = http_request("GET",
        cfg["api_v1_url"].rstrip("/") + "/" + path.lstrip("/"),
        params=params,
        timeout=_request_timeout(cfg),
    )
    response.raise_for_status()
    return response.json()


def api_post_json(url: str, payload: dict[str, Any], timeout: int = 15):
    response = http_request("POST",url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def user_id_from(payload: Any) -> str | None:
    for path in ("data.id", "user.id", "id", "data.user.id"):
        value = deep_get(payload, path)
        if value not in (None, ""):
            return str(value)
    return None


def _load_runtime_state() -> dict[str, Any]:
    data = load_json(RUNTIME_STATE_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_runtime_state(**patch) -> dict[str, Any]:
    data = _load_runtime_state()
    data.update(patch)
    data["updatedAt"] = time.time()
    save_json(RUNTIME_STATE_FILE, data)
    return data


def resolve_user_id(cfg: dict[str, Any]) -> str:
    # A user ID belongs to the API key AND region, not to the installation.
    scope=hashlib.sha256((str(cfg.get('api_key',''))+'|'+str(cfg.get('api_v1_url',''))).encode()).hexdigest()
    runtime=_load_runtime_state()
    if runtime.get('credentialScope')==scope and runtime.get('userId'):
        return str(runtime['userId'])
    payload=api_get(cfg,'/user')
    uid=user_id_from(payload)
    if not uid:
        raise RuntimeError('DonatePay не вернул User ID. Проверь регион кабинета (.ru или .eu) и API-ключ.')
    _save_runtime_state(userId=uid,credentialScope=scope)
    current=load_json(CONFIG_FILE,{})
    current['user_id']=uid
    save_json(CONFIG_FILE,current)
    log('User ID проверен для текущего ключа и региона')
    return uid


def normalize_transaction(item: Any):
    if not isinstance(item, dict):
        return None
    status = str(item.get("status") or "").lower()
    transaction_type = str(item.get("type") or "").lower()
    if status and status != "success":
        return None
    if transaction_type and transaction_type != "donation":
        return None
    return donation_from_candidate(item, "donatepay", "RUB", "DonatePay API")


def transaction_items(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        for key in ("data", "transactions", "items", "rows", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for sub_key in ("data", "items", "rows", "transactions"):
                    nested = value.get(sub_key)
                    if isinstance(nested, list):
                        return nested
    return payload if isinstance(payload, list) else []


def load_seen() -> tuple[bool, set[str]]:
    data = load_json(SEEN_FILE, {"initialized": False, "ids": []})
    return bool(data.get("initialized")), set(map(str, data.get("ids") or []))


def save_seen(ids: set[str]) -> None:
    save_json(
        SEEN_FILE,
        {
            "initialized": True,
            "ids": sorted(ids)[-5000:],
            "updatedAt": time.time(),
        },
    )


def send(cfg: dict[str, Any], donation: dict[str, Any], seen: set[str]) -> bool:
    key = str(donation["externalId"])
    if key in seen:
        STATUS.update(lastSkippedEvent=key,duplicateEvents=int(STATUS.data.get('duplicateEvents',0))+1)
        log('Событие уже учтено ранее; повтор пропущен','DEBUG')
        return False
    result = post_donation(
        cfg.get("widget_api_url", "http://127.0.0.1:3333/api/donation"),
        donation,
        timeout=_request_timeout(cfg),
    )
    seen.add(key)
    save_seen(seen)
    STATUS.update(lastEvent=key, lastError=None)
    log(
        f"Донат {key}: {donation['username']} — "
        f"{donation['amount']} {donation['currency']} | {result.get('message', 'OK')}"
    )
    return True


def _retry_after_seconds(response, cfg: dict[str, Any]) -> int:
    fallback = max(300, int(cfg.get("catch_up_rate_limit_delay_seconds", 900)))
    raw = str(response.headers.get("Retry-After") or "").strip()
    try:
        return max(60, int(float(raw)))
    except Exception:
        return fallback


def catch_up(cfg: dict[str, Any], seen: set[str]) -> None:
    if not cfg.get("catch_up_enabled", False):
        STATUS.update(catchUpStatus="disabled", catchUpRetryAt=None)
        return

    state = load_json(CATCH_UP_STATE_FILE, {})
    now = time.time()
    retry_at = float(state.get("retryAfterUntil") or 0)
    minimum_interval = max(600, int(cfg.get("catch_up_min_interval_seconds", 1800)))
    last_attempt = float(state.get("lastAttemptAt") or 0)

    if retry_at > now:
        STATUS.update(catchUpStatus="rate_limited", catchUpRetryAt=retry_at)
        return
    if last_attempt and now - last_attempt < minimum_interval:
        STATUS.update(catchUpStatus="cooldown")
        return

    state["lastAttemptAt"] = now
    save_json(CATCH_UP_STATE_FILE, state)
    STATUS.update(catchUpStatus="requesting", catchUpRetryAt=None)

    params = {
        "limit": max(1, min(int(cfg.get("catch_up_limit", 10)), 25)),
        "order": "DESC",
        "type": "donation",
        "status": "success",
        "access_token": cfg["api_key"],
    }
    url = cfg["api_v1_url"].rstrip("/") + "/transactions"
    response = http_request("GET",url, params=params, timeout=_request_timeout(cfg))

    if response.status_code == 429:
        retry_seconds = _retry_after_seconds(response, cfg)
        retry_at = time.time() + retry_seconds
        state.update({"retryAfterUntil": retry_at, "lastStatus": 429})
        save_json(CATCH_UP_STATE_FILE, state)
        STATUS.update(catchUpStatus="rate_limited", catchUpRetryAt=retry_at)
        log(
            f"/transactions ограничен (HTTP 429). Catch-up выключен на {retry_seconds} сек.; "
            "real-time WebSocket продолжает работу.",
            "WARN",
        )
        return

    response.raise_for_status()
    payload = response.json()
    initialized, _ = load_seen()
    donations = [normalize_transaction(item) for item in transaction_items(payload)]
    donations = [item for item in donations if item]

    if not initialized and not cfg.get("import_existing_first_run", False):
        seen.update(str(item["externalId"]) for item in donations)
        save_seen(seen)
        log(f"Первый catch-up: запомнено старых операций — {len(donations)}")
    else:
        for donation in reversed(donations):
            try:
                send(cfg, donation, seen)
            except Exception as error:
                log(f"Catch-up {donation.get('externalId')}: {safe_error(error)}", "WARN")

    finished = time.time()
    state.update({"lastSuccessAt": finished, "retryAfterUntil": 0, "lastStatus": 200})
    save_json(CATCH_UP_STATE_FILE, state)
    STATUS.update(
        catchUpStatus="ok",
        catchUpRetryAt=None,
        catchUpLastSuccessAt=finished,
    )


class DonatePayAuthError(RuntimeError):
    pass


def get_connection_token(cfg: dict[str, Any]) -> str:
    payload = api_post_json(
        cfg["socket_token_url"],
        {"access_token": cfg["api_key"]},
        _request_timeout(cfg),
    )
    token = deep_get(payload, "token", "data.token", "result.token")
    if not token:
        if isinstance(payload,dict) and 'incorrect token' in str(payload.get('message','')).lower():
            raise DonatePayAuthError('DonatePay отклонил ключ на выбранном сервере (Incorrect token). Проверь регион кабинета (.ru/.eu), затем API-ключ.')
        raise RuntimeError("DonatePay не вернул connection token; проверь API-ключ и доступность сервиса")
    return str(token)


def get_subscription_token(cfg: dict[str, Any], client: str, channel: str) -> str:
    attempts = [
        {"access_token": cfg["api_key"], "client": client, "channels": [channel]},
        {"access_token": cfg["api_key"], "client": client, "channel": channel},
        {"access_token": cfg["api_key"], "channels": [channel]},
    ]
    last_error: BaseException | None = None
    for body in attempts:
        try:
            payload = api_post_json(cfg["socket_token_url"], body, _request_timeout(cfg))
            token = deep_get(payload, "token", "data.token", "result.token")
            if not token and isinstance(payload.get("channels"), list):
                token = next(
                    (
                        item.get("token")
                        for item in payload["channels"]
                        if isinstance(item, dict)
                        and str(item.get("channel") or channel) == channel
                    ),
                    None,
                )
            if token:
                return str(token)
        except Exception as error:
            last_error = error
    raise RuntimeError(f"Не получен subscription token: {safe_error(last_error or 'неизвестный ответ')}")


def _decode_json_frames(raw: Any) -> list[Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    frames: list[Any] = []
    for part in str(raw or "").splitlines():
        text = part.strip()
        if not text or text == "{}":
            continue
        try:
            frames.append(json.loads(text))
        except Exception:
            continue
    return frames


def _candidate_payloads(value: Any, depth: int = 0) -> Iterable[Any]:
    if depth > 12:
        return
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                yield from _candidate_payloads(json.loads(text), depth + 1)
            except Exception:
                pass
        return
    if isinstance(value, list):
        for item in value:
            yield from _candidate_payloads(item, depth + 1)
        return
    if not isinstance(value, dict):
        return

    yield value
    # Centrifugo v2/v3 publication envelopes and DonatePay notification payloads.
    for key in ("data", "result", "push", "pub", "publication", "message", "notification", "vars"):
        if key in value:
            yield from _candidate_payloads(value[key], depth + 1)


def _donatepay_test_notification(candidate: Any) -> dict[str, Any] | None:
    """Convert DonatePay test notifications where notification.id is null.

    Real donations normally contain an ID and are handled by the common parser.
    DonatePay's dashboard test frames can contain a complete donation in
    notification.vars but deliberately set notification.id to null.  We create a
    deterministic test-only ID from the payload so the event enters Core while a
    retransmitted frame is still deduplicated.
    """
    if not isinstance(candidate, dict):
        return None

    notification = candidate.get("notification") if isinstance(candidate.get("notification"), dict) else candidate
    if not isinstance(notification, dict):
        return None
    if str(notification.get("type") or "").lower() != "donation":
        return None
    vars_data = notification.get("vars") if isinstance(notification.get("vars"), dict) else {}
    if not vars_data:
        return None

    amount = vars_data.get("sum") if vars_data.get("sum") not in (None, "") else vars_data.get("amount")
    try:
        amount_num = float(str(amount).replace(",", "."))
    except Exception:
        return None
    if amount_num <= 0:
        return None

    external_id = notification.get("id") or vars_data.get("id") or vars_data.get("notification_id")
    if external_id in (None, ""):
        canonical = json.dumps(
            {
                "user_id": notification.get("user_id"),
                "type": notification.get("type"),
                "vars": vars_data,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        external_id = "test-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]

    return {
        "source": "donatepay",
        "externalId": str(external_id),
        "username": str(vars_data.get("name") or vars_data.get("username") or "DonatePay"),
        "amount": amount_num,
        "currency": str(vars_data.get("currency") or "RUB").upper(),
        "message": str(vars_data.get("comment") or vars_data.get("message") or ""),
        "createdAt": str(vars_data.get("created_at") or vars_data.get("date") or ""),
        "note": "DonatePay Centrifugo test notification" if str(external_id).startswith("test-") else "DonatePay Centrifugo",
    }


def extract_ws(raw: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    keys: set[str] = set()
    for frame in _decode_json_frames(raw):
        for candidate in _candidate_payloads(frame):
            donations = extract_donations(candidate, "donatepay", "RUB", "DonatePay Centrifugo")
            if isinstance(candidate, dict):
                direct = donation_from_candidate(candidate, "donatepay", "RUB", "DonatePay Centrifugo")
                if direct:
                    donations.append(direct)
                test_notification = _donatepay_test_notification(candidate)
                if test_notification:
                    donations.append(test_notification)
            for donation in donations:
                key = str(donation.get("externalId") or "")
                if key and key not in keys:
                    keys.add(key)
                    result.append(donation)
    return result


def _validate_reply(raw: Any, operation: str) -> dict[str, Any]:
    frames = _decode_json_frames(raw)
    if not frames or not isinstance(frames[0], dict):
        raise RuntimeError(f"Centrifugo: пустой ответ на {operation}")
    reply = frames[0]
    if reply.get("error"):
        raise RuntimeError(f"Centrifugo {operation}: {reply['error']}")
    return reply


def socket_message(ws, pending):
    if pending:return pending.pop(0)
    opcode,raw=ws.recv_data(control_frame=True)
    if opcode in (websocket.ABNF.OPCODE_PING,websocket.ABNF.OPCODE_PONG):
        STATUS.update(lastHeartbeatAt=time.time())
        return None
    if opcode==websocket.ABNF.OPCODE_CLOSE:
        raise RuntimeError('WebSocket закрыт сервером')
    return raw


def receive_reply(ws, identity, operation, pending):
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        raw=ws.recv()
        if raw in (None, ''):raise RuntimeError('WebSocket закрыт при подписке')
        if str(raw).strip()=='{}':ws.send('{}');continue
        match=None
        for frame in _decode_json_frames(raw):
            if isinstance(frame,dict) and frame.get('id')==identity:
                if frame.get('error'):raise RuntimeError(f'Centrifugo {operation}: {frame["error"]}')
                match=frame
            else:pending.append(json.dumps(frame,ensure_ascii=False))
        if match is not None:return match
    raise RuntimeError(f'Не получено подтверждение {operation}')


def main() -> None:
    if requests is None or websocket is None:
        raise SystemExit("Нужны requests и websocket-client")

    cfg = config()
    key = str(cfg.get("api_key") or "").strip()
    if not cfg.get("enabled"):
        raise SystemExit("DonatePay выключен")
    if not key:
        raise SystemExit("Не указан API-ключ DonatePay")

    delay = max(3, int(cfg.get("reconnect_delay_seconds", 5)))
    max_delay = max(delay, int(cfg.get("max_reconnect_delay_seconds", 60)))
    _, seen = load_seen()
    STATUS.update(running=True, status="starting", lastError=None)

    while True:
        ws = None
        try:
            cfg = config()
            uid = resolve_user_id(cfg)
            channel = f"$public:{uid}"
            STATUS.update(userId=uid, channel=channel, status="preparing", lastError=None)

            try:
                catch_up(cfg, seen)
            except Exception as error:
                STATUS.update(catchUpStatus="error")
                log(f"Catch-up пропущен: {safe_error(error)}", "WARN")

            STATUS.update(status="connecting_socket")
            connection_token = get_connection_token(cfg)
            ws = websocket.create_connection(cfg["websocket_url"], timeout=45, **({} if cfg.get("use_system_proxy",False) else {"http_no_proxy":["*"]}))
            ws.send(json.dumps({"params": {"token": connection_token}, "id": 1}))
            pending=[]
            auth = receive_reply(ws, 1, "connect", pending)
            client = deep_get(auth, "result.client")
            if not client:
                raise RuntimeError(f"Centrifugo не вернул client: {auth}")

            subscription_token = get_subscription_token(cfg, str(client), channel)
            ws.send(json.dumps({"params": {"channel": channel, "token": subscription_token}, "method": 1, "id": 2}))
            subscription_reply = receive_reply(ws, 2, "subscribe", pending)
            STATUS.update(
                connected=True,
                subscribed=True,
                status="subscribed",
                lastError=None,
                subscriptionReply="ok",
            )
            log(f"Подключено; канал {channel}")
            delay = max(3, int(cfg.get("reconnect_delay_seconds", 5)))

            while True:
                try:
                    raw = socket_message(ws,pending)
                    if raw is None:continue
                    STATUS.update(lastSocketReadAt=time.time())
                except websocket.WebSocketTimeoutException:
                    STATUS.update(status="subscribed", lastHeartbeatAt=time.time())
                    # Keep idle connections alive without re-running /user.
                    try:
                        ws.send("{}")
                    except Exception:
                        raise
                    continue
                except socket.timeout:
                    STATUS.update(status="subscribed", lastHeartbeatAt=time.time())
                    ws.send("{}")
                    continue

                if raw in (None, ""):
                    raise RuntimeError("WebSocket закрыт сервером")
                if str(raw).strip() == "{}":
                    ws.send("{}")
                    continue

                STATUS.update(framesReceived=int(STATUS.data.get("framesReceived", 0)) + 1)
                donations = extract_ws(raw)
                if not donations:
                    unrecognized = int(STATUS.data.get("unrecognizedFrames", 0)) + 1
                    STATUS.update(unrecognizedFrames=unrecognized)
                    if unrecognized <= 5:
                        preview = safe_error(raw)[:500]
                        log(f"Нераспознанный Centrifugo frame #{unrecognized}: {preview}", "DEBUG")
                    continue

                for donation in donations:
                    try:
                        send(cfg, donation, seen)
                    except Exception as error:
                        # Keep socket alive; Core delivery will be retried only if the
                        # same event is published again/caught by optional catch-up.
                        STATUS.update(lastDeliveryError=f"{type(error).__name__}: {safe_error(error)}")
                        log(f"Core delivery: {safe_error(error)}", "WARN")

        except KeyboardInterrupt:
            break
        except DonatePayAuthError as error:
            STATUS.update(connected=False,subscribed=False,status='authorization_error',lastError=str(error),nextRetryAt=time.time()+300)
            log(str(error)+' Повтор через 5 минут или после перезапуска.','ERROR')
            time.sleep(300)
        except Exception as error:
            safe = safe_error(error)
            STATUS.update(
                connected=False,
                subscribed=False,
                status="reconnecting",
                lastError=f"{type(error).__name__}: {safe}",
                reconnects=int(STATUS.data.get("reconnects", 0)) + 1,
            )
            log(f"{type(error).__name__}: {safe}; повтор через {delay} сек.", "WARN")
            time.sleep(delay)
            delay = min(max_delay, max(delay + 1, delay * 2))
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

    STATUS.update(running=False, connected=False, subscribed=False, status="stopped")


if __name__ == "__main__":
    main()
