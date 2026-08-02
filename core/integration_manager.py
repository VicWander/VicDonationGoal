from __future__ import annotations

import json
import os
import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORT))
from safe_json import load_json as _robust_load_json, save_json as _robust_save_json
from source_registry import source_meta


PLACEHOLDER_MARKERS = ("ВСТАВЬ", "PASTE_", "CHANGE_ME")


def _load_json(path: Path, fallback):
    return _robust_load_json(path, fallback, retries=12)


def _save_json(path: Path, data):
    _robust_save_json(path, data, retries=80)


def _redact_value(text, secrets=()):
    value = str(text or "")
    value = re.sub(r"(?i)(access_token|refresh_token|token|jwt|api[_-]?key|client_secret|secret)=([^&\s]+)", r"\1=***", value)
    for secret in secrets:
        secret_text = str(secret or "")
        if len(secret_text) >= 8:
            value = value.replace(secret_text, "***")
    return value


class _WindowsKillOnCloseJob:
    """Put hidden integration subprocesses into a Windows Job Object.

    When the Core console is closed with the X button, Python does not always run
    `atexit`. The Job Object guarantees that all hidden integration processes are
    terminated by Windows when the Core process disappears, releasing log files.
    """
    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                return
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                kernel32.CloseHandle(handle)
                return
            self.handle = handle
            self._kernel32 = kernel32
        except Exception:
            self.handle = None

    def assign(self, process):
        if not self.handle or os.name != "nt":
            return False
        try:
            return bool(self._kernel32.AssignProcessToJobObject(self.handle, int(process._handle)))
        except Exception:
            return False

    def close(self):
        if self.handle:
            try:
                self._kernel32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None


def _is_placeholder(value) -> bool:
    text = str(value or "").strip()
    return not text or any(marker in text for marker in PLACEHOLDER_MARKERS)


