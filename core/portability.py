from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Callable


BACKUP_FORMAT = "vicdonationgoal-backup"
BACKUP_SCHEMA_VERSION = 1
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_FILES = 500
BACKUP_CAPTURE_ATTEMPTS = 3

CORE_DATA_NAMES = {
    "state.json",
    "donations.json",
    "rates.json",
    "donor_profiles.json",
    "donor_adjustments.json",
}

IGNORED_JSON_NAMES = {
    "manifest.json",
}

CUSTOM_TTS_DIR_NAMES = {
    "voices",
    "voice_samples",
    "reference_audio",
    "custom_audio",
}


class PortabilityError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_filename(value: str, fallback: str = "file") -> str:
    text = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "_", str(value or "")).strip("._")
    return text[:120] or fallback


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def app_version(project_root: Path) -> str:
    path = Path(project_root) / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "unknown"


def category_for_path(relative: str) -> str:
    path = relative.replace("\\", "/")
    if path == "core/data/donations.json":
        return "donation_history"
    if path in {"core/data/donor_profiles.json", "core/data/donor_adjustments.json"}:
        return "topdonation"
    if path in {"core/data/state.json", "core/data/rates.json"}:
        return "goal_and_rates"
    if path.startswith("integrations/streamerbot/"):
        return "streamerbot"
    if path.startswith("integrations/tts/"):
        return "tts"
    if path == "integrations/integrations_onboarding.json":
        return "integration_selection"
    if path.startswith("integrations/"):
        return "integrations"
    return "other"


def _safe_relative_path(value: str) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    if any(ord(char) < 32 or char in ':<>"|?*' for char in value):
        return False
    parts = value.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{kind}{i}" for kind in ("COM", "LPT") for i in range(1, 10)}
    return all(
        part and part not in {".", ".."} and not part.endswith((".", " "))
        and part.split(".", 1)[0].upper() not in reserved
        for part in parts
    )


def is_user_data_path(relative: str) -> bool:
    if not _safe_relative_path(relative):
        return False
    normalized = relative.lower()
    parts = PurePosixPath(normalized).parts
    if ".." in parts or not parts:
        return False

    if len(parts) == 3 and parts[:2] == ("core", "data"):
        return parts[-1] in CORE_DATA_NAMES

    if normalized == "integrations/integrations_onboarding.json":
        return True

    if len(parts) >= 3 and parts[0] == "integrations":
        name = parts[-1]
        if name.endswith(".example.json") or name in IGNORED_JSON_NAMES:
            return False
        if name.endswith(".json"):
            return True
        if len(parts) >= 4 and parts[1] == "tts" and parts[2] in CUSTOM_TTS_DIR_NAMES:
            return True

    return False


def _user_data_destination(project_root: Path, relative: str) -> Path:
    if not is_user_data_path(relative):
        raise PortabilityError(f"Неподдерживаемый или небезопасный путь: {relative}")
    root = Path(project_root).resolve()
    destination = (root / PurePosixPath(relative)).resolve()
    if not destination.is_relative_to(root):
        raise PortabilityError(f"Путь выходит за пределы папки программы: {relative}")
    return destination


def normalize_old_relative_path(value: str) -> str | None:
    raw = str(value or "").replace("\\", "/").strip("/")
    if not raw or ".." in raw.split("/"):
        return None
    candidates = [raw]
    parts = raw.split("/")
    for index in range(1, len(parts)):
        candidates.append("/".join(parts[index:]))
    for candidate in candidates:
        if is_user_data_path(candidate):
            return str(PurePosixPath(candidate))
    return None


