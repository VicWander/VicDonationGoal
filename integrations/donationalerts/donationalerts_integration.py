from __future__ import annotations

import json
import os
import secrets
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlencode, urlparse, unquote
from urllib.request import getproxies, proxy_bypass

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
DA_CATCH_UP_SCHEMA_VERSION = 1
DA_CATCH_UP_MAX_PAGES = 5
DA_LONG_OUTAGE_SECONDS = 300


class DonationAlertsIntegration:
    def __init__(self, project_root: Path, add_donation, load_json, save_json):
        self.project_root = Path(project_root)
        self.directory = self.project_root / "integrations" / "donationalerts"
        self.config_file = self.directory / "donationalerts_config.json"
        self.tokens_file = self.directory / "donationalerts_tokens.json"
        self.catch_up_file = self.directory / "donationalerts_catch_up_state.json"
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
            "status": "stopped",
            "channel": None,
            "lastError": None,
            "lastWarning": None,
            "lastEvent": None,
            "lastApiSuccessAt": None,
            "lastConnectedAt": None,
            "lastDisconnectedAt": None,
            "lastHeartbeatAt": None,
            "consecutiveFailures": 0,
            "nextRetryAt": None,
            "catchUp": {"status": "not_initialized", "added": 0},
            "updatedAt": time.time(),
        }
        self._logs = []
        self._lock = threading.RLock()
        self._thread = None
        self._ws = None
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

    @staticmethod
    def _now_text():
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _update_status(self, **fields):
        with self._lock:
            self.status.update(fields)
            self._write_status()

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
        self._update_status(
            authorized=False,
            connected=False,
            running=False,
            status="authorization_required",
            lastError=None,
        )

    def libraries_ok(self):
        return requests is not None and websocket is not None

    def _http_request(self, method, url, **kwargs):
        # A browser's Windows proxy can be unavailable or unsuitable for donation
        # services. Keep the integration's route explicit, including OAuth refresh.
        with requests.Session() as session:
            session.trust_env = bool(self.config().get("use_system_proxy", False))
            return session.request(method, url, **kwargs)

    def _websocket_options(self, config):
        if not config.get("use_system_proxy", False):
            return {"http_no_proxy": ["*"]}
        host = urlparse(DA_WS_URL).hostname
        if proxy_bypass(host):
            return {"http_no_proxy": ["*"]}
        proxies = getproxies()
        proxy = proxies.get("https") or proxies.get("all")
        if not proxy:
            return {}
        parsed = urlparse(proxy if "://" in proxy else "http://" + proxy)
        options = {
            "http_proxy_host": parsed.hostname,
            "http_proxy_port": parsed.port or 80,
            "proxy_type": parsed.scheme,
        }
        if parsed.username is not None:
            options["http_proxy_auth"] = (unquote(parsed.username), unquote(parsed.password or ""))
        return options

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
            self._update_status(
                status="authorization_required",
                lastError="Access token истёк, refresh_token отсутствует",
            )
            return None
        if requests is None:
            self._update_status(status="error", lastError="Не установлена библиотека requests")
            return None
        try:
            response = self._http_request("POST", DA_TOKEN_URL, data={
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
            self._update_status(
                status="authorization_required",
                lastError=f"Не удалось обновить токен: {type(error).__name__}: {error}",
            )
            return None

    def api_request(self, method, endpoint, json_data=None):
        if requests is None:
            raise RuntimeError("Не установлена библиотека requests")
        token = self._valid_access_token()
        if not token:
            raise RuntimeError("DonationAlerts не авторизован")
        response = self._http_request(
            method,
            DA_API_BASE + endpoint,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json=json_data,
            timeout=20,
        )
        if response.status_code == 401:
            self.clear_auth()
            self._update_status(
                status="authorization_required",
                lastError="DonationAlerts вернул 401; нужна повторная авторизация",
            )
            raise RuntimeError("DonationAlerts вернул 401; нужна повторная авторизация")
        response.raise_for_status()
        result = response.json() if response.text else {}
        self._update_status(lastApiSuccessAt=self._now_text())
        return result

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
        response = self._http_request("POST", DA_TOKEN_URL, data={
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
    def donation_from_payload(donation):
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

    @classmethod
    def extract_donation(cls, message):
        try:
            data = message if isinstance(message, dict) else json.loads(message)
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
        return cls.donation_from_payload(donation)

    def _load_catch_up_state(self):
        state = self.load_json(self.catch_up_file, {})
        return state if isinstance(state, dict) else {}

    def _save_catch_up_state(self, state):
        payload = dict(state or {})
        payload["schemaVersion"] = DA_CATCH_UP_SCHEMA_VERSION
        payload["updatedAt"] = self._now_text()
        self.save_json(self.catch_up_file, payload)
        return payload

    def _latest_local_donation(self):
        donations = self.load_json(self.project_root / "core" / "data" / "donations.json", [])
        if not isinstance(donations, list):
            return None
        for item in reversed(donations):
            if not isinstance(item, dict) or str(item.get("source") or "").lower() != "donationalerts":
                continue
            external_id = item.get("externalId") or item.get("external_id")
            if external_id is not None:
                return {
                    "externalId": str(external_id),
                    "createdAt": str(item.get("createdAt") or item.get("created_at") or ""),
                }
        return None

    def _remember_checkpoint(self, donation, source="live"):
        external_id = donation.get("externalId") if isinstance(donation, dict) else None
        if external_id is None:
            return
        state = self._load_catch_up_state()
        state.update({
            "lastSeenId": str(external_id),
            "lastSeenCreatedAt": str(donation.get("createdAt") or ""),
            "lastSeenSource": source,
        })
        self._save_catch_up_state(state)

    def _fetch_recent_donations(self, checkpoint_id=None, checkpoint_created_at=""):
        rows = []
        found_checkpoint = False
        for page in range(1, DA_CATCH_UP_MAX_PAGES + 1):
            payload = self.api_request("GET", f"/alerts/donations?page={page}")
            data = payload.get("data") or []
            if not isinstance(data, list):
                raise RuntimeError("DonationAlerts вернул неожиданный формат списка донатов")
            for raw in data:
                donation = self.donation_from_payload(raw)
                if not donation:
                    continue
                if checkpoint_id and str(donation.get("externalId")) == str(checkpoint_id):
                    found_checkpoint = True
                    break
                if checkpoint_created_at and str(donation.get("createdAt") or "") <= checkpoint_created_at:
                    continue
                rows.append(donation)
            if found_checkpoint or not (payload.get("links") or {}).get("next"):
                break
            # DonationAlerts limits HTTP API calls to one request per second.
            if not self._stop.wait(1.05):
                continue
            break
        return rows, found_checkpoint

    def _catch_up_after_connect(self):
        state = self._load_catch_up_state()
        checkpoint_id = str(state.get("lastSeenId") or "").strip()
        checkpoint_created_at = str(state.get("lastSeenCreatedAt") or "").strip()
        initialized_from = "checkpoint"

        if not checkpoint_id:
            local = self._latest_local_donation()
            if local:
                checkpoint_id = local["externalId"]
                checkpoint_created_at = local.get("createdAt") or ""
                initialized_from = "local_history"
            else:
                initialized_from = "remote_baseline"

        rows, found_checkpoint = self._fetch_recent_donations(checkpoint_id, checkpoint_created_at)
        newest = rows[0] if rows else None

        if not checkpoint_id:
            if newest:
                self._remember_checkpoint(newest, "remote_baseline")
            report = {
                "status": "baseline_created",
                "added": 0,
                "checked": len(rows),
                "initializedFrom": initialized_from,
                "at": self._now_text(),
            }
            self._update_status(catchUp=report)
            self._log("Догон истории: создана безопасная стартовая точка без импорта старых донатов")
            return True

        if initialized_from == "local_history" and not found_checkpoint:
            # Never turn the first launch after an upgrade into a bulk historical import.
            if newest:
                self._remember_checkpoint(newest, "remote_baseline_after_local_miss")
            report = {
                "status": "baseline_reset",
                "added": 0,
                "checked": len(rows),
                "checkpointFound": False,
                "initializedFrom": initialized_from,
                "at": self._now_text(),
            }
            self._update_status(catchUp=report)
            self._log("Догон истории: локальная точка слишком старая; создана новая без массового импорта", "WARN")
            return True

        added = 0
        duplicates = 0
        for donation in reversed(rows):
            _state, ok, _message = self.add_donation(donation)
            if ok:
                added += 1
            else:
                duplicates += 1

        if newest:
            self._remember_checkpoint(newest, "catch_up")
        elif not state.get("lastSeenId"):
            self._save_catch_up_state({
                "lastSeenId": checkpoint_id,
                "lastSeenCreatedAt": checkpoint_created_at,
                "lastSeenSource": initialized_from,
            })

        report = {
            "status": "complete" if found_checkpoint or not rows else "limited_window",
            "added": added,
            "duplicates": duplicates,
            "checked": len(rows),
            "checkpointFound": found_checkpoint,
            "initializedFrom": initialized_from,
            "at": self._now_text(),
        }
        self._update_status(catchUp=report)
        self._log(f"Догон истории завершён: добавлено {added}, дублей {duplicates}")
        return True

    @staticmethod
    def _is_transient_error(error):
        if requests is not None:
            if isinstance(error, (requests.Timeout, requests.ConnectionError)):
                return True
            if isinstance(error, requests.HTTPError):
                code = int(getattr(getattr(error, "response", None), "status_code", 0) or 0)
                return code in {408, 425, 429} or code >= 500
        if websocket is not None:
            transient_types = tuple(
                item for item in (
                    getattr(websocket, "WebSocketConnectionClosedException", None),
                    getattr(websocket, "WebSocketTimeoutException", None),
                    getattr(websocket, "WebSocketBadStatusException", None),
                ) if isinstance(item, type)
            )
            if transient_types and isinstance(error, transient_types):
                return True
        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return True
        text = str(error).lower()
        return any(marker in text for marker in (
            "502", "503", "504", "timeout", "timed out", "connection reset",
            "connection closed", "ssl", "eof", "centrifugo", "subscription token",
        ))

    @staticmethod
    def _read_ws_message(ws, pending):
        while not pending:
            raw = ws.recv()
            if not raw:
                raise ConnectionError("Centrifugo закрыл соединение")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            # Centrifugo batches independent JSON replies with newline separators.
            try:
                for line in raw.splitlines():
                    if line.strip():
                        item = json.loads(line)
                        if not isinstance(item, dict):
                            raise ValueError("reply is not an object")
                        pending.append(item)
            except (ValueError, UnicodeError) as error:
                raise ConnectionError("Centrifugo прислал некорректный пакет") from error
        return pending.popleft()

    def _handle_ws_ping(self, ws, message):
        if message:
            return False
        ws.send("{}")
        self._update_status(lastHeartbeatAt=self._now_text())
        return True

    def _wait_for_ws_reply(self, ws, reply_id, pending, deferred):
        deadline = time.monotonic() + 45
        while not self._stop.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError("Centrifugo не подтвердил команду")
            ws.settimeout(max(0.1, deadline - time.monotonic()))
            item = self._read_ws_message(ws, pending)
            if self._handle_ws_ping(ws, item):
                continue
            if item.get("id") != reply_id:
                deferred.append(item)
                continue
            if item.get("error"):
                error = item["error"]
                code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
                raise RuntimeError(f"Centrifugo отклонил команду {reply_id}, код {code}")
            result = item.get("result")
            if not isinstance(result, dict):
                raise ConnectionError("Centrifugo прислал ответ без result")
            return result
        raise ConnectionError("Centrifugo: подключение остановлено")

    def _listener_loop(self):
        reconnect_delay = 5
        first_failure_at = None
        self._update_status(running=True, status="starting", lastError=None, nextRetryAt=None)
        while not self._stop.is_set():
            ws = None
            try:
                config = self.reload_config()
                if not bool(config.get("enabled", False)):
                    self._update_status(running=False, connected=False, status="stopped", lastError=None)
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
                self._update_status(channel=channel_name, status="connecting")
                self._log(f"Подключение к {DA_WS_URL}")
                route = self._websocket_options(config)
                ws = websocket.create_connection(DA_WS_URL, timeout=45, **route)
                self._ws = ws
                pending = deque()
                deferred = deque()
                ws.send(json.dumps({"params": {"token": socket_token}, "id": 1}))
                auth_response = self._wait_for_ws_reply(ws, 1, pending, deferred)
                centrifugo_client = auth_response.get("client")
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
                self._wait_for_ws_reply(ws, 2, pending, deferred)
                connected_at = self._now_text()
                self._update_status(
                    connected=True,
                    running=True,
                    status="connected",
                    lastError=None,
                    lastWarning=None,
                    lastConnectedAt=connected_at,
                    consecutiveFailures=0,
                    nextRetryAt=None,
                )
                self._log(f"Подключено; канал {channel_name}")
                try:
                    catch_up_ok = self._catch_up_after_connect()
                    if not catch_up_ok:
                        self._update_status(status="degraded")
                except Exception as catch_up_error:
                    warning = f"Догон истории временно не выполнен: {type(catch_up_error).__name__}: {catch_up_error}"
                    self._update_status(status="degraded", lastWarning=warning)
                    self._log(warning, "WARN")
                ws.settimeout(90)
                reconnect_delay = 5
                first_failure_at = None
                while not self._stop.is_set():
                    item = deferred.popleft() if deferred else self._read_ws_message(ws, pending)
                    if self._handle_ws_ping(ws, item):
                        continue
                    donation = self.extract_donation(item)
                    if not donation:
                        continue
                    state, ok, message = self.add_donation(donation)
                    event_at = self._now_text()
                    self._remember_checkpoint(donation, "live")
                    self._update_status(status="connected", lastError=None, lastEventAt=event_at, lastEvent={
                        "ok": ok,
                        "message": message,
                        "donation": donation,
                        "time": event_at,
                    })
                    self._log(f"Донат: {donation['username']} — {donation['amount']} {donation['currency']} | {message}")
            except Exception as error:
                if self._stop.is_set():
                    break
                error_text = f"{type(error).__name__}: {error}"
                transient = self._is_transient_error(error)
                now = time.time()
                first_failure_at = first_failure_at or now
                failures = int(self.status.get("consecutiveFailures") or 0) + 1
                long_outage = transient and now - first_failure_at >= DA_LONG_OUTAGE_SECONDS
                if transient and not long_outage:
                    self._update_status(
                        connected=False,
                        running=True,
                        status="reconnecting",
                        lastError=None,
                        lastWarning=error_text,
                        lastDisconnectedAt=self._now_text(),
                        consecutiveFailures=failures,
                        nextRetryAt=now + reconnect_delay,
                    )
                    self._log(f"Связь временно потеряна; повтор через {reconnect_delay} сек. {error_text}", "WARN")
                else:
                    self._update_status(
                        connected=False,
                        running=transient,
                        status="outage" if long_outage else "error",
                        lastError=error_text,
                        lastWarning=error_text if transient else self.status.get("lastWarning"),
                        lastDisconnectedAt=self._now_text(),
                        consecutiveFailures=failures,
                        nextRetryAt=(now + reconnect_delay) if transient else None,
                    )
                    self._log(error_text, "ERROR")
                try:
                    if ws:
                        ws.close()
                except Exception:
                    pass
                self._ws = None
                if not transient:
                    return
                if not self._stop.wait(reconnect_delay):
                    reconnect_delay = min(reconnect_delay * 2, 60)
        final_status = self.status.get("status") if self.status.get("lastError") else "stopped"
        self._update_status(running=False, connected=False, status=final_status, nextRetryAt=None)

    def start(self):
        if self._thread and self._thread.is_alive():
            if not self._stop.is_set():
                return
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                self._update_status(
                    status="reconnecting",
                    lastWarning="Предыдущий WebSocket ещё завершается; повторите запуск через несколько секунд",
                )
                return
        if not self.libraries_ok():
            self._update_status(status="error", lastError="Не установлены requests/websocket-client")
            return
        self._stop.clear()
        self._update_status(running=True, connected=False, status="starting", lastError=None)
        self._thread = threading.Thread(target=self._listener_loop, daemon=True, name="DonationAlertsIntegration")
        self._thread.start()

    def stop(self):
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        self._ws = None
        self._update_status(running=False, connected=False, status="stopped", lastError=None, nextRetryAt=None)

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
            live_state = str(self.status.get("status") or "stopped")
            if self.status.get("connected"):
                message = "Авторизация и API работают. Получение новых донатов подключено."
                level = "success"
            elif self.status.get("running"):
                message = "Авторизация и API работают. Канал новых донатов сейчас переподключается автоматически."
                level = "warning"
            else:
                message = "Авторизация и API работают. Модуль новых донатов сейчас не запущен."
                level = "warning"
            return {
                "ok": True,
                "level": level,
                "message": message,
                "checks": {"api": "ok", "realtime": "ok" if self.status.get("connected") else live_state},
                "user": {"id": data.get("id"), "name": data.get("name") or data.get("username")},
            }
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
