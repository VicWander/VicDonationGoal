"""Validated, atomic UI preferences, separate from donation/OBS configuration.

Readers fail safe to defaults; a damaged or newer file is never overwritten by a
partial update. Every transaction reads from disk so imports and other instances
are visible immediately. LOCK serializes the entire read/merge/write transaction.
"""
from __future__ import annotations

import copy
import sys
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from safe_json import load_json as _load_json, save_json as _save_json

SCHEMA_VERSION = 1
SETTINGS_FILE = Path(__file__).resolve().parent / "ui_settings.json"
LOCK = threading.RLock()
BASE_FAMILIES = frozenset({"neutral", "stone", "zinc", "slate", "gray"})
ACCENT_FAMILIES = BASE_FAMILIES | frozenset({
    "red", "orange", "amber", "yellow", "lime", "green", "emerald", "teal",
    "cyan", "sky", "blue", "indigo", "violet", "purple", "fuchsia", "pink",
    "rose", "mauve", "olive", "mist", "taupe",
})
BASE_FAMILIES = ACCENT_FAMILIES
WIDGET_MINIMUMS = {
    "connections": (6, 2), "latest": (4, 6), "goal": (4, 4),
    "manual": (4, 8), "speech": (4, 5), "top": (4, 5),
    "summary": (4, 3), "rates": (4, 5), "ttsQueue": (4, 5),
    "ttsTest": (4, 6), "ttsHistory": (4, 5), "services": (4, 4),
}
MAX_ROWS = 128
MAX_WIDGET_HEIGHT = 30


class UIPreferencesError(ValueError):
    """A request or persisted UI preference file violates the schema."""


def default_settings() -> dict[str, Any]:
    # Layout matches the approved Studio dashboard prototype.
    return {
        "schemaVersion": SCHEMA_VERSION,
        "theme": {"mode": "dark", "family": "monocrome", "base": "neutral", "accent": "neutral", "baseSaturation": 35},
        "dashboard": {"widgets": [
            {"id": "connections", "x": 0, "y": 0, "w": 12, "h": 2},
            {"id": "latest", "x": 0, "y": 2, "w": 8, "h": 14},
            {"id": "goal", "x": 8, "y": 2, "w": 4, "h": 4},
            {"id": "manual", "x": 8, "y": 6, "w": 4, "h": 11},
        ]},
    }


def _object(value: Any, allowed: set[str], label: str, *, complete: bool = False) -> dict:
    if not isinstance(value, dict):
        raise UIPreferencesError(f"{label}: ожидался JSON-объект")
    if set(value) - allowed:
        raise UIPreferencesError(f"{label}: неизвестные поля")
    if complete and set(value) != allowed:
        raise UIPreferencesError(f"{label}: отсутствуют обязательные поля")
    return value


def _choice(value: Any, choices: set[str] | frozenset[str], label: str) -> None:
    if not isinstance(value, str) or value not in choices:
        raise UIPreferencesError(f"{label}: недопустимое значение")


def _integer(value: Any, minimum: int, maximum: int, label: str) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise UIPreferencesError(f"{label}: ожидалось целое число от {minimum} до {maximum}")


def _validate_widgets(widgets: Any) -> None:
    if not isinstance(widgets, list) or len(widgets) > len(WIDGET_MINIMUMS):
        raise UIPreferencesError(f"dashboard.widgets: ожидался массив до {len(WIDGET_MINIMUMS)} блоков")
    seen = set()
    placed = []
    for index, widget in enumerate(widgets):
        label = f"dashboard.widgets[{index}]"
        _object(widget, {"id", "x", "y", "w", "h"}, label, complete=True)
        widget_id = widget["id"]
        _choice(widget_id, set(WIDGET_MINIMUMS), f"{label}.id")
        if widget_id in seen:
            raise UIPreferencesError(f"{label}.id: повторяющийся блок")
        seen.add(widget_id)
        min_w, min_h = WIDGET_MINIMUMS[widget_id]
        _integer(widget["x"], 0, 11, f"{label}.x")
        _integer(widget["y"], 0, MAX_ROWS - 1, f"{label}.y")
        _integer(widget["w"], min_w, 12, f"{label}.w")
        _integer(widget["h"], min_h, MAX_WIDGET_HEIGHT, f"{label}.h")
        if widget["x"] + widget["w"] > 12 or widget["y"] + widget["h"] > MAX_ROWS:
            raise UIPreferencesError(f"{label}: блок выходит за пределы сетки")
        for other in placed:
            if (widget["x"] < other["x"] + other["w"] and widget["x"] + widget["w"] > other["x"]
                    and widget["y"] < other["y"] + other["h"] and widget["y"] + widget["h"] > other["y"]):
                raise UIPreferencesError(f"{label}: блоки перекрываются")
        placed.append(widget)