def collect_user_files(project_root: Path) -> list[Path]:
    project_root = Path(project_root)
    result: list[Path] = []
    core_data = project_root / "core" / "data"
    for name in sorted(CORE_DATA_NAMES):
        path = core_data / name
        if path.is_file():
            result.append(path)

    integrations = project_root / "integrations"
    if integrations.exists():
        for path in sorted(integrations.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(project_root).as_posix()
            if is_user_data_path(relative):
                result.append(path)

    unique: dict[str, Path] = {}
    for path in result:
        unique[path.relative_to(project_root).as_posix()] = path
    return [unique[key] for key in sorted(unique)]


def _manifest_for_payload(project_root: Path, payload: dict[str, bytes], reason: str) -> dict[str, Any]:
    entries = []
    total_size = 0
    for relative, data in sorted(payload.items()):
        total_size += len(data)
        entries.append({
            "path": relative,
            "category": category_for_path(relative),
            "size": len(data),
            "sha256": sha256_bytes(data),
        })
    return {
        "format": BACKUP_FORMAT,
        "schemaVersion": BACKUP_SCHEMA_VERSION,
        "appVersion": app_version(project_root),
        "createdAt": now_iso(),
        "reason": str(reason or "manual"),
        "containsSecrets": True,
        "fileCount": len(entries),
        "totalSize": total_size,
        "files": entries,
    }


def _capture_user_payload(project_root: Path) -> dict[str, bytes]:
    files = collect_user_files(project_root)
    if len(files) + 1 > MAX_ARCHIVE_FILES:
        raise PortabilityError("Слишком много пользовательских файлов для резервной копии")
    payload = {}
    total = 0
    for path in files:
        relative = path.relative_to(project_root).as_posix()
        content = _user_data_destination(project_root, relative).read_bytes()
        total += len(content)
        if total > MAX_ARCHIVE_BYTES:
            raise PortabilityError("Пользовательские данные превышают допустимый размер резервной копии")
        payload[relative] = content
    return payload


def create_backup_bytes(project_root: Path, reason: str = "manual") -> tuple[bytes, dict[str, Any]]:
    project_root = Path(project_root)
    # Core protects its stores with locks; separate workers can still update sent
    # markers. Require two matching captures and fail safely if they keep changing.
    payload = None
    for attempt in range(BACKUP_CAPTURE_ATTEMPTS):
        try:
            first = _capture_user_payload(project_root)
            second = _capture_user_payload(project_root)
            if first == second:
                payload = first
                break
        except OSError:
            pass
        time.sleep(0.02 * (attempt + 1))
    if payload is None:
        raise PortabilityError("Файлы меняются или временно недоступны. Повторите создание бэкапа через несколько секунд")
    if not payload:
        raise PortabilityError("Не найдено пользовательских данных для резервной копии")
    validate_user_payload(payload)
    manifest = _manifest_for_payload(project_root, payload, reason)
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if sum(map(len, payload.values())) + len(manifest_bytes) > MAX_ARCHIVE_BYTES:
        raise PortabilityError("Данные вместе с описанием архива превышают допустимый размер восстановления")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        for relative, content in sorted(payload.items()):
            archive.writestr(f"data/{relative}", content)
    archive_bytes = output.getvalue()
    if len(archive_bytes) > MAX_UPLOAD_BYTES:
        raise PortabilityError("Архив превышает допустимый размер восстановления; уменьшите объём переносимых аудиофайлов")
    return archive_bytes, manifest


def write_backup(project_root: Path, reason: str = "manual", group: str = "manual") -> tuple[Path, dict[str, Any]]:
    project_root = Path(project_root)
    payload, manifest = create_backup_bytes(project_root, reason=reason)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"VicDonationGoal_Backup_v{safe_filename(manifest['appVersion'], 'unknown')}_{stamp}.zip"
    destination = project_root / "backups" / safe_filename(group, "manual") / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + f".{uuid.uuid4().hex}.tmp")
    temp.write_bytes(payload)
    os.replace(temp, destination)
    return destination, manifest


def list_local_backups(project_root: Path, limit: int = 12) -> list[dict[str, Any]]:
    root = Path(project_root) / "backups"
    rows = []
    for group in ("automatic", "manual"):
        folder = root / group
        if not folder.exists():
            continue
        for path in folder.glob("*.zip"):
            try:
                stat = path.stat()
                rows.append({
                    "id": f"{group}/{path.name}",
                    "group": group,
                    "name": path.name,
                    "size": stat.st_size,
                    "modifiedAt": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
                })
            except OSError:
                continue
    rows.sort(key=lambda item: item["modifiedAt"], reverse=True)
    return rows[: max(1, int(limit))]


def resolve_local_backup(project_root: Path, backup_id: str) -> Path:
    raw = str(backup_id or "")
    if not _safe_relative_path(raw):
        raise PortabilityError("Некорректный ID резервной копии")
    parts = PurePosixPath(raw).parts
    if len(parts) != 2 or parts[0] not in {"automatic", "manual"}:
        raise PortabilityError("Некорректный ID резервной копии")
    root = (Path(project_root) / "backups").resolve()
    path = (root / parts[0] / parts[1]).resolve()
    if not path.is_relative_to(root):
        raise PortabilityError("Путь резервной копии выходит за пределы папки бэкапов")
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise PortabilityError("Резервная копия не найдена")
    return path


