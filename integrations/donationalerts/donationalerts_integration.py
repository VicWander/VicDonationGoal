from __future__ import annotations

import json
import os
import secrets
import threading
import time
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


DA_AUTH_URL = "https://www.donationalerts.com/oauth/authorize"
DA_TOKEN_URL = "https://www.donationalerts.com/oauth/token"
DA_API_BASE = "https://www.donationalerts.com/api/v1"
DA_WS_URL = "wss://centrifugo.donationalerts.com/connection/websocket"


class DonationAlertsIntegration:
    def __init__(self, project_root: Path, add_donation, load_json, save_json):
        self.project_root = Path(project_root)
        self.directory = self.project_root / "integrations" / "donationalerts"
        self.config_file = self.directory / "donationalerts_config.json"
        self.tokens_file = self.directory / "donationalerts_tokens.json"
        self.oauth_state_file = self.directory / "oauth_state.txt"
        self.status_file = self.project_root / "runtime" / "integrations" / "donationalerts_status.json"
        self.log_file = self.project_root / "runtime" / "integrations" / "donationalerts.log"
        self.add_donation = add_donation
        self.load_json = load_json
        self.save_json = save_json
        self.status = {
            "service": "donationalerts",
            "configured": False,
            "authorized": False,
            "connected": False,
            "running": False,
            "channel": None,
            "lastError": None,
            "lastEvent": None,
            "updatedAt": time.time(),
        }
        self._logs = []
        self._lock = threading.RLock()
        self._thread = None
        self._stop = threading.Event()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.reload_config()
        self._load_tokens()
        self._write_status()

    def _log(self, message, level="INFO"):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {level} {message}"
        print(f"[DA] {message}")
        with self._lock:
            self._logs.append(line)
            self._logs = self._logs[-500:]
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
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
        self.status["configured"] = bool(
            config.get("enabled", False)
            and client_id
            and client_secret
            and "ВСТАВЬ" not in client_id
            and "ВСТАВЬ" not in client_secret
        )
        self._write_status()
        return config

    def _load_tokens(self):
        tokens = self.load_json(self.tokens_file, {})
        if not isinstance(tokens, dict):
            tokens = {}
        self.status["authorized"] = bool(tokens.get("access_token"))
        return tokens

    def _save_tokens(self, tokens):
        if "expires_in" in tokens:
            tokens["expires_at"] = time.time() + int(tokens.get("expires_in") or 0) - 120
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
        self.status.update({"authorized": False, "connected": False, "lastError": None})
        self._write_status()

    def libraries_ok(self):
        return requests is not None and websocket is not None

    def _valid_access_token(self):
        config = self.reload_config()
        tokens = self._load_tokens()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_at = float(tokens.get("expires_at") or 0)
        if not access_token:
            return None
        if not expires_at or time.time() < expires_at:
            return access_token
        if not refresh_token:
            self.status["lastError"] = "Access token истёк, refresh_token отсутствует"
            self._write_status()
            return None
        if requests is None:
            self.status["lastError"] = "Не установлена библиотека requests"
            self._write_status()
            return None
        try:
            response = requests.post(DA_TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": config.get("client_id"),
                "client_secret": config.get("client_secret"),
                "scope": config.get("scopes", "oauth-user-show oauth-donation-subscribe oauth-donation-index"),
            }, timeout=20)
            response.raise_for_status()
            new_tokens = response.json()
            new_tokens.setdefault("refresh_token", refresh_token)
            self._save_tokens(new_tokens)
            return new_tokens.get("access_token")
        except Exception as error:
            self.status["lastError"] = f"Не удалось обновить токен: {type(error).__name__}: {error}"
            self._write_status()
            return None

    def api_request(self, method, endpoint, json_data=None):
        if requests is None:
            raise RuntimeError("Не установлена библиотека requests")
        token = self._valid_access_token()
        if not token:
            raise RuntimeError("DonationAlerts не авторизован")
        response = requests.request(
            method,
            DA_API_BASE + endpoint,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json=json_data,
            timeout=20,
        )
        if response.status_code == 401:
            self.clear_auth()
            raise RuntimeError("DonationAlerts вернул 401; нужна повторная авторизация")
        response.raise_for_status()
        return response.json() if response.text else {}

    def begin_oauth(self):
        if not self.libraries_ok():
            raise RuntimeError("Не установлены requests/websocket-client")
        config = self.reload_config()
        if not self.status.get("configured"):
            raise RuntimeError("Сначала заполните client_id и client_secret")
        oauth_state = secrets.token_urlsafe(24)
        self.oauth_state_file.write_text(oauth_state, encoding="utf-8")
        params = {
            "client_id": config.get("client_id"),
            "redirect_uri": config.get("redirect_uri"),
            "response_type": "code",
            "scope": config.get("scopes", "oauth-user-show oauth-donation-subscribe oauth-donation-index"),
            "state": oauth_state,
        }
        return DA_AUTH_URL + "?" + urlencode(params)

    def finish_oauth(self, code, state):
        expected = ""
        try:
            expected = self.oauth_state_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            pass
        if not code:
            raise RuntimeError("DonationAlerts не вернул authorization code")
        if not expected or state != expected:
            raise RuntimeError("Не совпал OAuth state; начните авторизацию заново")
        config = self.reload_config()
        response = requests.post(DA_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
            "redirect_uri": config.get("redirect_uri"),
            "code": code,
        }, timeout=20)
        response.raise_for_status()
        self._save_tokens(response.json())
        self.start()
        return self.public_status()

    @staticmethod
    def extract_donation(message):
        try:
            data = json.loads(message)
        except Exception:
            return None
        if not isinstance(data, dict) or not data:
            return None
        result = data.get("result")
        if not isinstance(result, dict):
            return None
        channel = str(result.get("channel") or "")
        if not channel.startswith("$alerts:donation_"):
            return None
        outer = result.get("data")
        donation = outer.get("data") if isinstance(outer, dict) else None
        if not isinstance(donation, dict) or donation.get("id") is None:
            return None
        return {
            "source": "donationalerts",
            "externalId": donation.get("id"),
            "username": donation.get("username") or donation.get("name") or "Аноним",
            "amount": donation.get("amount"),
            "currency": donation.get("currency") or "RUB",
            "message": donation.get("message") or "",
            "createdAt": donation.get("created_at") or "",
        }

    def _listener_loop(self):
        reconnect_delay = 5
        self.status["running"] = True
        self._write_status()
        while not self._stop.is_set():
            ws = None
            try:
                config = self.reload_config()
                if not bool(config.get("enabled", False)):
                    self.status.update({"running": False, "connected": False, "lastError": None})
                    self._write_status()
                    return
                if not self.status.get("configured"):
                    raise RuntimeError("DonationAlerts не настроен")
                if not self._load_tokens().get("access_token"):
                    raise RuntimeError("DonationAlerts не авторизован")
                user_response = self.api_request("GET", "/user/oauth")
                user_data = user_response.get("data") or {}
                user_id = user_data.get("id")
                socket_token = user_data.get("socket_connection_token")
                if not user_id or not socket_token:
                    raise RuntimeError("В /user/oauth нет id или socket_connection_token")
                channel_name = f"$alerts:donation_{user_id}"
                self.status["channel"] = channel_name
                self._log(f"Подключение к {DA_WS_URL}")
                ws = websocket.create_connection(DA_WS_URL, timeout=30)
                ws.send(json.dumps({"params": {"token": socket_token}, "id": 1}))
                auth_response = json.loads(ws.recv())
                centrifugo_client = auth_response.get("result", {}).get("client")
                if not centrifugo_client:
                    raise RuntimeError("Centrifugo не вернул client id")
                subscription = self.api_request("POST", "/centrifuge/subscribe", json_data={
                    "channels": [channel_name],
                    "client": centrifugo_client,
                })
                subscription_token = next((item.get("token") for item in subscription.get("channels", []) if item.get("channel") == channel_name), None)
                if not subscription_token:
                    raise RuntimeError("Не получен subscription token")
                ws.send(json.dumps({
                    "params": {"channel": channel_name, "token": subscription_token},
                    "method": 1,
                    "id": 2,
                }))
                ws.recv()
                self.status.update({"connected": True, "running": True, "lastError": None})
                self._write_status()
                self._log(f"Подключено; канал {channel_name}")
                reconnect_delay = 5
                while not self._stop.is_set():
                    raw = ws.recv()
                    if raw.strip() == "{}":
                        ws.send("{}")
                        continue
                    donation = self.extract_donation(raw)
                    if not donation:
                        continue
                    state, ok, message = self.add_donation(donation)
                    self.status["lastEvent"] = {
                        "ok": ok,
                        "message": message,
                        "donation": donation,
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    self._write_status()
                    self._log(f"Донат: {donation['username']} — {donation['amount']} {donation['currency']} | {message}")
            except Exception as error:
                self.status.update({"connected": False, "running": True, "lastError": f"{type(error).__name__}: {error}"})
                self._write_status()
                self._log(self.status["lastError"], "ERROR")
                try:
                    if ws:
                        ws.close()
                except Exception:
                    pass
                if not self._stop.wait(reconnect_delay):
                    reconnect_delay = min(reconnect_delay * 2, 60)
        self.status.update({"running": False, "connected": False})
        self._write_status()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        if not self.libraries_ok():
            self.status["lastError"] = "Не установлены requests/websocket-client"
            self._write_status()
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._listener_loop, daemon=True, name="DonationAlertsIntegration")
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.status.update({"running": False, "connected": False})
        self._write_status()

    def test_connection(self):
        config = self.reload_config()
        if not bool(config.get("enabled", False)):
            return {"ok": False, "message": "DonationAlerts выключен"}
        if not self.status.get("configured"):
            return {"ok": False, "message": "Не заполнены client_id/client_secret"}
        if not self._load_tokens().get("access_token"):
            return {"ok": False, "message": "Нужна OAuth-авторизация", "authorizeUrl": "/auth/donationalerts/start"}
        try:
            data = self.api_request("GET", "/user/oauth").get("data") or {}
            return {"ok": True, "message": f"Подключение работает; user_id={data.get('id', '?')}", "user": {"id": data.get("id"), "name": data.get("name") or data.get("username")}}
        except Exception as error:
            return {"ok": False, "message": f"{type(error).__name__}: {error}"}

    def public_status(self):
        self.reload_config()
        self._load_tokens()
        result = dict(self.status)
        result["librariesOk"] = self.libraries_ok()
        result["authorizeUrl"] = "/auth/donationalerts/start"
        result["last_error"] = result.get("lastError")
        result["last_event"] = result.get("lastEvent")
        return result
