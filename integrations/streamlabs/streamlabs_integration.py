from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, quote

try:
    import requests
except ImportError:
    requests = None

try:
    import websocket
except ImportError:
    websocket = None

SL_AUTHORIZE_URL = "https://streamlabs.com/api/v2.0/authorize"
SL_TOKEN_URL = "https://streamlabs.com/api/v2.0/token"
SL_API_BASE = "https://streamlabs.com/api/v2.0"


class StreamlabsIntegration:
    """Streamlabs OAuth + lightweight Socket.IO WebSocket adapter.

    The official API delivers donations through Socket.IO. To avoid a second
    Socket.IO dependency, this adapter implements the small subset of Engine.IO /
    Socket.IO packets required for the default namespace and the `event` event.
    It tries Engine.IO v4 and v3 for compatibility.
    """

    def __init__(self, project_root: Path, add_donation, load_json, save_json):
        self.project_root = Path(project_root)
        self.directory = self.project_root / "integrations" / "streamlabs"
        self.config_file = self.directory / "streamlabs_config.json"
        self.tokens_file = self.directory / "streamlabs_tokens.json"
        self.oauth_state_file = self.directory / "oauth_state.txt"
        self.status_file = self.project_root / "runtime" / "integrations" / "streamlabs_status.json"
        self.log_file = self.project_root / "runtime" / "integrations" / "streamlabs.log"
        self.add_donation = add_donation
        self.load_json = load_json
        self.save_json = save_json
        self.status = {
            "service": "streamlabs",
            "configured": False,
            "authorized": False,
            "connected": False,
            "running": False,
            "status": "stopped",
            "engineIoVersion": None,
            "lastError": None,
            "lastEvent": None,
            "updatedAt": time.time(),
        }
        self._logs = []
        self._lock = threading.RLock()
        self._thread = None
        self._stop = threading.Event()
        self._socket = None
        self.directory.mkdir(parents=True, exist_ok=True)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.reload_config()
        self._load_tokens()
        self._write_status()

    def _log(self, message, level="INFO"):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {level} {message}"
        print(f"[Streamlabs] {message}")
        with self._lock:
            self._logs.append(line)
            self._logs = self._logs[-500:]
            try:
                with self.log_file.open("a", encoding="utf-8") as file:
                    file.write(line + "\n")
            except Exception:
                pass

    def logs(self, limit=250):
        with self._lock:
            return list(self._logs[-max(1, int(limit)):])

    def _write_status(self):
        self.status["updatedAt"] = time.time()
        try:
            self.save_json(self.status_file, self.status)
        except Exception:
            pass

    def config(self):
        data = self.load_json(self.config_file, {})
        return data if isinstance(data, dict) else {}

    def reload_config(self):
        config = self.config()
        client_id = str(config.get("client_id") or "").strip()
        client_secret = str(config.get("client_secret") or "").strip()
        self.status["configured"] = bool(config.get("enabled", False) and client_id and client_secret and "ВСТАВЬ" not in client_id and "ВСТАВЬ" not in client_secret)
        self._write_status()
        return config

    def _load_tokens(self):
        tokens = self.load_json(self.tokens_file, {})
        if not isinstance(tokens, dict):
            tokens = {}
        self.status["authorized"] = bool(tokens.get("access_token"))
        return tokens

    def _save_tokens(self, tokens):
        self.save_json(self.tokens_file, tokens)
        self.status["authorized"] = bool(tokens.get("access_token"))
        self._write_status()

    def clear_auth(self):
        self.stop()
        for path in (self.tokens_file, self.oauth_state_file):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self.status.update({"authorized": False, "connected": False, "lastError": None, "status": "stopped"})
        self._write_status()

    def libraries_ok(self):
        return requests is not None and websocket is not None

    def _access_token(self):
        return str(self._load_tokens().get("access_token") or "").strip() or None

    def begin_oauth(self):
        if not self.libraries_ok():
            raise RuntimeError("Не установлены requests/websocket-client")
        config = self.reload_config()
        if not self.status.get("configured"):
            raise RuntimeError("Сначала заполните client_id и client_secret")
        state = secrets.token_urlsafe(24)
        self.oauth_state_file.write_text(state, encoding="utf-8")
        params = {
            "response_type": "code",
            "client_id": config.get("client_id"),
            "redirect_uri": config.get("redirect_uri"),
            "scope": config.get("scopes", "socket.token"),
            "state": state,
        }
        return SL_AUTHORIZE_URL + "?" + urlencode(params)

    def finish_oauth(self, code, state):
        try:
            expected = self.oauth_state_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            expected = ""
        if not code:
            raise RuntimeError("Streamlabs не вернул authorization code")
        if not expected or state != expected:
            raise RuntimeError("Не совпал OAuth state; начните авторизацию заново")
        config = self.reload_config()
        response = requests.post(
            SL_TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "client_id": config.get("client_id"),
                "client_secret": config.get("client_secret"),
                "redirect_uri": config.get("redirect_uri"),
                "code": code,
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
            timeout=25,
        )
        if not response.ok:
            raise RuntimeError(f"Streamlabs token HTTP {response.status_code}: {response.text[:500]}")
        self._save_tokens(response.json())
        self.start()
        return self.public_status()

    def api_request(self, method, endpoint):
        if requests is None:
            raise RuntimeError("Не установлена библиотека requests")
        token = self._access_token()
        if not token:
            raise RuntimeError("Streamlabs не авторизован")
        config = self.config()
        base = str(config.get("api_base") or SL_API_BASE).rstrip("/")
        response = requests.request(
            method,
            base + endpoint,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
            timeout=25,
        )
        if response.status_code == 401:
            self.status.update({"authorized": False, "lastError": "Streamlabs вернул 401; нужна повторная авторизация"})
            self._write_status()
            raise RuntimeError(self.status["lastError"])
        response.raise_for_status()
        return response.json() if response.text else {}

    @staticmethod
    def _find_socket_token(payload):
        if isinstance(payload, str) and payload.strip():
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("socket_token", "socketToken", "token"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in payload.values():
                found = StreamlabsIntegration._find_socket_token(value)
                if found:
                    return found
        if isinstance(payload, list):
            for value in payload:
                found = StreamlabsIntegration._find_socket_token(value)
                if found:
                    return found
        return None

    def _socket_token(self):
        data = self.api_request("GET", "/socket/token")
        token = self._find_socket_token(data)
        if not token:
            raise RuntimeError("Streamlabs не вернул socket token")
        return token

    @staticmethod
    def extract_donations(event_data):
        """Return normalized donation dictionaries from a Streamlabs Socket event."""
        events = event_data if isinstance(event_data, list) else [event_data]
        result = []
        for event in events:
            if not isinstance(event, dict) or str(event.get("type") or "") != "donation":
                continue
            target = str(event.get("for") or "").strip().lower()
            if target not in ("", "streamlabs"):
                continue
            messages = event.get("message")
            if not isinstance(messages, list):
                messages = [messages] if isinstance(messages, dict) else []
            for item in messages:
                if not isinstance(item, dict):
                    continue
                external_id = item.get("_id") or item.get("id") or event.get("event_id")
                if external_id in (None, ""):
                    continue
                result.append({
                    "source": "streamlabs",
                    "externalId": str(external_id),
                    "username": str(item.get("name") or item.get("from") or "Аноним"),
                    "amount": item.get("amount", 0),
                    "currency": str(item.get("currency") or "USD").upper(),
                    "message": str(item.get("message") or ""),
                    "createdAt": str(item.get("created_at") or item.get("createdAt") or time.strftime("%Y-%m-%dT%H:%M:%S%z")),
                    "note": f"Streamlabs event_id: {event.get('event_id') or ''}",
                })
        return result

    @staticmethod
    def _decode_socket_event(frame):
        if not isinstance(frame, str):
            return []
        # Socket.IO event packet: 42["event", {...}]
        if not frame.startswith("42"):
            return []
        try:
            payload = json.loads(frame[2:])
        except Exception:
            return []
        if not isinstance(payload, list) or len(payload) < 2 or payload[0] != "event":
            return []
        return StreamlabsIntegration.extract_donations(payload[1])

    def _engine_versions(self):
        raw = str(self.config().get("engineio_versions") or "4,3")
        versions = []
        for part in raw.split(","):
            try:
                version = int(part.strip())
            except Exception:
                continue
            if version in (3, 4) and version not in versions:
                versions.append(version)
        return versions or [4, 3]

    def _socket_url(self, socket_token, engine_version):
        base = str(self.config().get("socket_base") or "wss://sockets.streamlabs.com/socket.io/")
        separator = "&" if "?" in base else "?"
        return base + separator + urlencode({"token": socket_token, "EIO": engine_version, "transport": "websocket"})

    def _connect_once(self, socket_token, engine_version, probe=False):
        ws = websocket.create_connection(self._socket_url(socket_token, engine_version), timeout=35)
        self._socket = ws
        namespace_open = False
        try:
            opened_at = time.time()
            while not self._stop.is_set():
                frame = ws.recv()
                if frame in (None, ""):
                    raise RuntimeError("Socket.IO соединение закрыто")
                if isinstance(frame, bytes):
                    frame = frame.decode("utf-8", errors="replace")
                if frame.startswith("0"):
                    # Engine.IO open. Open the default Socket.IO namespace.
                    ws.send("40")
                    continue
                if frame == "2" or frame.startswith("2"):
                    ws.send("3" + frame[1:])
                    continue
                if frame.startswith("40"):
                    namespace_open = True
                    self.status.update({"connected": True, "status": "connected", "engineIoVersion": engine_version, "lastError": None})
                    self._write_status()
                    if probe:
                        return True
                    continue
                if frame.startswith("44"):
                    raise RuntimeError(f"Socket.IO connect_error: {frame[2:500]}")
                for donation in self._decode_socket_event(frame):
                    state, ok, message = self.add_donation(donation)
                    self.status.update({"lastEvent": donation.get("externalId"), "lastError": None, "status": "connected"})
                    self._write_status()
                    self._log(f"Донат {donation.get('externalId')}: {message}")
                if not namespace_open and time.time() - opened_at > 12:
                    raise RuntimeError("Socket.IO namespace не подтвердил подключение")
            return True
        finally:
            self._socket = None
            try:
                ws.close()
            except Exception:
                pass

    def _listener_loop(self):
        delay = max(1, int(self.config().get("reconnect_delay_seconds") or 3))
        max_delay = max(delay, int(self.config().get("max_reconnect_delay_seconds") or 60))
        while not self._stop.is_set():
            try:
                token = self._socket_token()
                last_error = None
                for version in self._engine_versions():
                    try:
                        self._log(f"Подключение Socket.IO, Engine.IO v{version}")
                        self._connect_once(token, version)
                        last_error = None
                        break
                    except Exception as error:
                        last_error = error
                        self._log(f"Engine.IO v{version}: {type(error).__name__}: {error}", "WARN")
                        if self._stop.is_set():
                            break
                if last_error and not self._stop.is_set():
                    raise last_error
                delay = max(1, int(self.config().get("reconnect_delay_seconds") or 3))
            except Exception as error:
                self.status.update({"connected": False, "status": "reconnecting", "lastError": f"{type(error).__name__}: {error}"})
                self._write_status()
                self._log(f"{type(error).__name__}: {error}; повтор через {delay} сек.", "ERROR")
                self._stop.wait(delay)
                delay = min(max_delay, max(delay + 1, delay * 2))
        self.status.update({"running": False, "connected": False, "status": "stopped"})
        self._write_status()

    def start(self):
        config = self.reload_config()
        if not bool(config.get("enabled", False)):
            return
        if not self.status.get("configured"):
            raise RuntimeError("Streamlabs config не заполнен")
        if not self._access_token():
            raise RuntimeError("Streamlabs не авторизован")
        if not self.libraries_ok():
            raise RuntimeError("Не установлены requests/websocket-client")
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self.status.update({"running": True, "status": "starting", "lastError": None})
            self._write_status()
            self._thread = threading.Thread(target=self._listener_loop, name="StreamlabsIntegration", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        ws = self._socket
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3)
        self._thread = None
        self.status.update({"running": False, "connected": False, "status": "stopped"})
        self._write_status()

    def test_connection(self):
        config = self.reload_config()
        if not bool(config.get("enabled", False)):
            return {"ok": False, "message": "Streamlabs выключен"}
        if not self.status.get("configured"):
            return {"ok": False, "message": "Не заполнены client_id/client_secret"}
        if not self._access_token():
            return {"ok": False, "message": "Нужна OAuth-авторизация", "authorizeUrl": "/auth/streamlabs/start"}
        try:
            token = self._socket_token()
            if not token:
                raise RuntimeError("Пустой socket token")
            # If listener is already connected, no need for a second socket.
            if self.status.get("connected"):
                return {"ok": True, "message": f"Streamlabs подключён (Engine.IO v{self.status.get('engineIoVersion')})"}
            last_error = None
            for version in self._engine_versions():
                try:
                    self._connect_once(token, version, probe=True)
                    return {"ok": True, "message": f"Socket token получен; WebSocket handshake работает (Engine.IO v{version})"}
                except Exception as error:
                    last_error = error
            raise last_error or RuntimeError("Не удалось подключиться к Socket.IO")
        except Exception as error:
            return {"ok": False, "message": f"{type(error).__name__}: {error}"}

    def public_status(self):
        self.reload_config()
        self._load_tokens()
        result = dict(self.status)
        result["librariesOk"] = self.libraries_ok()
        result["authorizeUrl"] = "/auth/streamlabs/start"
        result["last_error"] = result.get("lastError")
        result["last_event"] = result.get("lastEvent")
        return result