def validate_settings(value: Any) -> dict[str, Any]:
    """Validate a full stored/imported document; partial files are not accepted."""
    _object(value, {"schemaVersion", "theme", "dashboard"}, "settings", complete=True)
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != SCHEMA_VERSION:
        raise UIPreferencesError("schemaVersion: неподдерживаемая версия настроек интерфейса")
    theme = _object(value["theme"], {"mode", "family", "base", "accent", "baseSaturation"}, "theme")
    if not {"mode", "family", "base", "accent"}.issubset(theme):
        raise UIPreferencesError("theme: отсутствуют обязательные поля")
    saturation=theme.get("baseSaturation",35)
    if type(saturation) is not int or not 0 <= saturation <= 100:
        raise UIPreferencesError("theme.baseSaturation: ожидается целое число от 0 до 100")
    _choice(theme["mode"], {"dark", "light"}, "theme.mode")
    _choice(theme["family"], {"monocrome", "palette", "vicwander"}, "theme.family")
    _choice(theme["base"], BASE_FAMILIES, "theme.base")
    _choice(theme["accent"], ACCENT_FAMILIES, "theme.accent")
    dashboard = _object(value["dashboard"], {"widgets"}, "dashboard", complete=True)
    _validate_widgets(dashboard["widgets"])
    result=copy.deepcopy(value)
    result["theme"]["baseSaturation"]=saturation
    return result


class UIPreferencesStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else SETTINGS_FILE

    def _read(self) -> dict[str, Any]:
        try:
            value = _load_json(self.path, None, retries=3, delay=0.01,
                               backup_dir=self.path.parent / "data" / "broken_json")
        except UnicodeError as error:
            raise UIPreferencesError("Файл настроек интерфейса содержит некорректный текст") from error
        if value is None and not self.path.exists():
            return default_settings()
        try:
            return validate_settings(value)
        except UIPreferencesError as error:
            raise UIPreferencesError("Файл настроек интерфейса повреждён или использует неподдерживаемую схему; оригинал сохранён") from error

    def load(self) -> dict[str, Any]:
        """Return validated settings/defaults without creating or erasing a file."""
        with LOCK:
            try:
                return self._read()
            except UIPreferencesError:
                return default_settings()

    def update(self, patch: Any) -> dict[str, Any]:
        """Merge sections and their fields under one lock, then atomically save."""
        _object(patch, {"schemaVersion", "theme", "dashboard"}, "settings")
        if "schemaVersion" in patch and (type(patch["schemaVersion"]) is not int or patch["schemaVersion"] != SCHEMA_VERSION):
            raise UIPreferencesError("schemaVersion: неподдерживаемая версия настроек интерфейса")
        for section, keys in (("theme", {"mode", "family", "base", "accent", "baseSaturation"}), ("dashboard", {"widgets"})):
            if section in patch:
                _object(patch[section], keys, section)
        # Detach mutable request objects before entering the transaction.
        patch = copy.deepcopy(patch)
        with LOCK:
            settings = self._read()
            for section in ("theme", "dashboard"):
                if section in patch:
                    settings[section].update(patch[section])
            settings = validate_settings(settings)
            _save_json(self.path, settings)
            return settings