class IntegrationManager:
    """Registry and runtime manager for VicDonationGoal integrations.

    v1.4.0 intentionally keeps the contract small: each integration has a manifest,
    a local config file and either an in-process adapter or a Python entrypoint.
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.integrations_dir = self.project_root / "integrations"
        self.runtime_dir = self.project_root / "runtime" / "integrations"
        self.onboarding_file = self.integrations_dir / "integrations_onboarding.json"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._adapters = {}
        self._processes = {}
        self._log_handles = {}
        self._manifests = {}
        self._child_job = _WindowsKillOnCloseJob()
        self._pid_file = self.project_root / "runtime" / "integration_processes.json"
        self.reload_manifests()
        self.ensure_files()

    def _write_pid_registry(self):
        processes = {}
        for integration_id, process in list(self._processes.items()):
            if process is not None and process.poll() is None:
                processes[integration_id] = {"pid": process.pid, "updatedAt": time.time()}
        _save_json(self._pid_file, {"corePid": os.getpid(), "processes": processes, "updatedAt": time.time()})

    def _secret_values(self, integration_id):
        manifest = self._manifest(integration_id)
        config = self._load_config(integration_id)
        return [config.get(key) for key in manifest.get("secretFields") or []]

    def register_adapter(self, integration_id: str, adapter):
        self._adapters[str(integration_id)] = adapter

    def reload_manifests(self):
        manifests = {}
        if self.integrations_dir.exists():
            for path in sorted(self.integrations_dir.glob("*/manifest.json")):
                data = _load_json(path, {})
                integration_id = str(data.get("id") or path.parent.name).strip()
                if not integration_id:
                    continue
                data["id"] = integration_id
                data["directory"] = str(path.parent)
                manifests[integration_id] = data
        self._manifests = manifests
        return manifests

    def ensure_files(self):
        if not self.onboarding_file.exists():
            configured = []
            for integration_id, manifest in self._manifests.items():
                config = self._load_config(integration_id)
                if self._configured(manifest, config):
                    configured.append(integration_id)
            # Existing private builds should not be interrupted by a wizard.
            completed = bool(configured)
            _save_json(self.onboarding_file, {
                "completed": completed,
                "selected": configured,
                "updatedAt": time.time(),
            })

    def manifests(self):
        return dict(self._manifests)

    def _manifest(self, integration_id: str):
        integration_id = str(integration_id or "")
        manifest = self._manifests.get(integration_id)
        if not manifest:
            raise KeyError(f"Неизвестная интеграция: {integration_id}")
        return manifest

    def _integration_dir(self, manifest):
        return Path(manifest["directory"])

    def _config_path(self, manifest):
        filename = str(manifest.get("configFile") or "config.json")
        return self._integration_dir(manifest) / filename

    def _example_path(self, manifest):
        filename = str(manifest.get("configExampleFile") or "")
        return self._integration_dir(manifest) / filename if filename else None

    def _status_path(self, manifest):
        value = str(manifest.get("statusFile") or "")
        if not value:
            return None
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path

    def _guide_path(self, manifest):
        filename = str(manifest.get("guideFile") or "GUIDE.md")
        return self._integration_dir(manifest) / filename

    def _log_path(self, integration_id):
        return self.runtime_dir / f"{integration_id}.log"

    def _load_config(self, integration_id):
        manifest = self._manifest(integration_id)
        config_path = self._config_path(manifest)
        if not config_path.exists():
            example_path = self._example_path(manifest)
            if example_path and example_path.exists():
                config_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                _save_json(config_path, {"enabled": False})
        data = _load_json(config_path, {})
        return data if isinstance(data, dict) else {}

    def _save_config(self, integration_id, config):
        manifest = self._manifest(integration_id)
        _save_json(self._config_path(manifest), config)

    def _configured(self, manifest, config):
        required = manifest.get("requiredFields") or []
        for key in required:
            if _is_placeholder(config.get(key)):
                return False
        return True

    def _public_config(self, manifest, config):
        secret_fields = set(manifest.get("secretFields") or [])
        result = {}
        for field in manifest.get("fields") or []:
            key = str(field.get("key") or "")
            if not key:
                continue
            if key in secret_fields:
                result[key] = "__SET__" if not _is_placeholder(config.get(key)) else ""
            else:
                result[key] = config.get(key, field.get("default"))
        result["enabled"] = bool(config.get("enabled", False))
        return result

    def _read_status_file(self, manifest):
        path = self._status_path(manifest)
        if not path:
            return {}
        data = _load_json(path, {})
        if not isinstance(data, dict):
            return {}
        updated_at = float(data.get("updatedAt") or 0)
        age = max(0.0, time.time() - updated_at) if updated_at else None
        data["ageSeconds"] = round(age, 1) if age is not None else None
        data["stale"] = bool(age is None or age > float(manifest.get("statusStaleSeconds") or 120))
        return data

    def _process(self, integration_id):
        process = self._processes.get(integration_id)
        if process is not None and process.poll() is not None:
            self._processes.pop(integration_id, None)
            handle = self._log_handles.pop(integration_id, None)
            if handle:
                try:
                    handle.close()
                except Exception:
                    pass
            process = None
            try:
                self._write_pid_registry()
            except Exception:
                pass
        return process

    def integration_status(self, integration_id):
        manifest = self._manifest(integration_id)
        adapter = self._adapters.get(integration_id)
        if adapter is not None:
            status = adapter.public_status()
        else:
            status = self._read_status_file(manifest)
        process = self._process(integration_id)
        if manifest.get("kind") == "subprocess":
            status = dict(status or {})
            status["processRunning"] = bool(process)
            status["pid"] = process.pid if process else None
            if process and not status.get("running"):
                status["running"] = True
        return status or {}

    def _common_state(self, enabled, configured, running, connected, status):
        status = status if isinstance(status, dict) else {}
        raw = str(status.get("status") or "").strip().lower()
        stale = bool(status.get("stale"))
        last_error = status.get("lastError") or status.get("last_error")
        degraded_states = {"degraded", "polling_degraded", "reconnecting", "retry", "rate_limited"}
        starting_states = {"starting", "connecting", "connecting_sse", "capturing_sse", "authorizing"}
        if not enabled:
            return "disabled"
        if not configured:
            return "unconfigured"
        if connected and not stale:
            return "degraded" if (last_error or raw in degraded_states) else "connected"
        if raw in starting_states or (running and not last_error and not stale):
            return "starting"
        if last_error:
            return "error"
        if stale and running:
            return "degraded"
        if running:
            return "starting"
        return "stopped"

    def _summary(self, integration_id):
        manifest = self._manifest(integration_id)
        config = self._load_config(integration_id)
        status = self.integration_status(integration_id)
        secrets = [config.get(key) for key in manifest.get("secretFields") or []]
        public_status_fields = set(manifest.get("publicStatusFields") or [])
        if isinstance(status, dict):
            status = {
                key: (value if key in public_status_fields else _redact_value(value, secrets))
                if isinstance(value, str) else value
                for key, value in status.items()
            }
        enabled = bool(config.get("enabled", False))
        configured = self._configured(manifest, config)
        connected = bool(status.get("connected")) if enabled else False
        running = bool(status.get("running") or status.get("processRunning")) if enabled else False
        common_state = self._common_state(enabled, configured, running, connected, status)
        # Keep state for backward compatibility with the detailed Integration Hub.
        state = common_state
        meta = source_meta(integration_id)
        return {
            "id": integration_id,
            "name": manifest.get("name", integration_id),
            "shortName": manifest.get("shortName", manifest.get("name", integration_id)),
            "description": manifest.get("description", ""),
            "icon": manifest.get("icon", integration_id[:2].upper()),
            "order": int(manifest.get("order") or 100),
            "kind": manifest.get("kind", "subprocess"),
            "enabled": enabled,
            "configured": configured,
            "running": running,
            "connected": connected,
            "state": state,
            "commonState": common_state,
            "stability": manifest.get("stability") or meta.get("stability") or "unknown",
            "dashboardVisible": bool(manifest.get("dashboardVisible", True)),
            "status": status,
            "capabilities": manifest.get("capabilities") or {},
        }

    def bootstrap(self):
        integrations = sorted((self._summary(i) for i in self._manifests), key=lambda item: (item["order"], item["name"]))
        onboarding = _load_json(self.onboarding_file, {"completed": False, "selected": []})
        if not isinstance(onboarding, dict):
            onboarding = {"completed": False, "selected": []}
        return {
            "ok": True,
            "integrations": integrations,
            "onboarding": onboarding,
        }

    def detail(self, integration_id):
        manifest = self._manifest(integration_id)
        config = self._load_config(integration_id)
        guide_path = self._guide_path(manifest)
        return {
            "ok": True,
            "manifest": {key: value for key, value in manifest.items() if key != "directory"},
            "summary": self._summary(integration_id),
            "config": self._public_config(manifest, config),
            "guide": guide_path.read_text(encoding="utf-8") if guide_path.exists() else "Инструкция пока не добавлена.",
        }

    def save_config(self, integration_id, patch):
        manifest = self._manifest(integration_id)
        config = self._load_config(integration_id)
        secret_fields = set(manifest.get("secretFields") or [])
        allowed = {str(field.get("key")) for field in manifest.get("fields") or [] if field.get("key")}
        allowed.add("enabled")
        for key, value in (patch or {}).items():
            if key not in allowed:
                continue
            if key in secret_fields and value in (None, "", "__SET__", "__KEEP__"):
                continue
            config[key] = value
        self._save_config(integration_id, config)
        adapter = self._adapters.get(integration_id)
        if adapter is not None:
            adapter.reload_config()
        return self.detail(integration_id)

    def set_enabled(self, integration_id, enabled):
        config = self._load_config(integration_id)
        config["enabled"] = bool(enabled)
        self._save_config(integration_id, config)
        if enabled:
            return self.start(integration_id)
        return self.stop(integration_id)

    def start(self, integration_id):
        manifest = self._manifest(integration_id)
        config = self._load_config(integration_id)
        if not bool(config.get("enabled", False)):
            return {"ok": False, "message": "Интеграция выключена", "detail": self.detail(integration_id)}
        if not self._configured(manifest, config):
            return {"ok": False, "message": "Сначала заполните обязательные настройки", "detail": self.detail(integration_id)}
        adapter = self._adapters.get(integration_id)
        if adapter is not None:
            adapter.start()
            return {"ok": True, "message": "Интеграция запущена", "detail": self.detail(integration_id)}
        if manifest.get("kind") != "subprocess":
            return {"ok": False, "message": "Для интеграции не зарегистрирован runtime adapter"}
        with self._lock:
            process = self._process(integration_id)
            if process:
                return {"ok": True, "message": "Интеграция уже запущена", "detail": self.detail(integration_id)}
            entrypoint = self._integration_dir(manifest) / str(manifest.get("entrypoint") or "")
            if not entrypoint.exists():
                return {"ok": False, "message": f"Не найден entrypoint: {entrypoint.name}"}
            log_path = self._log_path(integration_id)
            log_handle = log_path.open("a", encoding="utf-8", buffering=1)
            log_handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] START {integration_id}\n")
            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            process = subprocess.Popen(
                [sys.executable, str(entrypoint)],
                cwd=str(entrypoint.parent),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=flags,
            )
            self._processes[integration_id] = process
            self._log_handles[integration_id] = log_handle
            self._child_job.assign(process)
            self._write_pid_registry()
        return {"ok": True, "message": "Интеграция запущена", "detail": self.detail(integration_id)}

    def stop(self, integration_id):
        manifest = self._manifest(integration_id)
        adapter = self._adapters.get(integration_id)
        if adapter is not None:
            adapter.stop()
            return {"ok": True, "message": "Интеграция остановлена", "detail": self.detail(integration_id)}
        with self._lock:
            process = self._process(integration_id)
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
                self._processes.pop(integration_id, None)
                handle = self._log_handles.pop(integration_id, None)
                if handle:
                    try:
                        handle.close()
                    except Exception:
                        pass
                self._write_pid_registry()
        status_path = self._status_path(manifest)
        if status_path:
            status = self._read_status_file(manifest)
            status.update({"running": False, "connected": False, "status": "stopped", "updatedAt": time.time()})
            status.pop("ageSeconds", None)
            status.pop("stale", None)
            _save_json(status_path, status)
        return {"ok": True, "message": "Интеграция остановлена", "detail": self.detail(integration_id)}

    def restart(self, integration_id):
        self.stop(integration_id)
        time.sleep(0.25)
        return self.start(integration_id)

    def _test_tribute_webhook(self, config, status):
        public_url = str(status.get("publicWebhookUrl") or "").strip()
        api_key = str(config.get("api_key") or "").strip()
        if not public_url:
            return {"ok": False, "message": "Cloudflare Tunnel подключён, но publicWebhookUrl ещё не получен", "status": status}
        if not api_key:
            return {"ok": False, "message": "Не задан API-ключ Tribute", "status": status}

        stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload = {
            "name": "vicdonationgoal_test",
            "created_at": stamp,
            "sent_at": stamp,
            "payload": {"probe_id": str(uuid.uuid4())},
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(api_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
        request = Request(
            public_url, data=body, method="POST",
            headers={"Content-Type": "application/json", "trbt-signature": signature},
        )
        try:
            with urlopen(request, timeout=25) as response:
                response_body = response.read(2048).decode("utf-8", errors="replace")
                if 200 <= response.status < 300:
                    return {
                        "ok": True,
                        "message": "Публичный Tribute webhook доступен: туннель, подпись и Core работают",
                        "status": self.integration_status("tribute"),
                        "httpStatus": response.status,
                        "response": response_body,
                    }
                return {"ok": False, "message": f"Tribute self-test HTTP {response.status}: {response_body}", "status": status}
        except HTTPError as error:
            body_text = error.read(2048).decode("utf-8", errors="replace")
            return {"ok": False, "message": f"Tribute self-test HTTP {error.code}: {body_text}", "status": self.integration_status("tribute")}
        except (URLError, TimeoutError, OSError) as error:
            return {"ok": False, "message": f"Публичный Tribute webhook недоступен: {type(error).__name__}: {error}", "status": self.integration_status("tribute")}

    def test(self, integration_id):
        manifest = self._manifest(integration_id)
        adapter = self._adapters.get(integration_id)
        if adapter is not None:
            return adapter.test_connection()
        config = self._load_config(integration_id)
        if not self._configured(manifest, config):
            return {"ok": False, "message": "Не заполнены обязательные настройки"}
        result = self.start(integration_id)
        if not result.get("ok"):
            return result
        deadline = time.time() + float(manifest.get("testWaitSeconds") or 5)
        while time.time() < deadline:
            status = self.integration_status(integration_id)
            if status.get("connected"):
                if integration_id == "tribute":
                    return self._test_tribute_webhook(config, status)
                return {"ok": True, "message": "Подключение работает", "status": status}
            if status.get("lastError"):
                return {"ok": False, "message": str(status.get("lastError")), "status": status}
            time.sleep(0.5)
        return {"ok": True, "message": "Модуль запущен; подключение ещё устанавливается", "status": self.integration_status(integration_id)}

    def clear_auth(self, integration_id):
        adapter = self._adapters.get(integration_id)
        if adapter is not None and hasattr(adapter, "clear_auth"):
            adapter.clear_auth()
            return {"ok": True, "message": "Данные авторизации удалены", "detail": self.detail(integration_id)}
        return {"ok": False, "message": "Эта интеграция не использует отдельную авторизацию"}

    def logs(self, integration_id, limit=250):
        adapter = self._adapters.get(integration_id)
        if adapter is not None and hasattr(adapter, "logs"):
            lines = adapter.logs(limit)
        else:
            path = self._log_path(integration_id)
            if not path.exists():
                lines = []
            else:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, int(limit)):]
        secrets = self._secret_values(integration_id)
        lines = [_redact_value(line, secrets) for line in lines]
        return {"ok": True, "lines": lines}

    def save_onboarding(self, payload):
        selected = [str(item) for item in payload.get("selected", []) if str(item) in self._manifests]
        completed = bool(payload.get("completed", True))
        _save_json(self.onboarding_file, {
            "completed": completed,
            "selected": selected,
            "updatedAt": time.time(),
        })
        for integration_id in self._manifests:
            config = self._load_config(integration_id)
            should_enable = integration_id in selected
            config["enabled"] = should_enable
            self._save_config(integration_id, config)
            if not should_enable:
                self.stop(integration_id)
        if completed:
            self.start_enabled()
        return self.bootstrap()

    def start_enabled(self):
        results = []
        for integration_id in sorted(self._manifests, key=lambda item: int(self._manifests[item].get("order") or 100)):
            config = self._load_config(integration_id)
            if bool(config.get("enabled", False)) and self._configured(self._manifests[integration_id], config):
                results.append(self.start(integration_id))
        return results

    def stop_all(self):
        for integration_id in list(self._manifests):
            try:
                self.stop(integration_id)
            except Exception:
                pass
        try:
            self._write_pid_registry()
        except Exception:
            pass
