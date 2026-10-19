from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "core")]
import portability
from tools.test_portability import sample_project, write_json

spec = importlib.util.spec_from_file_location("file_safety_server", ROOT / "core/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class FileSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="vic_file_safety_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def isolated_server(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        sample_project(self.root)
        for key, value in {
            "PROJECT_ROOT": self.root,
            "DATA_DIR": self.root / "core/data",
            "STATE_FILE": self.root / "core/data/state.json",
            "DONATIONS_FILE": self.root / "core/data/donations.json",
            "RATES_FILE": self.root / "core/data/rates.json",
            "BROKEN_JSON_DIR": self.root / "backups/broken_json",
        }.items():
            stack.enter_context(patch.object(server, key, value))
        for key, value in {
            "DATA_DIR": self.root / "core/data",
            "PROFILES_FILE": self.root / "core/data/donor_profiles.json",
            "ADJUSTMENTS_FILE": self.root / "core/data/donor_adjustments.json",
        }.items():
            stack.enter_context(patch.object(server.donor_store, key, value))
        return stack

    def request_static(self, path):
        public = self.root / "public"
        public.mkdir(exist_ok=True)
        (public / "admin.html").write_bytes(b"public page")
        (public / "space name.txt").write_bytes(b"space file")
        (self.root / "private.txt").write_bytes(b"private-marker")
        handler = object.__new__(server.Handler)
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        with patch.object(server, "PUBLIC", public):
            handler.serve_static(path)
        return handler.send_response.call_args.args[0], handler.wfile.getvalue()

    def test_static_cannot_read_outside_public(self):
        for path in ["/../private.txt", "/%2e%2e/private.txt", "/..\\private.txt", "/%2e%2e%5cprivate.txt"]:
            with self.subTest(path=path):
                code, body = self.request_static(path)
                self.assertNotEqual(code, 200)
                self.assertNotIn(b"private-marker", body)

    def test_normal_and_encoded_public_files_still_work(self):
        self.assertEqual(self.request_static("/admin.html"), (200, b"public page"))
        self.assertEqual(self.request_static("/space%20name.txt"), (200, b"space file"))

    def test_import_paths_are_relative_and_safe_on_windows(self):
        for path in ["/core/data/state.json", "\\core\\data\\state.json", "integrations/tts/voices/C:/file.wav",
                     "integrations/tts/voices/sample.wav:stream", "integrations/tts/voices/NUL.wav",
                     "integrations/donatty/bad*.json"]:
            with self.subTest(path=path):
                self.assertFalse(portability.is_user_data_path(path))
        self.assertTrue(portability.is_user_data_path("core/data/state.json"))
        self.assertTrue(portability.is_user_data_path("integrations/tts/voices/voice.wav"))

    def test_donation_rows_are_validated_in_every_import_format(self):
        for row in ["invalid-row", {"uniqueKey": "manual:x", "amount": "NaN"},
                    {"uniqueKey": "manual:x", "amount": {"bad": 10}}, {"uniqueKey": "manual:x"},
                    {"source": "manual", "amount": 10}]:
            raw = encoded([row])
            with self.subTest(row=row), self.assertRaises(portability.PortabilityError):
                portability.validate_user_payload({"core/data/donations.json": raw})
            with self.subTest(standalone=row), self.assertRaises(portability.PortabilityError):
                portability.parse_donations_bytes(raw)

    def test_legacy_numeric_strings_and_external_ids_are_accepted(self):
        row = {"source": "donationalerts", "external_id": 123, "amount": "12,50", "currency": "RUB"}
        self.assertEqual(portability.parse_donations_bytes(encoded([row])), [row])
        portability.validate_user_payload({"core/data/donor_adjustments.json": encoded([
            {"id": "adjustment-1", "donorId": "donor-1", "amount": -50, "amountForTop": -50},
        ])})

    def test_invalid_profiles_and_configs_are_rejected(self):
        for path, value in [
            ("core/data/donor_profiles.json", [{"id": "donor-1", "aliases": "invalid"}]),
            ("integrations/tts/tts_queue.json", ["invalid"]),
            ("integrations/donatty/donatty_config.json", []),
        ]:
            with self.subTest(path=path), self.assertRaises(portability.PortabilityError):
                portability.validate_user_payload({path: encoded(value)})

    def test_non_finite_json_numbers_are_rejected(self):
        with self.assertRaises(portability.PortabilityError):
            portability.validate_user_payload({"core/data/state.json": b'{"goal":NaN}'})

    def test_apply_validates_all_files_before_writing_any(self):
        path = self.root / "core/data/state.json"
        write_json(path, {"title": "Original", "goal": 100})
        original = path.read_bytes()
        payload = {
            "core/data/state.json": encoded({"title": "Changed", "goal": 200}),
            "integrations/donatty/donatty_config.json": b"[]",
        }
        with self.assertRaises(portability.PortabilityError):
            portability.apply_payload(self.root, payload)
        self.assertEqual(path.read_bytes(), original)

    def test_partial_io_failure_restores_old_and_removes_new_files(self):
        existing = self.root / "core/data/state.json"
        write_json(existing, {"title": "Original", "goal": 100})
        original = existing.read_bytes()
        created = self.root / "core/data/rates.json"
        payload = {"core/data/rates.json": encoded({"ratesToRUB": {"RUB": 1}}),
                   "core/data/state.json": encoded({"goal": 200}),
                   "integrations/donatty/donatty_config.json": encoded({"enabled": False})}
        atomic_write = portability._atomic_write

        def fail_last(path, content):
            if path.name == "donatty_config.json":
                raise OSError("synthetic write failure")
            return atomic_write(path, content)

        with patch.object(portability, "_atomic_write", side_effect=fail_last):
            with self.assertRaises((OSError, portability.PortabilityError)):
                portability.apply_payload(self.root, payload)
        self.assertEqual(existing.read_bytes(), original)
        self.assertFalse(created.exists())

    def test_backup_hashes_match_the_exact_archived_bytes(self):
        sample_project(self.root)
        path = self.root / "core/data/donations.json"
        original = path.read_bytes()
        real_write = zipfile.ZipFile.writestr

        def change_after_manifest(archive, name, data, *args, **kwargs):
            result = real_write(archive, name, data, *args, **kwargs)
            if name == "manifest.json":
                write_json(path, [{"uniqueKey": "manual:new", "amount": 250}])
            return result

        with patch.object(zipfile.ZipFile, "writestr", new=change_after_manifest):
            raw, _ = portability.create_backup_bytes(self.root)
        _, payload = portability.inspect_backup_bytes(raw)
        self.assertEqual(payload["core/data/donations.json"], original)

    def test_changing_files_do_not_produce_an_inconsistent_backup(self):
        sample_project(self.root)
        path = self.root / "core/data/state.json"
        real_read = Path.read_bytes
        counter = [0]

        def changing_read(p):
            content = real_read(p)
            if p == path:
                counter[0] += 1
                write_json(path, {"goal": 1000, "current": counter[0]})
            return content

        with patch.object(Path, "read_bytes", new=changing_read):
            with self.assertRaises(portability.PortabilityError):
                portability.create_backup_bytes(self.root)

    def test_restore_rejects_a_newer_major_version(self):
        sample_project(self.root)
        raw, _ = portability.create_backup_bytes(self.root)
        source = zipfile.ZipFile(io.BytesIO(raw))
        output = io.BytesIO()
        with source, zipfile.ZipFile(output, "w") as target:
            for name in source.namelist():
                data = source.read(name)
                if name == "manifest.json":
                    manifest = json.loads(data)
                    manifest["appVersion"] = "2.0.0"
                    data = encoded(manifest)
                target.writestr(name, data)
        with self.assertRaises(portability.PortabilityError):
            portability.backup_preview(output.getvalue(), "1.4.6")

    def test_backup_id_cannot_select_another_windows_drive(self):
        with patch.object(Path, "is_file", return_value=True):
            with self.assertRaises(portability.PortabilityError):
                portability.resolve_local_backup(self.root, "manual/D:elsewhere.zip")

    def test_backup_that_exceeds_restore_limit_is_not_returned(self):
        sample_project(self.root)
        with patch.object(portability, "MAX_UPLOAD_BYTES", 1):
            with self.assertRaises(portability.PortabilityError):
                portability.create_backup_bytes(self.root)

    def test_manual_backup_holds_the_core_data_lock(self):
        class Lock:
            held = False
            def __enter__(self): self.held = True
            def __exit__(self, *args): self.held = False

        lock = Lock()
        archive = self.root / "backup.zip"
        archive.write_bytes(b"synthetic-backup")

        def capture(*args, **kwargs):
            self.assertTrue(lock.held, "Donation writes must wait until the snapshot is captured")
            return archive, {"schemaVersion": 1}

        handler = object.__new__(server.Handler)
        handler.path = "/api/portability/backup"
        handler.headers = {"Host": "127.0.0.1"}
        handler.send_json = Mock()
        handler.send_bytes = Mock()
        with patch.object(server, "FILE_LOCK", lock), patch.object(portability, "write_backup", side_effect=capture):
            handler.do_GET()
        self.assertTrue(handler.send_bytes.called)
        self.assertFalse(handler.send_json.called)

    def test_manifest_is_included_in_backup_limits(self):
        sample_project(self.root)
        files = portability.collect_user_files(self.root)
        with patch.object(portability, "MAX_ARCHIVE_FILES", len(files)):
            with self.assertRaises(portability.PortabilityError):
                portability.create_backup_bytes(self.root)
        with patch.object(portability, "MAX_ARCHIVE_BYTES", sum(p.stat().st_size for p in files)):
            with self.assertRaises(portability.PortabilityError):
                portability.create_backup_bytes(self.root)

    def test_rate_changes_wait_for_the_import_lock(self):
        class Lock:
            held = False
            def __enter__(self): self.held = True
            def __exit__(self, *args): self.held = False

        lock = Lock()
        handler = object.__new__(server.Handler)
        handler.path = "/api/rates"
        handler.headers = {"Host": "127.0.0.1"}
        handler.read_body_json = Mock(return_value={})
        handler.send_json = Mock()

        def save(*args):
            self.assertTrue(lock.held, "Rate writes must wait until the import/rollback finishes")
            return {}

        with patch.object(server, "FILE_LOCK", lock), patch.object(server, "save_rates", side_effect=save), \
             patch.object(server, "load_json", return_value={}), patch.object(server, "save_json"), \
             patch.object(server, "recalc_goal_current"):
            handler.do_POST()
        self.assertTrue(handler.send_json.called)

    def test_adjustment_comma_amount_is_rejected_before_it_can_become_zero(self):
        with self.assertRaises(portability.PortabilityError):
            portability.validate_user_payload({"core/data/donor_adjustments.json": encoded([
                {"id": "adjustment-1", "donorId": "donor-1", "amount": "12,50"}
            ])})

    def test_late_import_failure_removes_files_absent_before_import(self):
        self.isolated_server()
        server.normalize_storage()
        before = {p: p.read_bytes() for p in portability.collect_user_files(self.root)}
        relative = "integrations/new_service/config.json"
        token = portability.create_folder_stage(self.root, {relative: encoded({"enabled": True})}, {})
        real_normalize = server.normalize_storage
        calls = []

        def fail_once():
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError("synthetic late normalization failure")
            return real_normalize()

        with patch.object(server, "normalize_storage", side_effect=fail_once):
            with self.assertRaises(portability.PortabilityError):
                server.apply_staged_import(token)
        self.assertFalse((self.root / relative).exists())
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content, str(path))

    def test_failed_import_cannot_erase_a_concurrent_donation(self):
        self.isolated_server()
        attempted = threading.Event()
        completed = threading.Event()
        writer = []
        failures = []
        real_inspect = portability.inspect_backup_bytes

        def donate():
            attempted.set()
            try:
                server.add_donation({"uniqueKey": "manual:concurrent", "source": "manual", "amount": 100})
            except Exception as error:
                failures.append(error)
            finally:
                completed.set()

        def inspect_during_rollback(*args, **kwargs):
            thread = threading.Thread(target=donate)
            writer.append(thread)
            thread.start()
            self.assertTrue(attempted.wait(1))
            # On the old code this donation completed in the unlocked rollback
            # window, and the restore immediately erased it.
            completed.wait(0.2)
            return real_inspect(*args, **kwargs)

        token = portability.create_stage(self.root, "unknown", "bad.bin", b"bad", {})
        with patch.object(portability, "inspect_backup_bytes", side_effect=inspect_during_rollback):
            with self.assertRaises(portability.PortabilityError):
                server.apply_staged_import(token)
        for thread in writer:
            thread.join(timeout=3)
        self.assertTrue(completed.is_set())
        self.assertEqual(failures, [])
        rows = json.loads((self.root / "core/data/donations.json").read_text(encoding="utf-8"))
        self.assertIn("manual:concurrent", {row.get("uniqueKey") for row in rows})


if __name__ == "__main__":
    unittest.main(verbosity=2)
