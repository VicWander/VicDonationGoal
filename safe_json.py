from __future__ import annotations

import copy
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(Path(path).resolve()).lower()
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


def _clone(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


def load_json(
    path: str | Path,
    fallback: Any,
    *,
    retries: int = 12,
    delay: float = 0.03,
    backup_dir: str | Path | None = None,
    backup_decode_errors: bool = True,
) -> Any:
    """Read JSON while tolerating short Windows sharing/replace races.

    Permission errors are treated as transient sharing violations, not as corruption.
    JSON decode errors are retried because another process may have been replacing the
    file at the exact moment of the read. Only a persistent decode error is backed up.
    """
    target = Path(path)
    last_error: BaseException | None = None

    for attempt in range(max(1, retries)):
        try:
            with target.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return _clone(fallback)
        except (PermissionError, OSError, json.JSONDecodeError) as error:
            last_error = error
            if attempt + 1 < max(1, retries):
                time.sleep(min(0.25, delay * (attempt + 1)))
                continue

    if (
        backup_dir
        and backup_decode_errors
        and isinstance(last_error, json.JSONDecodeError)
        and target.exists()
    ):
        try:
            backup_root = Path(backup_dir)
            backup_root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup = backup_root / f"{target.stem}_{stamp}{target.suffix}.broken.bak"
            # read_bytes can itself hit a sharing violation, so retry a few times.
            for attempt in range(8):
                try:
                    backup.write_bytes(target.read_bytes())
                    break
                except (PermissionError, OSError):
                    if attempt == 7:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        except Exception:
            pass

    return _clone(fallback)


def save_json(
    path: str | Path,
    data: Any,
    *,
    retries: int = 80,
    delay: float = 0.025,
) -> None:
    """Atomically write JSON and retry Windows sharing violations.

    `os.replace` may briefly fail when another Python process, antivirus or Explorer
    has the destination open. Retrying avoids false corruption and lost updates.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    temp = target.with_name(f".{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
    lock = _lock_for(target)

    with lock:
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            last_error: BaseException | None = None
            for attempt in range(max(1, retries)):
                try:
                    os.replace(temp, target)
                    return
                except (PermissionError, OSError) as error:
                    last_error = error
                    if attempt + 1 >= max(1, retries):
                        break
                    time.sleep(min(0.2, delay * (1 + attempt // 4)))

            raise last_error or PermissionError(f"Не удалось заменить {target}")
        finally:
            if temp.exists():
                for attempt in range(8):
                    try:
                        temp.unlink()
                        break
                    except (PermissionError, OSError):
                        if attempt == 7:
                            break
                        time.sleep(0.05 * (attempt + 1))
