"""Offline validation of the UI preference store and portable backups."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "core")]

import portability
import ui_preferences as ui


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vdg_ui_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "core/ui_settings.json"
        self.store = ui.UIPreferencesStore(self.path)

    def test_defaults_are_independent_and_do_not_create_file(self):
        value = self.store.load()
        self.assertEqual(value["theme"], {"mode": "dark", "family": "monocrome", "base": "neutral", "accent": "neutral", "baseSaturation": 35})
        self.assertEqual([w["id"] for w in value["dashboard"]["widgets"]], ["connections", "latest", "goal", "manual"])
        value["dashboard"]["widgets"].clear()
        self.assertEqual(len(self.store.load()["dashboard"]["widgets"]), 4)
        self.assertFalse(self.path.exists())

    def test_updates_merge_nested_sections_and_empty_layout_survives_restart(self):
        self.store.update({"theme": {"mode": "light", "family": "palette", "accent": "rose"}})
        settings = self.store.update({"dashboard": {"widgets": []}})
        self.assertEqual(settings["theme"]["accent"], "rose")
        self.assertEqual(settings["theme"]["base"], "neutral")
        self.assertEqual(ui.UIPreferencesStore(self.path).load(), settings)
        self.assertEqual(settings["dashboard"]["widgets"], [])

    def test_all_supported_accents(self):
        for accent in ui.ACCENT_FAMILIES:
            with self.subTest(accent=accent):
                self.assertEqual(self.store.update({"theme": {"accent": accent}})["theme"]["accent"], accent)

    def test_rejects_malformed_patches_without_changing_saved_file(self):
        self.store.update({"theme": {"mode": "light"}})
        before = self.path.read_bytes()
        invalid = [None, [], {"unknown": 1}, {"theme": []}, {"theme": {"mode": "system"}},
                   {"theme": {"family": "monochrome"}}, {"theme": {"base": "unknown-palette"}},
                   {"theme": {"accent": "#ff0000"}}, {"theme": {"extra": 1}},
                   {"dashboard": None}, {"dashboard": {"other": []}}, {"schemaVersion": 2},
                   {"schemaVersion": True}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ui.UIPreferencesError):
                self.store.update(value)
            self.assertEqual(self.path.read_bytes(), before)

    def test_layout_validation(self):
        widget = {"id": "goal", "x": 0, "y": 0, "w": 4, "h": 4}
        invalid = [[widget, widget], [{**widget, "id": "unknown"}], [{**widget, "x": True}],
                   [{**widget, "x": 1.0}], [{**widget, "x": -1}], [{**widget, "x": 9}],
                   [{**widget, "h": 31}], [{**widget, "y": 129}], [{**widget, "w": 0}],
                   [{**widget, "type": "goal"}], [{"id": "goal"}], None,
                   [widget, {**widget, "id": "top", "h": 5}]]
        for widgets in invalid:
            with self.subTest(widgets=widgets), self.assertRaises(ui.UIPreferencesError):
                self.store.update({"dashboard": {"widgets": widgets}})
        adjacent = [widget, {**widget, "id": "top", "x": 4, "h": 5}]
        self.assertEqual(self.store.update({"dashboard": {"widgets": adjacent}})["dashboard"]["widgets"], adjacent)

    def test_concurrent_separate_store_instances_keep_both_sections(self):
        # Synchronize at transaction entry to stress the read/merge/write boundary.
        for _ in range(12):
            self.store.update(ui.default_settings())
            barrier = threading.Barrier(2)
            def update(value):
                barrier.wait()
                return ui.UIPreferencesStore(self.path).update(value)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(update, {"theme": {"accent": "teal"}}),
                           pool.submit(update, {"dashboard": {"widgets": []}})]
                for future in futures:
                    future.result()
            result = self.store.load()
            self.assertEqual(result["theme"]["accent"], "teal")
            self.assertEqual(result["dashboard"]["widgets"], [])

    def test_corrupt_or_future_file_fails_safe_without_erasing_it(self):
        self.path.parent.mkdir(parents=True)
        for content in (b"{broken", b"null", b"\xff", json.dumps({**ui.default_settings(), "schemaVersion": 2}).encode()):
            self.path.write_bytes(content)
            self.assertEqual(self.store.load(), ui.default_settings())
            self.assertEqual(self.path.read_bytes(), content)
            with self.assertRaises(ui.UIPreferencesError):
                self.store.update({"theme": {"mode": "light"}})
            self.assertEqual(self.path.read_bytes(), content)

    def test_failed_replace_preserves_previous_file_and_cleans_temp(self):
        self.store.update({"theme": {"mode": "light"}})
        before = self.path.read_bytes()
        import safe_json
        original_save = safe_json.save_json
        def fast_save(path, data):
            return original_save(path, data, retries=1)
        with patch.object(ui, "_save_json", fast_save), patch("safe_json.os.replace", side_effect=PermissionError("busy")):
            with self.assertRaises(PermissionError):
                self.store.update({"theme": {"accent": "teal"}})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_backup_folder_roundtrip_and_strict_path_allowlist(self):
        saved = self.store.update({"theme": {"mode": "light", "accent": "violet"}, "dashboard": {"widgets": []}})
        data, manifest = portability.create_backup_bytes(self.root)
        self.assertIn("core/ui_settings.json", [entry["path"] for entry in manifest["files"]])
        self.assertEqual(portability.category_for_path("core/ui_settings.json"), "ui_preferences")
        _, files = portability.inspect_backup_bytes(data)
        destination = self.root / "restore"
        portability.apply_payload(destination, files)
        self.assertEqual(ui.UIPreferencesStore(destination / "core/ui_settings.json").load(), saved)
        self.assertEqual(portability.normalize_old_relative_path("old/core/ui_settings.json"), "core/ui_settings.json")
        for name in ("core/server.py", "core/other.json", "core/ui_settings.json.bak", "core/../ui_settings.json"):
            self.assertFalse(portability.is_user_data_path(name))

    def test_backup_rejects_invalid_or_future_preferences_before_writing(self):
        self.store.update({"theme": {"accent": "cyan"}})
        before = self.path.read_bytes()
        for settings in ({"schemaVersion": 1}, {**ui.default_settings(), "schemaVersion": 2},
                         {**ui.default_settings(), "theme": {"mode": "bad"}}):
            payload = {"core/ui_settings.json": json.dumps(settings).encode()}
            with self.assertRaises(portability.PortabilityError):
                portability.validate_user_payload(payload)
            with self.assertRaises(portability.PortabilityError):
                portability.apply_payload(self.root, payload)
            self.assertEqual(self.path.read_bytes(), before)

    def test_restore_and_partial_update_share_transaction_lock(self):
        self.store.update({"theme": {"mode": "light"}})
        restored = ui.default_settings()
        restored["dashboard"]["widgets"] = []
        entered = threading.Event()
        release = threading.Event()
        update_done = threading.Event()
        original_write = portability._atomic_write
        def blocked_write(path, data):
            entered.set()
            if not release.wait(3):
                raise AssertionError("restore was not released")
            original_write(path, data)
        def update():
            result = self.store.update({"theme": {"accent": "teal"}})
            update_done.set()
            return result
        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(portability, "_atomic_write", blocked_write):
            restore_future = pool.submit(portability.apply_payload, self.root,
                                         {"core/ui_settings.json": json.dumps(restored).encode()})
            self.assertTrue(entered.wait(3))
            update_future = pool.submit(update)
            try:
                self.assertFalse(update_done.wait(0.1), "UI update raced the restore transaction")
            finally:
                release.set()
            restore_future.result()
            update_future.result()
        result = self.store.load()
        self.assertEqual(result["theme"]["accent"], "teal")
        self.assertEqual(result["dashboard"]["widgets"], [])

    def test_expanded_dashboard_modules_roundtrip_and_minimums(self):
        expected = {"summary": (4, 3), "rates": (4, 5), "ttsQueue": (4, 5),
                    "ttsTest": (4, 6), "ttsHistory": (4, 5), "services": (4, 4)}
        widgets = []
        y = 0
        for widget_id, (width, height) in ui.WIDGET_MINIMUMS.items():
            widgets.append({"id": widget_id, "x": 0, "y": y, "w": width, "h": height})
            y += height
        saved = self.store.update({"dashboard": {"widgets": widgets}})
        self.assertEqual(len(saved["dashboard"]["widgets"]), 12)
        self.assertEqual(ui.UIPreferencesStore(self.path).load(), saved)
        before = self.path.read_bytes()
        for widget_id, minimum in expected.items():
            self.assertEqual(ui.WIDGET_MINIMUMS[widget_id], minimum)
            valid = {"id": widget_id, "x": 0, "y": 0, "w": minimum[0], "h": minimum[1]}
            for key in ("w", "h"):
                with self.subTest(widget_id=widget_id, key=key), self.assertRaises(ui.UIPreferencesError):
                    self.store.update({"dashboard": {"widgets": [{**valid, key: valid[key] - 1}]}})
            self.assertEqual(self.path.read_bytes(), before)

    def test_old_layout_coordinates_are_not_reset_or_compacted_on_load(self):
        old = ui.default_settings()
        old["dashboard"]["widgets"] = [
            {"id": "goal", "x": 8, "y": 17, "w": 4, "h": 4},
            {"id": "speech", "x": 0, "y": 42, "w": 4, "h": 6},
        ]
        self.store.update(old)
        self.assertEqual(ui.UIPreferencesStore(self.path).load(), old)


if __name__ == "__main__":
    unittest.main()
