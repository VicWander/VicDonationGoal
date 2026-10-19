from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PATCH_ROOT = PROJECT_ROOT / "_patch"
MANIFEST_PATH = PATCH_ROOT / "manifest.json"
PAYLOAD_ROOT = PATCH_ROOT / "files"

DATA_BACKUP_PATTERNS = (
    "core/data/*.json",
    "integrations/**/*.json",
    "integrations/**/*.txt",
    "runtime/**/*.json",
)

PROTECTED_USER_FILENAMES = {
    "integrations_onboarding.json",
    "donation_event_rules.json",
    "streamerbot_config.json",
    "streamerbot_event_rules_sent.json",
    "streamerbot_sent.json",
    "tts_config.json",
    "tts_profiles.json",
    "tts_rules.json",
    "tts_history.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: str) -> Path:
    relative = Path(str(value).replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"Небезопасный путь в manifest: {value}")
    return relative


def is_protected_user_file(relative: Path) -> bool:
    posix = relative.as_posix().lower()
    name = relative.name.lower()
    if posix.startswith("core/data/") and name.endswith(".json") and not name.endswith(".example.json"):
        return True
    if posix.startswith("runtime/"):
        return True
    if posix.startswith("integrations/"):
        if name in PROTECTED_USER_FILENAMES:
            return True
        if name.endswith(("_config.json", "_tokens.json", "_seen.json", "_sent.json", "_state.json")):
            return True
    return False


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("Не найден _patch/manifest.json. Распакуйте патч в папку VicDonationGoal целиком.")
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise ValueError("Некорректный manifest патча")
    return payload


def validate_patch(manifest: dict) -> list[tuple[Path, Path]]:
    current = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    compatible = {str(item) for item in manifest.get("compatibleFrom", [])}
    if current not in compatible:
        expected = ", ".join(sorted(compatible)) or "не указана"
        raise RuntimeError(f"Патч рассчитан на версию {expected}, а установлена {current}")

    files: list[tuple[Path, Path]] = []
    for item in manifest["files"]:
        relative = safe_relative(item.get("path", ""))
        if is_protected_user_file(relative):
            raise RuntimeError(f"Патч пытается заменить пользовательские данные: {relative}")
        source = PAYLOAD_ROOT / relative
        target = PROJECT_ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(f"В патче отсутствует файл: {relative}")
        expected_hash = str(item.get("sha256") or "").lower()
        actual_hash = sha256(source)
        if not expected_hash or actual_hash != expected_hash:
            raise RuntimeError(f"Не совпала контрольная сумма: {relative}")
        files.append((source, target))
    return files


def stop_processes() -> None:
    stopper = PROJECT_ROOT / "tools" / "stop_all.py"
    if stopper.exists():
        subprocess.run(
            [sys.executable, str(stopper), "--all-vicdonationgoal", "--quiet"],
            cwd=PROJECT_ROOT,
            check=False,
            timeout=45,
        )


def backup_paths(targets: list[Path]) -> tuple[Path, set[Path]]:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = PROJECT_ROOT / "backups" / "patch_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    archive = backup_dir / f"VicDonationGoal_before_patch_{stamp}.zip"

    paths: set[Path] = {path for path in targets if path.exists() and path.is_file()}
    for pattern in DATA_BACKUP_PATTERNS:
        paths.update(path for path in PROJECT_ROOT.glob(pattern) if path.is_file())

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(paths):
            output.write(path, path.relative_to(PROJECT_ROOT).as_posix())
    return archive, paths


def restore_backup(archive: Path, targets: list[Path], originally_existing: set[Path]) -> None:
    for target in targets:
        if target not in originally_existing and target.exists():
            target.unlink()
    with zipfile.ZipFile(archive) as source:
        source.extractall(PROJECT_ROOT)


def run_stability_check() -> tuple[bool, str]:
    check = PROJECT_ROOT / "tools" / "stability_check.py"
    if not check.exists():
        return False, "Не найден tools/stability_check.py"
    result = subprocess.run(
        [sys.executable, str(check)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    output = (result.stdout or "") + (("\nSTDERR:\n" + result.stderr) if result.stderr else "")
    return result.returncode == 0, output


def apply_patch() -> int:
    manifest = load_manifest()
    files = validate_patch(manifest)
    target_version = str(manifest.get("targetVersion") or "неизвестно")

    print(f"VicDonationGoal patch -> v{target_version}")
    print("Остановка процессов...")
    stop_processes()

    targets = [target for _, target in files]
    backup, originally_existing = backup_paths(targets)
    print(f"Резервная копия: {backup.relative_to(PROJECT_ROOT)}")

    try:
        for source, target in files:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        ok, output = run_stability_check()
        log_path = backup.with_name(backup.stem + "_stability.txt")
        log_path.write_text(output, encoding="utf-8")
        if not ok:
            raise RuntimeError(f"Stability Check нашёл критическую ошибку. Подробности: {log_path}")
    except Exception:
        restore_backup(backup, targets, originally_existing)
        raise

    print(f"Патч v{target_version} успешно установлен.")
    print("История, подключения, токены и пользовательские настройки сохранены.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe VicDonationGoal patch installer")
    parser.parse_args()
    try:
        return apply_patch()
    except Exception as error:
        print(f"ОШИБКА: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
