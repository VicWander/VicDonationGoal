from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable


TEXT_SUFFIXES = {
    ".bat", ".css", ".html", ".js", ".json", ".md", ".py", ".txt", ".yml", ".yaml"
}

FORBIDDEN_PARTS = {"__pycache__", ".venv", "venv", "runtime", "backups", "legacy"}
FORBIDDEN_NAMES = {
    "cloudflared.exe",
    "oauth_state.txt",
    "donationalerts_tokens.json",
    "streamlabs_tokens.json",
    "streamerbot_sent.json",
    "streamerbot_event_rules_sent.json",
    "tts_history.json",
    "tts_log.json",
    "tts_queue.json",
    "tts_sent.json",
    "donations.json",
    "donor_profiles.json",
    "donor_adjustments.json",
    "state.json",
}

LOCAL_NAME_PATTERNS = (
    re.compile(r"(?:^|/)[^/]+_config\.json$", re.IGNORECASE),
    re.compile(r"(?:^|/)[^/]+_(?:seen|runtime_state|catch_up_state)\.json$", re.IGNORECASE),
    re.compile(r"(?:^|/)README_PRIVATE[^/]*$", re.IGNORECASE),
    re.compile(r"(?:^|/)FINAL_TEST_REPORT[^/]*$", re.IGNORECASE),
    re.compile(r"(?:^|/)CHANGELOG_v[^/]*$", re.IGNORECASE),
    re.compile(r"(?:^|/)README_INSTALL[^/]*PATCH[^/]*$", re.IGNORECASE),
)

CONTENT_PATTERNS = {
    "JWT": re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}(?![A-Za-z0-9_-])"),
    "Bearer token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}"),
    "OAuth/secret JSON value": re.compile(
        r'(?i)"(?:access_token|refresh_token|client_secret|api_key|webhook_secret|widget_token|authorization)"\s*:\s*"(?!\s*(?:PASTE_|CHANGE_ME|ВСТАВЬ|__SET__))[^"]{12,}"'
    ),
    "Streamer.bot action UUID": re.compile(
        r'(?i)"action_id"\s*:\s*"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"'
    ),
    "Secret query parameter": re.compile(
        r"(?i)https?://[^\s\"'<>]+[?&](?:access_token|refresh_token|token|jwt|api_key|key|secret|signature)=[A-Za-z0-9._~+/-]{16,}"
    ),
}


def normalized_name(name: str) -> str:
    return str(PurePosixPath(name.replace("\\", "/"))).lstrip("./")


def forbidden_reason(name: str) -> str | None:
    normalized = normalized_name(name)
    path = PurePosixPath(normalized)
    if any(part.lower() in FORBIDDEN_PARTS for part in path.parts):
        return "runtime/private directory"
    if path.name.lower() in FORBIDDEN_NAMES:
        return "private runtime file"
    if path.name.lower().endswith(".example.json"):
        return None
    for pattern in LOCAL_NAME_PATTERNS:
        if pattern.search(normalized):
            return "local/private file"
    if "/audio_cache/" in f"/{normalized.lower()}/" and path.name != ".gitkeep":
        return "TTS audio cache"
    if normalized.lower().startswith("diagnostics/") and path.name != ".gitkeep":
        return "diagnostic output"
    if normalized.lower().startswith("integration_inspector_reports/") and path.name != ".gitkeep":
        return "integration inspector output"
    return None


def scan_text(name: str, raw: bytes) -> list[str]:
    if Path(name).suffix.lower() not in TEXT_SUFFIXES or len(raw) > 5_000_000:
        return []
    text = raw.decode("utf-8", errors="ignore")
    return [label for label, pattern in CONTENT_PATTERNS.items() if pattern.search(text)]


def iter_directory(root: Path) -> Iterable[tuple[str, bytes]]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path.relative_to(root).as_posix(), path.read_bytes()


def iter_zip(path: Path) -> Iterable[tuple[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        prefix = ""
        if files:
            first_parts = [PurePosixPath(item.filename).parts for item in files]
            if all(parts and parts[0] == first_parts[0][0] for parts in first_parts):
                prefix = first_parts[0][0] + "/"
        for item in files:
            name = item.filename[len(prefix):] if prefix and item.filename.startswith(prefix) else item.filename
            yield normalized_name(name), archive.read(item)


def scan(target: Path) -> tuple[int, list[tuple[str, str]]]:
    items = iter_zip(target) if target.is_file() and target.suffix.lower() == ".zip" else iter_directory(target)
    count = 0
    findings: list[tuple[str, str]] = []
    for name, raw in items:
        count += 1
        reason = forbidden_reason(name)
        if reason:
            findings.append((name, reason))
            continue
        for label in scan_text(name, raw):
            findings.append((name, label))
    return count, findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a VicDonationGoal release directory or ZIP without printing secret values.")
    parser.add_argument("target", nargs="?", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args()
    target = Path(args.target).resolve()
    if not target.exists() or (target.is_file() and target.suffix.lower() != ".zip"):
        print(f"ERROR: target must be a directory or ZIP: {target}")
        return 2

    count, findings = scan(target)
    print(f"Scanned files: {count}")
    if findings:
        print(f"Findings: {len(findings)}")
        for name, reason in findings:
            print(f"[ERR] {reason}: {name}")
        return 1
    print("Findings: 0")
    print("Release sanitization check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