def _validate_zip_members(archive: zipfile.ZipFile) -> None:
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_FILES:
        raise PortabilityError("В архиве слишком много файлов")
    total = 0
    names = set()
    for item in members:
        name = item.filename.rstrip("/") if item.is_dir() else item.filename
        if not _safe_relative_path(name):
            raise PortabilityError("Архив содержит небезопасный путь")
        if name.casefold() in names:
            raise PortabilityError("Архив содержит повторяющиеся пути")
        names.add(name.casefold())
        total += max(0, int(item.file_size))
        if total > MAX_ARCHIVE_BYTES:
            raise PortabilityError("Распакованный архив слишком большой")


def _read_json_bytes(data: bytes, label: str) -> Any:
    try:
        def reject_constant(value):
            raise ValueError("non-finite JSON number")
        return json.loads(data.decode("utf-8-sig"), parse_constant=reject_constant)
    except Exception as error:
        raise PortabilityError(f"{label}: некорректный JSON ({type(error).__name__})") from error


def _finite_number(value: Any, label: str, minimum: float | None = None, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PortabilityError(f"{label}: ожидалось число")
    try:
        number = float(str(value).replace(",", "."))
    except (ValueError, OverflowError):
        raise PortabilityError(f"{label}: некорректное число") from None
    if not math.isfinite(number):
        raise PortabilityError(f"{label}: NaN и бесконечные суммы не поддерживаются")
    if (positive and number <= 0) or (minimum is not None and number < minimum):
        raise PortabilityError(f"{label}: недопустимое значение суммы")
    return number


def _object_rows(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise PortabilityError(f"{label}: ожидался JSON-массив")
    for index, row in enumerate(value, 1):
        if not isinstance(row, dict):
            raise PortabilityError(f"{label}, запись {index}: ожидался объект")
    return value


def _valid_identifier(value: Any) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool) and bool(str(value).strip())


def _validate_donations(value: Any, label: str) -> None:
    for index, row in enumerate(_object_rows(value, label), 1):
        context = f"{label}, запись {index}"
        _finite_number(row.get("amount"), f"{context}, amount", positive=True)
        has_key = _valid_identifier(row.get("uniqueKey"))
        has_external_id = _valid_identifier(row.get("source")) and any(
            _valid_identifier(row.get(key)) for key in ("externalId", "external_id", "externalID")
        )
        if not has_key and not has_external_id:
            raise PortabilityError(f"{context}: нет uniqueKey или source с externalId; безопасно определить дубли невозможно")
        for field in ("amountForGoal", "amountForTop"):
            if row.get(field) is not None:
                _finite_number(row[field], f"{context}, {field}", minimum=0)
        for field in ("source", "username", "name", "currency", "message", "note", "createdAt", "receivedAt", "donorId"):
            if row.get(field) is not None and not isinstance(row[field], str):
                raise PortabilityError(f"{context}, {field}: ожидалась строка")
        for field in ("includeInGoal", "includeInTop", "notifyStreamerBot", "triggerDonationEvents", "speakTTS"):
            value = row.get(field)
            if value is not None and str(value).lower() not in {"true", "false", "1", "0", "1.0", "0.0", "yes", "no", "on", "off", "да", "нет", "д", "н"}:
                raise PortabilityError(f"{context}, {field}: ожидалось логическое значение")


def validate_user_payload(payload: dict[str, bytes]) -> dict[str, str]:
    """Validate all known records before writing any imported file; keep extra fields."""
    schemas: dict[str, str] = {}
    seen = set()
    for relative, content in payload.items():
        if not is_user_data_path(relative):
            raise PortabilityError(f"Неподдерживаемый или небезопасный путь: {relative}")
        name = relative.lower()
        if name in seen:
            raise PortabilityError(f"Повторяющийся путь: {relative}")
        seen.add(name)
        if not name.endswith(".json"):
            schemas[relative] = "binary"
            continue
        parsed = _read_json_bytes(content, relative)
        if name == "core/data/donations.json":
            _validate_donations(parsed, relative)
        elif name == "core/data/donor_profiles.json":
            ids = set()
            for index, profile in enumerate(_object_rows(parsed, relative), 1):
                if not _valid_identifier(profile.get("id")) or str(profile["id"]) in ids:
                    raise PortabilityError(f"{relative}, запись {index}: пустой или повторяющийся ID профиля")
                ids.add(str(profile["id"]))
                for field in ("displayName", "note", "createdAt", "updatedAt"):
                    if profile.get(field) is not None and not isinstance(profile[field], str):
                        raise PortabilityError(f"{relative}, запись {index}, {field}: ожидалась строка")
                for alias in _object_rows(profile.get("aliases", []), f"{relative}, aliases"):
                    if not all(isinstance(alias.get(key), str) and alias[key].strip() for key in ("source", "username")):
                        raise PortabilityError(f"{relative}, запись {index}: некорректный алиас")
                if profile.get("pinOrder") is not None:
                    _finite_number(profile["pinOrder"], f"{relative}, pinOrder")
        elif name == "core/data/donor_adjustments.json":
            for index, adjustment in enumerate(_object_rows(parsed, relative), 1):
                if not _valid_identifier(adjustment.get("id")) or not _valid_identifier(adjustment.get("donorId")):
                    raise PortabilityError(f"{relative}, запись {index}: нет ID корректировки или донатера")
                for field in ("amount", "amountForTop", "snapshotAmount", "baseDonationAmount"):
                    if adjustment.get(field) is not None:
                        _finite_number(adjustment[field], f"{relative}, запись {index}, {field}")
                        # The adjustments reader uses float(), unlike donations.
                        if isinstance(adjustment[field], str) and "," in adjustment[field]:
                            raise PortabilityError(f"{relative}, запись {index}, {field}: используйте точку в дробной сумме")
        elif name in {"core/data/state.json", "core/data/rates.json", "integrations/integrations_onboarding.json"}:
            if not isinstance(parsed, dict):
                raise PortabilityError(f"{relative}: ожидался JSON-объект")
            if name.endswith("state.json"):
                for field in ("goal", "current", "baseAmount"):
                    if parsed.get(field) is not None:
                        _finite_number(parsed[field], f"{relative}, {field}", minimum=0, positive=field == "goal")
                if parsed.get("lastDonation") is not None and not isinstance(parsed["lastDonation"], dict):
                    raise PortabilityError(f"{relative}, lastDonation: ожидался объект")
            if name.endswith("rates.json") and "ratesToRUB" in parsed:
                if not isinstance(parsed["ratesToRUB"], dict):
                    raise PortabilityError(f"{relative}, ratesToRUB: ожидался объект")
                for currency, rate in parsed["ratesToRUB"].items():
                    _finite_number(rate, f"{relative}, курс {currency}", positive=True)
        elif name.startswith("integrations/tts/") and Path(name).name in {
            "tts_profiles.json", "tts_rules.json", "tts_queue.json", "tts_history.json", "tts_log.json",
        }:
            _object_rows(parsed, relative)
        elif name.endswith(("_config.json", "config.json", "_tokens.json", "tts_control.json")):
            if not isinstance(parsed, dict):
                raise PortabilityError(f"{relative}: ожидался JSON-объект")
        elif not isinstance(parsed, (dict, list)):
            raise PortabilityError(f"{relative}: ожидался JSON-объект или массив")
        schemas[relative] = "list" if isinstance(parsed, list) else "object"
    return schemas


def _version_major(value: str) -> int | None:
    match = re.match(r"\s*v?(\d+)", str(value or ""), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def inspect_backup_bytes(data: bytes, current_version: str | None = None) -> tuple[dict[str, Any], dict[str, bytes]]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise PortabilityError("Файл превышает допустимый размер")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except Exception as error:
        raise PortabilityError("Файл не является ZIP-архивом VicDonationGoal") from error

    with archive:
        _validate_zip_members(archive)
        names = set(archive.namelist())
        if "manifest.json" not in names:
            raise PortabilityError("В архиве нет manifest.json; для старой папки используйте импорт папки")
        manifest = _read_json_bytes(archive.read("manifest.json"), "manifest.json")
        if not isinstance(manifest, dict) or manifest.get("format") != BACKUP_FORMAT:
            raise PortabilityError("Это не резервная копия VicDonationGoal")
        schema = int(manifest.get("schemaVersion") or 0)
        if schema < 1:
            raise PortabilityError("Неизвестная схема резервной копии")
        if schema > BACKUP_SCHEMA_VERSION:
            raise PortabilityError(
                f"Архив использует схему {schema}, а эта версия поддерживает только {BACKUP_SCHEMA_VERSION}"
            )
        source_major = _version_major(manifest.get("appVersion", "unknown"))
        current_major = _version_major(current_version) if current_version is not None else None
        if source_major is not None and current_major is not None and source_major > current_major:
            raise PortabilityError(f"Данные из v{manifest['appVersion']} новее этой программы (v{current_version}); импорт отменён")

        payload: dict[str, bytes] = {}
        entries = manifest.get("files")
        if not isinstance(entries, list) or not entries:
            raise PortabilityError("В manifest.json нет списка пользовательских файлов")
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise PortabilityError("manifest.json содержит некорректную запись файла")
            relative = str(entry.get("path") or "")
            if not is_user_data_path(relative):
                raise PortabilityError(f"Архив содержит неподдерживаемый путь: {relative}")
            if relative.casefold() in seen:
                raise PortabilityError("manifest.json содержит повторяющиеся пути")
            seen.add(relative.casefold())
            member = f"data/{relative}"
            if member not in names:
                raise PortabilityError(f"В архиве отсутствует {relative}")
            content = archive.read(member)
            if entry.get("size") != len(content) or isinstance(entry.get("size"), bool):
                raise PortabilityError(f"Размер {relative} не совпадает с manifest.json")
            if str(entry.get("sha256") or "") != sha256_bytes(content):
                raise PortabilityError(f"Контрольная сумма {relative} не совпадает")
            if relative.endswith(".json"):
                _read_json_bytes(content, relative)
            payload[relative] = content
        validate_user_payload(payload)
    return manifest, payload


def backup_preview(data: bytes, current_version: str) -> dict[str, Any]:
    manifest, payload = inspect_backup_bytes(data, current_version=current_version)
    categories: dict[str, int] = {}
    for relative in payload:
        category = category_for_path(relative)
        categories[category] = categories.get(category, 0) + 1
    warnings = ["Архив содержит токены и секреты подключений. Не отправляйте его другим людям."]
    source_version = str(manifest.get("appVersion") or "unknown")
    if source_version != current_version:
        warnings.append(f"Данные будут перенесены из v{source_version} в v{current_version}.")
    return {
        "kind": "backup",
        "compatible": True,
        "sourceVersion": source_version,
        "schemaVersion": manifest.get("schemaVersion"),
        "createdAt": manifest.get("createdAt"),
        "containsSecrets": bool(manifest.get("containsSecrets", True)),
        "fileCount": len(payload),
        "totalSize": sum(len(item) for item in payload.values()),
        "categories": categories,
        "warnings": warnings,
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def apply_payload(project_root: Path, payload: dict[str, bytes]) -> list[str]:
    project_root = Path(project_root)
    validate_user_payload(payload)
    destinations = {relative: _user_data_destination(project_root, relative) for relative in sorted(payload)}
    originals = {relative: path.read_bytes() if path.exists() else None for relative, path in destinations.items()}
    touched = []
    try:
        for relative, path in destinations.items():
            touched.append(relative)
            _atomic_write(path, payload[relative])
    except Exception as error:
        failed = []
        for relative in reversed(touched):
            path = destinations[relative]
            try:
                if originals[relative] is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write(path, originals[relative])
            except OSError:
                failed.append(relative)
        if failed:
            raise PortabilityError("Не удалось откатить файлы: " + ", ".join(failed)) from error
        raise
    return list(destinations)


def folder_payload_from_request(files: list[dict[str, Any]]) -> dict[str, bytes]:
    if not isinstance(files, list) or not files:
        raise PortabilityError("В выбранной папке не найдено файлов")
    payload: dict[str, bytes] = {}
    total = 0
    for entry in files:
        if not isinstance(entry, dict):
            continue
        relative = normalize_old_relative_path(str(entry.get("path") or ""))
        if not relative:
            continue
        try:
            content = base64.b64decode(str(entry.get("content") or ""), validate=True)
        except Exception as error:
            raise PortabilityError(f"Не удалось прочитать {entry.get('path')}") from error
        total += len(content)
        if total > MAX_UPLOAD_BYTES:
            raise PortabilityError("Пользовательские данные старой папки слишком большие")
        if relative.endswith(".json"):
            _read_json_bytes(content, relative)
        if relative.casefold() in {name.casefold() for name in payload}:
            raise PortabilityError(f"В выбранной папке несколько файлов с путём {relative}; выберите одну версию программы")
        payload[relative] = content
    if not payload:
        raise PortabilityError("В выбранной папке нет поддерживаемых пользовательских данных")
    validate_user_payload(payload)
    return payload


def folder_preview(payload: dict[str, bytes], current_version: str, source_version: str = "unknown") -> dict[str, Any]:
    validate_user_payload(payload)
    source_major = _version_major(source_version)
    current_major = _version_major(current_version)
    if source_major is not None and current_major is not None and source_major > current_major:
        raise PortabilityError(
            f"Данные из v{source_version} новее этой программы (v{current_version}); импорт отменён"
        )
    categories: dict[str, int] = {}
    for relative in payload:
        category = category_for_path(relative)
        categories[category] = categories.get(category, 0) + 1
    warnings = []
    if source_version in {"", "unknown"}:
        warnings.append("В старой папке не найден VERSION. Структура JSON проверена, но номер исходной версии неизвестен.")
    if "core/data/donations.json" not in payload:
        warnings.append("В папке не найден donations.json — история донатов не будет перенесена.")
    if not any("tokens.json" in key for key in payload):
        warnings.append("OAuth-токены не найдены. Некоторые сервисы могут потребовать повторную авторизацию.")
    return {
        "kind": "folder",
        "compatible": True,
        "sourceVersion": source_version or "unknown",
        "targetVersion": current_version,
        "fileCount": len(payload),
        "totalSize": sum(len(item) for item in payload.values()),
        "categories": categories,
        "warnings": warnings,
    }


def parse_donations_bytes(data: bytes) -> list[dict[str, Any]]:
    parsed = _read_json_bytes(data, "donations.json")
    _validate_donations(parsed, "donations.json")
    return parsed


def donation_preview(
    incoming: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    normalize: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    existing_keys = {str(item.get("uniqueKey") or "") for item in existing if isinstance(item, dict)}
    seen = set(existing_keys)
    new_count = 0
    duplicate_count = 0
    invalid_count = 0
    total_new = 0.0
    sources: dict[str, int] = {}
    for raw in incoming:
        item = normalize(raw)
        key = str(item.get("uniqueKey") or "")
        amount = float(item.get("amount") or 0)
        if not key or amount <= 0:
            invalid_count += 1
            continue
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        new_count += 1
        total_new += float(item.get("amountForTop") or item.get("amountForGoal") or 0)
        source = str(item.get("source") or "unknown")
        sources[source] = sources.get(source, 0) + 1
    return {
        "kind": "donations",
        "compatible": True,
        "rows": len(incoming),
        "newCount": new_count,
        "duplicateCount": duplicate_count,
        "invalidCount": invalid_count,
        "newTopAmount": round(total_new, 2),
        "sources": sources,
        "warnings": [
            "Импортированные записи не запустят TTS, Streamer.bot или донат-ивенты.",
            "По умолчанию новые записи не добавляются в текущий сбор, но учитываются в TopDonation.",
        ],
    }


def merge_donations(
    incoming: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    normalize: Callable[[dict[str, Any]], dict[str, Any]],
    include_in_goal: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    result = [normalize(item) for item in existing if isinstance(item, dict)]
    seen = {str(item.get("uniqueKey") or "") for item in result}
    stats = {"added": 0, "duplicates": 0, "invalid": 0}
    for raw in incoming:
        item = normalize(raw)
        key = str(item.get("uniqueKey") or "")
        if not key or float(item.get("amount") or 0) <= 0:
            stats["invalid"] += 1
            continue
        if key in seen:
            stats["duplicates"] += 1
            continue
        seen.add(key)
        item["includeInGoal"] = bool(include_in_goal)
        item["notifyStreamerBot"] = False
        item["triggerDonationEvents"] = False
        item["speakTTS"] = False
        item["includeInTop"] = bool(item.get("includeInTop", True))
        note = str(item.get("note") or "").strip()
        item["note"] = (note + " | " if note else "") + "Импортировано из donations.json"
        result.append(item)
        stats["added"] += 1
    return result, stats


class DonationAlertsTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def parse_donationalerts_table(data: bytes) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1251", errors="replace")
    parser = DonationAlertsTableParser()
    parser.feed(text)
    if not parser.rows:
        raise PortabilityError("В файле DonationAlerts не найдена таблица")
    headers = [re.sub(r"\s+", " ", item).strip() for item in parser.rows[0]]
    normalized_headers = [item.casefold() for item in headers]
    try:
        name_index = normalized_headers.index("имя пользователя")
        amount_index = next(index for index, item in enumerate(normalized_headers) if item.startswith("сумма"))
    except (ValueError, StopIteration) as error:
        raise PortabilityError("Не найдены обязательные колонки «Имя пользователя» и «Сумма»") from error

    result = []
    for row in parser.rows[1:]:
        if max(name_index, amount_index) >= len(row):
            continue
        username = re.sub(r"\s+", " ", row[name_index]).strip() or "Аноним"
        raw_amount = row[amount_index].replace("\u00a0", "").replace(" ", "").replace(",", ".")
        try:
            amount = round(float(raw_amount), 2)
        except ValueError:
            continue
        if amount <= 0:
            continue
        result.append({"username": username, "amount": amount})
    if not result:
        raise PortabilityError("В таблице DonationAlerts нет корректных строк")
    return result


def stage_directory(project_root: Path) -> Path:
    path = Path(project_root) / "runtime" / "import_staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_staging(project_root: Path, max_age_seconds: int = 24 * 3600) -> None:
    root = stage_directory(project_root)
    cutoff = time.time() - max_age_seconds
    for path in root.iterdir():
        try:
            if path.stat().st_mtime < cutoff:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        except OSError:
            continue


def create_stage(project_root: Path, kind: str, filename: str, data: bytes, preview: dict[str, Any]) -> str:
    cleanup_staging(project_root)
    token = uuid.uuid4().hex
    folder = stage_directory(project_root) / token
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "input.bin").write_bytes(data)
    metadata = {
        "token": token,
        "kind": kind,
        "filename": safe_filename(filename, "import.bin"),
        "createdAt": now_iso(),
        "preview": preview,
    }
    (folder / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return token


def create_folder_stage(project_root: Path, payload: dict[str, bytes], preview: dict[str, Any]) -> str:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, content in sorted(payload.items()):
            archive.writestr(relative, content)
    return create_stage(project_root, "folder", "old-version-folder.zip", output.getvalue(), preview)


def load_stage(project_root: Path, token: str) -> tuple[dict[str, Any], bytes]:
    clean = re.fullmatch(r"[0-9a-f]{32}", str(token or ""))
    if not clean:
        raise PortabilityError("Некорректный токен импорта")
    folder = stage_directory(project_root) / clean.group(0)
    meta_path = folder / "meta.json"
    input_path = folder / "input.bin"
    if not meta_path.is_file() or not input_path.is_file():
        raise PortabilityError("Предпросмотр импорта устарел; выберите файл заново")
    metadata = _read_json_bytes(meta_path.read_bytes(), "meta.json")
    return metadata, input_path.read_bytes()


def delete_stage(project_root: Path, token: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", str(token or "")):
        return
    folder = stage_directory(project_root) / str(token)
    if folder.is_dir():
        shutil.rmtree(folder)


def payload_from_staged_folder(data: bytes) -> dict[str, bytes]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except Exception as error:
        raise PortabilityError("Не удалось прочитать выбранную папку") from error
    payload: dict[str, bytes] = {}
    with archive:
        _validate_zip_members(archive)
        for item in archive.infolist():
            if item.is_dir():
                continue
            relative = normalize_old_relative_path(item.filename)
            if relative:
                if relative.casefold() in {name.casefold() for name in payload}:
                    raise PortabilityError(f"В выбранной папке несколько файлов с путём {relative}")
                payload[relative] = archive.read(item.filename)
    if not payload:
        raise PortabilityError("В выбранной папке нет поддерживаемых данных")
    validate_user_payload(payload)
    return payload


def make_download_name(version: str) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"VicDonationGoal_Backup_v{safe_filename(version, 'unknown')}_{stamp}.zip"
