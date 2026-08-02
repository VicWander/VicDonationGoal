from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWN_MARKERS = (
    "server.py",
    "streamerbot_bridge.py",
    "tts_hub.py",
    "donatepay_listener.py",
    "donatestream_listener.py",
    "donatex_listener.py",
    "donatty_listener.py",
    "streamelements_listener.py",
    "streamlabs_integration.py",
    "tribute_tunnel.py",
    "cloudflared.exe",
)


def registry_pids() -> set[int]:
    result: set[int] = set()
    path = PROJECT_ROOT / "runtime" / "integration_processes.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in (payload.get("processes") or {}).values():
            if isinstance(item, dict) and item.get("pid"):
                result.add(int(item["pid"]))
        if payload.get("corePid"):
            result.add(int(payload["corePid"]))
    except Exception:
        pass
    return result


def discover_vicdonationgoal_pids() -> set[int]:
    if os.name != "nt":
        return set()
    script = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return set()
        payload = json.loads(completed.stdout)
        if isinstance(payload, dict):
            payload = [payload]
    except Exception:
        return set()

    pids: set[int] = set()
    current = os.getpid()
    for item in payload if isinstance(payload, list) else []:
        try:
            pid = int(item.get("ProcessId"))
        except Exception:
            continue
        if pid == current:
            continue
        command = str(item.get("CommandLine") or "").lower()
        if "vicdonationgoal" not in command:
            continue
        if any(marker in command for marker in KNOWN_MARKERS):
            pids.add(pid)
    return pids


def kill_pid(pid: int, quiet: bool = False) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if not quiet and completed.returncode == 0:
            print(f"Stopped PID {pid}")
        return completed.returncode == 0
    try:
        os.kill(pid, 15)
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-vicdonationgoal", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    pids = registry_pids()
    if args.all_vicdonationgoal:
        pids.update(discover_vicdonationgoal_pids())

    stopped = 0
    for pid in sorted(pids, reverse=True):
        stopped += 1 if kill_pid(pid, args.quiet) else 0

    # Give Windows a moment to release log and JSON handles.
    if pids:
        time.sleep(0.8)

    for relative in ("runtime/integration_processes.json",):
        try:
            (PROJECT_ROOT / relative).unlink()
        except Exception:
            pass

    if not args.quiet:
        print(f"VicDonationGoal processes stopped: {stopped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
