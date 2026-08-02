from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.base.common import StatusWriter, load_json
from tools.install_cloudflared import install as install_cloudflared

try:
    import requests
except ImportError:
    requests = None

CONFIG_FILE = ROOT / "tribute_config.json"
STATUS_FILE = PROJECT_ROOT / "runtime/integrations/tribute_status.json"
STATUS = StatusWriter(
    STATUS_FILE,
    "tribute",
    publicWebhookUrl=None,
    tunnelUrl=None,
    cloudflaredPath=None,
)


def log(message: str, level: str = "INFO") -> None:
    print(f"[Tribute] {level} {message}", flush=True)


def resolve_path(value: Any) -> Path:
    path = Path(str(value or "tools/cloudflared.exe").strip())
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def wait_for_core(local_url: str, timeout_seconds: int = 20) -> None:
    if requests is None:
        return
    deadline = time.time() + timeout_seconds
    health_url = local_url.rstrip("/") + "/api/health"
    last_error: BaseException | None = None
    while time.time() < deadline:
        try:
            response = requests.get(health_url, timeout=2)
            if response.ok:
                return
        except Exception as error:
            last_error = error
        time.sleep(0.5)
    raise RuntimeError(f"Core Server не отвечает: {last_error or health_url}")


def main() -> None:
    cfg = load_json(CONFIG_FILE, {})
    if not cfg.get("enabled"):
        raise SystemExit("Tribute выключен")

    secret = str(cfg.get("webhook_secret") or "").strip()
    if not secret:
        raise SystemExit("Не задан webhook_secret")

    local_url = str(cfg.get("local_url") or "http://127.0.0.1:3333").rstrip("/")
    wait_for_core(local_url)

    public = str(cfg.get("public_base_url") or "").rstrip("/")
    if public:
        webhook_url = f"{public}/api/integrations/tribute/webhook/{secret}"
        STATUS.update(
            running=True,
            connected=True,
            status="ready_external",
            tunnelUrl=public,
            publicWebhookUrl=webhook_url,
            lastError=None,
        )
        log(f"Webhook URL: {webhook_url}")
        while True:
            time.sleep(30)

    if not cfg.get("auto_start_tunnel", True):
        raise SystemExit("Укажите public_base_url или включите auto_start_tunnel")

    executable = resolve_path(cfg.get("cloudflared_path"))
    STATUS.update(cloudflaredPath=str(executable))
    if not executable.exists():
        if cfg.get("auto_install_cloudflared", True):
            STATUS.update(status="installing_cloudflared", lastError=None)
            log("cloudflared не найден — скачиваю автоматически...")
            executable = install_cloudflared()
            STATUS.update(cloudflaredPath=str(executable), status="cloudflared_installed")
        else:
            raise SystemExit(
                f"Не найден cloudflared: {executable}. "
                "Запустите 12_INSTALL_CLOUDFLARED.bat"
            )

    protocol = str(cfg.get("tunnel_protocol") or "http2").strip().lower()
    if protocol not in {"auto", "http2", "quic"}:
        protocol = "http2"
    command = [
        str(executable),
        "tunnel",
        "--no-autoupdate",
        "--protocol",
        protocol,
        "--url",
        local_url,
    ]
    STATUS.update(
        running=True,
        connected=False,
        status="starting_tunnel",
        lastError=None,
        publicWebhookUrl=None,
        tunnelUrl=None,
    )
    log(f"Запускаю Cloudflare Quick Tunnel ({protocol}) → {local_url}")

    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )

    found_url = False
    started_at = time.time()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip()
            if line:
                print(line, flush=True)
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line, re.I)
            if match:
                found_url = True
                public = match.group(0).rstrip("/")
                webhook_url = f"{public}/api/integrations/tribute/webhook/{secret}"
                STATUS.update(
                    connected=False,
                    status="tunnel_url_ready",
                    tunnelUrl=public,
                    publicWebhookUrl=webhook_url,
                    lastError=None,
                )
                log(f"Webhook URL: {webhook_url}")

            lower_line = line.lower()
            if "registered tunnel connection" in lower_line:
                STATUS.update(connected=True, status="ready", lastError=None)
            elif any(marker in lower_line for marker in (
                "failed to dial",
                "serve tunnel error",
                "failed to serve tunnel connection",
                "retrying connection",
            )):
                STATUS.update(connected=False, status="reconnecting_tunnel", lastError=line[-500:])

            if not found_url and time.time() - started_at > 60:
                STATUS.update(status="waiting_for_tunnel_url")

        exit_code = process.wait()
        raise RuntimeError(f"cloudflared завершился с кодом {exit_code}")
    finally:
        if process.poll() is None:
            process.terminate()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        STATUS.update(running=False, connected=False, status="stopped")
    except Exception as error:
        STATUS.update(
            running=False,
            connected=False,
            status="error",
            lastError=f"{type(error).__name__}: {error}",
        )
        print(f"[Tribute] ERROR {type(error).__name__}: {error}", flush=True)
        raise
