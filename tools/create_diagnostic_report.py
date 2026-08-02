from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
SECRET_KEY_RE = re.compile(r"(?i)(token|secret|password|api[_-]?key|client[_-]?secret|authorization|jwt|webhook[_-]?secret|widget[_-]?url)")
QUERY_SECRET_RE = re.compile(r"(?i)(token|access_token|refresh_token|jwt|key|secret|signature)")
INLINE_SECRET_RE = re.compile(r"(?i)\b(access_token|refresh_token|token|jwt|api[_-]?key|client_secret|secret)=([^&\s]+)")
LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_\-]{48,}\b")
SECRET_VALUES: set[str] = set()


def redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc:
            return value
        query = []
        for key, item in parse_qsl(parts.query, keep_blank_values=True):
            query.append((key, "***" if QUERY_SECRET_RE.search(key) else item))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except Exception:
        return value


def redact_text(value: object) -> str:
    text = str(value or "")
    text = INLINE_SECRET_RE.sub(lambda match: f"{match.group(1)}=***", text)
    text = re.sub(r"https?://[^\s\"'<>]+", lambda match: redact_url(match.group(0)), text)
    for secret in sorted(SECRET_VALUES, key=len, reverse=True):
        if len(secret) >= 8:
            text = text.replace(secret, "***")
    return LONG_SECRET_RE.sub("***", text)


def redact_data(value, key: str = ""):
    if SECRET_KEY_RE.search(str(key)):
        if value in (None, "", False):
            return value
        return "***SET***"
    if isinstance(value, dict):
        return {str(k): redact_data(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_data(item, key) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def read_json(path: Path, fallback=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tail_text(path: Path, lines: int = 250) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(redact_text(line) for line in content[-lines:]) + "\n"
    except Exception as exc:
        return f"Unable to read {path.name}: {type(exc).__name__}: {exc}\n"


def donation_summary() -> dict:
    items = read_json(ROOT / "core/data/donations.json", [])
    if not isinstance(items, list):
        return {"readable": False}
    sources = Counter(str(item.get("source") or "unknown").lower() for item in items if isinstance(item, dict))
    return {
        "readable": True,
        "count": len(items),
        "sources": dict(sorted(sources.items())),
        "lastCreatedAt": next((item.get("createdAt") for item in reversed(items) if isinstance(item, dict) and item.get("createdAt")), None),
        "messagesIncluded": False,
    }


def process_snapshot() -> str:
    try:
        if os.name == "nt":
            result = subprocess.run(["tasklist", "/FO", "CSV"], capture_output=True, text=True, timeout=10)
            rows = [line for line in result.stdout.splitlines() if any(name in line.lower() for name in ("python", "cloudflared", "chrome"))]
            return "\n".join(rows) + "\n"
        result = subprocess.run(["ps", "-eo", "pid,ppid,comm,args"], capture_output=True, text=True, timeout=10)
        rows = [line for line in result.stdout.splitlines() if any(name in line.lower() for name in ("python", "cloudflared", "chromium"))]
        return "\n".join(redact_text(line) for line in rows) + "\n"
    except Exception as exc:
        return f"Process snapshot unavailable: {type(exc).__name__}: {exc}\n"


def collect_secret_values() -> set[str]:
    values: set[str] = set()
    for manifest_path in (ROOT / "integrations").glob("*/manifest.json"):
        manifest = read_json(manifest_path, {})
        if not isinstance(manifest, dict):
            continue
        config_path = manifest_path.parent / str(manifest.get("configFile") or "")
        config = read_json(config_path, {}) if config_path.exists() else {}
        if isinstance(config, dict):
            for key in manifest.get("secretFields") or []:
                value = config.get(key)
                if isinstance(value, str) and len(value) >= 8:
                    values.add(value)
    for token_path in [
        ROOT / "integrations/donationalerts/donationalerts_tokens.json",
        ROOT / "integrations/streamlabs/streamlabs_tokens.json",
    ]:
        data = read_json(token_path, {})
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, str) and len(value) >= 8:
                    values.add(value)
    return values


def create_report(root: Path | None = None) -> Path:
    global ROOT
    if root is not None:
        ROOT = Path(root).resolve()
    SECRET_VALUES.clear()
    SECRET_VALUES.update(collect_secret_values())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / "diagnostics"
    work = output_dir / f"diagnostic_{stamp}"
    work.mkdir(parents=True, exist_ok=True)

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "dev"
    system = {
        "vicDonationGoalVersion": version,
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "workingDirectory": str(ROOT),
        "cloudflaredBundled": (ROOT / "tools/cloudflared.exe").exists(),
        "donations": donation_summary(),
    }
    write_json(work / "system.json", system)

    # Public manifest metadata and redacted configs.
    integrations = []
    configs = {}
    for manifest_path in sorted((ROOT / "integrations").glob("*/manifest.json")):
        manifest = read_json(manifest_path, {})
        if not isinstance(manifest, dict):
            continue
        integrations.append(redact_data(manifest))
        config_name = str(manifest.get("configFile") or "")
        if config_name:
            config_path = manifest_path.parent / config_name
            configs[str(manifest.get("id") or manifest_path.parent.name)] = redact_data(read_json(config_path, {}))
    write_json(work / "integrations_manifests.json", integrations)
    write_json(work / "integrations_configs_redacted.json", configs)

    statuses = {}
    runtime = ROOT / "runtime"
    if runtime.exists():
        for path in sorted(runtime.rglob("*.json")):
            rel = str(path.relative_to(runtime)).replace("\\", "/")
            statuses[rel] = redact_data(read_json(path, {}))
    write_json(work / "runtime_statuses_redacted.json", statuses)

    logs_dir = work / "logs"
    logs_dir.mkdir(exist_ok=True)
    for path in sorted(runtime.rglob("*.log")) if runtime.exists() else []:
        target = logs_dir / path.name
        target.write_text(tail_text(path), encoding="utf-8")

    for relative in [
        "integrations/streamerbot/streamerbot_config.json",
        "integrations/streamerbot/donation_event_rules.json",
        "integrations/tts/tts_config.json",
        "integrations/tts/tts_profiles.json",
        "integrations/tts/tts_rules.json",
    ]:
        path = ROOT / relative
        if path.exists():
            write_json(work / "configs" / (relative.replace("/", "__")), redact_data(read_json(path, {})))

    (work / "processes.txt").write_text(process_snapshot(), encoding="utf-8")

    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/stability_check.py")],
            cwd=ROOT, capture_output=True, text=True, timeout=180,
        )
        stability = (result.stdout or "") + ("\nSTDERR:\n" + result.stderr if result.stderr else "")
        (work / "stability_check.txt").write_text(redact_text(stability), encoding="utf-8")
    except Exception as exc:
        (work / "stability_check.txt").write_text(f"Stability Check failed: {type(exc).__name__}: {exc}\n", encoding="utf-8")

    (work / "README.txt").write_text(
        "VicDonationGoal diagnostic report\n"
        "Secrets, tokens and sensitive URL parameters are redacted.\n"
        "Donation message texts are not included; only aggregate counts are saved.\n",
        encoding="utf-8",
    )

    archive = output_dir / f"VicDonationGoal_diagnostic_{version}_{stamp}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(work.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(work.parent))
    import shutil
    shutil.rmtree(work, ignore_errors=True)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    archive = create_report()
    if args.json:
        print(json.dumps({"ok": True, "path": str(archive)}, ensure_ascii=False))
    else:
        print(f"Diagnostic report created: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
