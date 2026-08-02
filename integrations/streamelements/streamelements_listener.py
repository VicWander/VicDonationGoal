from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    requests = None

try:
    import websocket
except ImportError:
    websocket = None

DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = DIRECTORY.parent.parent
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from safe_json import load_json as _robust_load_json, save_json as _robust_save_json
CONFIG_FILE = DIRECTORY / "streamelements_config.json"
STATUS_FILE = PROJECT_ROOT / "runtime" / "integrations" / "streamelements_status.json"


def load_json(path: Path, fallback):
    return _robust_load_json(path, fallback, retries=16)


def save_json(path: Path, data):
    _robust_save_json(path, data, retries=120)


def split_values(value):
    if isinstance(value, list):
        return {str(item).strip().lower() for item in value}
    return {part.strip().lower() for part in str(value or "").split(",")}


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Status:
    def __init__(self):
        self.data = {
            "service": "streamelements",
            "running": False,
            "connected": False,
            "subscribed": False,
            "status": "stopped",
            "channel": None,
            "topic": "channel.tips",
            "lastEvent": None,
            "lastError": None,
            "reconnects": 0,
            "updatedAt": time.time(),
        }
        self.write()

    def update(self, **values):
        self.data.update(values)
        self.data["updatedAt"] = time.time()
        self.write()

    def write(self):
        try:
            save_json(STATUS_FILE, self.data)
        except Exception:
            pass


STATUS = Status()


def log(message, level="INFO"):
    print(f"[StreamElements] {level} {message}", flush=True)


def extract_donation(message, config=None):
    """Convert a StreamElements channel.tips message to VicDonationGoal format."""
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except Exception:
            return None
    if not isinstance(message, dict):
        return None
    if message.get("type") != "message" or message.get("topic") != "channel.tips":
        return None
    data = message.get("data")
    if not isinstance(data, dict):
        return None
    donation = data.get("donation")
    if not isinstance(donation, dict):
        return None

    config = config or {}
    accepted_statuses = split_values(config.get("accept_statuses", "success"))
    accepted_approvals = split_values(config.get("accept_approval_states", "allowed,approved,"))
    status = str(data.get("status") or "").strip().lower()
    approval = str(data.get("approved") or "").strip().lower()
    if accepted_statuses and status not in accepted_statuses:
        return None
    if accepted_approvals and approval not in accepted_approvals:
        return None

    user = donation.get("user") if isinstance(donation.get("user"), dict) else {}
    event_id = data.get("_id") or data.get("transactionId") or message.get("id")
    if event_id in (None, ""):
        return None
    return {
        "source": "streamelements",
        "externalId": str(event_id),
        "username": str(user.get("username") or user.get("displayName") or "Аноним"),
        "amount": donation.get("amount", 0),
        "currency": str(donation.get("currency") or "RUB").upper(),
        "message": str(donation.get("message") or ""),
        "createdAt": str(data.get("createdAt") or message.get("ts") or now_iso()),
        "note": f"StreamElements provider: {data.get('provider') or 'unknown'}",
    }


def send_donation(api_url, donation, timeout=10):
    if requests is None:
        raise RuntimeError("Не установлена библиотека requests")
    last_error = None
    for attempt in range(1, 4):
        try:
            response = requests.post(api_url, json=donation, timeout=timeout)
            payload = response.json() if response.text else {}
            if response.ok and payload.get("ok", True):
                return payload
            raise RuntimeError(payload.get("message") or f"Core HTTP {response.status_code}")
        except Exception as error:
            last_error = error
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError(f"Не удалось передать донат в Core: {last_error}")


def subscription_payload(config):
    return {
        "type": "subscribe",
        "nonce": str(uuid.uuid4()),
        "data": {
            "topic": str(config.get("topic") or "channel.tips"),
            "room": str(config.get("channel_id") or "").strip(),
            "token": str(config.get("token") or "").strip(),
            "token_type": str(config.get("token_type") or "jwt").strip().lower(),
        },
    }


def validate_config(config):
    if not bool(config.get("enabled", False)):
        raise RuntimeError("Интеграция выключена")
    if not str(config.get("channel_id") or "").strip():
        raise RuntimeError("Не указан StreamElements Channel ID")
    if not str(config.get("token") or "").strip():
        raise RuntimeError("Не указан StreamElements token")
    if str(config.get("token_type") or "jwt") not in {"jwt", "apikey", "oauth2"}:
        raise RuntimeError("token_type должен быть jwt, apikey или oauth2")
    if requests is None or websocket is None:
        raise RuntimeError("Нужны requests и websocket-client")


def connect_loop(config):
    reconnect_url = None
    base_url = str(config.get("websocket_url") or "wss://astro.streamelements.com/")
    delay = max(1, int(config.get("reconnect_delay_seconds") or 3))
    max_delay = max(delay, int(config.get("max_reconnect_delay_seconds") or 60))
    api_url = str(config.get("widget_api_url") or "http://127.0.0.1:3333/api/donation")
    timeout = max(3, int(config.get("request_timeout_seconds") or 10))

    while True:
        ws = None
        try:
            url = reconnect_url or base_url
            STATUS.update(running=True, connected=False, subscribed=False, status="connecting", lastError=None)
            log(f"Подключение к {base_url}")
            ws = websocket.create_connection(url, timeout=45)
            STATUS.update(connected=True, status="connected", channel=str(config.get("channel_id")))
            subscribed = False
            while True:
                raw = ws.recv()
                if raw in (None, ""):
                    raise RuntimeError("WebSocket закрыт сервером")
                try:
                    packet = json.loads(raw)
                except Exception:
                    continue
                packet_type = packet.get("type")
                if packet_type == "welcome":
                    ws.send(json.dumps(subscription_payload(config), ensure_ascii=False))
                    continue
                if packet_type == "response":
                    if packet.get("error"):
                        detail = packet.get("data") or {}
                        raise RuntimeError(detail.get("message") or str(packet.get("error")))
                    subscribed = True
                    STATUS.update(subscribed=True, status="subscribed")
                    log("Подписка channel.tips активна")
                    continue
                if packet_type == "reconnect":
                    token = str((packet.get("data") or {}).get("reconnect_token") or "")
                    reconnect_url = base_url + ("&" if "?" in base_url else "?") + urlencode({"reconnect_token": token}) if token else None
                    raise RuntimeError("StreamElements запросил graceful reconnect")
                donation = extract_donation(packet, config)
                if donation:
                    result = send_donation(api_url, donation, timeout)
                    STATUS.update(lastEvent=donation.get("externalId"), status="subscribed", lastError=None)
                    log(f"Донат {donation['externalId']} учтён: {result.get('message', 'OK')}")
        except KeyboardInterrupt:
            break
        except Exception as error:
            STATUS.update(connected=False, subscribed=False, status="reconnecting", lastError=f"{type(error).__name__}: {error}", reconnects=int(STATUS.data.get("reconnects") or 0)+1)
            log(f"{type(error).__name__}: {error}; повтор через {delay} сек.", "ERROR")
            time.sleep(delay)
            delay = min(max_delay, max(delay + 1, delay * 2))
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
    STATUS.update(running=False, connected=False, subscribed=False, status="stopped")


def main():
    config = load_json(CONFIG_FILE, {})
    try:
        validate_config(config)
    except Exception as error:
        STATUS.update(running=False, connected=False, status="error", lastError=str(error))
        log(str(error), "ERROR")
        raise SystemExit(1)
    STATUS.update(running=True, status="starting", topic=str(config.get("topic") or "channel.tips"))
    connect_loop(config)


if __name__ == "__main__":
    main()
