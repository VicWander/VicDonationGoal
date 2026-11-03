"""Real local HTTP requests against disposable project data; no workers/network."""
from __future__ import annotations

import http.client
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent


class PreviewAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vdg_preview_http_")
        cls.root = Path(cls.temp.name) / "app"
        shutil.copytree(ROOT, cls.root, ignore=shutil.ignore_patterns(
            "__pycache__", "runtime", "backups", "diagnostics", "audio_cache", "integration_inspector_reports"))
        for name, content in (("donations.json", []), ("state.json", {"title": "Fixture", "goal": 1000, "currency": "RUB", "current": 0}),
                              ("donor_profiles.json", []), ("donor_adjustments.json", [])):
            target = cls.root / "core/data" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(content), encoding="utf-8")
        (cls.root / "core/ui_settings.json").unlink(missing_ok=True)
        sys.path[:0] = [str(cls.root / "core"), str(cls.root)]
        with patch.dict(os.environ, {"VDG_PREVIEW": "1", "VDG_PORT": "3347"}):
            spec = importlib.util.spec_from_file_location("vdg_preview_fixture_server", cls.root / "core/server.py")
            cls.server = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.server)
        cls.server.UI_PREFERENCES=cls.server.UIPreferencesStore(cls.root / "core/ui_settings.json")
        cls.server.ensure_files()
        cls.http = cls.server.VicThreadingHTTPServer(("127.0.0.1", 0), cls.server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(3)
        cls.temp.cleanup()

    def request(self, method, path, value=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        try:
            body = None if value is None else json.dumps(value, ensure_ascii=False).encode("utf-8")
            connection.request(method, path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_environment_and_health(self):
        self.assertTrue(self.server.PREVIEW_MODE)
        self.assertEqual(self.server.PORT, 3347)
        code, result = self.request("GET", "/api/health")
        self.assertEqual(code, 200)
        self.assertTrue(result["preview"])

    def test_ui_settings_partial_updates_and_configured_flag(self):
        target = self.root / "core/ui_settings.json"
        target.unlink(missing_ok=True)
        code, result = self.request("GET", "/api/ui/settings")
        self.assertEqual(code, 200)
        self.assertFalse(result["configured"])
        self.assertEqual(result["settings"]["theme"]["family"], "monocrome")
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [pool.submit(self.request, "POST", "/api/ui/settings", value) for value in (
                {"theme": {"mode": "light", "accent": "mauve"}}, {"dashboard": {"widgets": []}})]
            for response in responses:
                self.assertEqual(response.result()[0], 200)
        _, result = self.request("GET", "/api/ui/settings")
        self.assertTrue(result["configured"])
        self.assertEqual(result["settings"]["theme"]["accent"], "mauve")
        self.assertEqual(result["settings"]["dashboard"]["widgets"], [])
        before = target.read_bytes()
        for payload in ({"theme": {"accent": "bad"}}, [], {"schemaVersion": 2}):
            self.assertEqual(self.request("POST", "/api/ui/settings", payload)[0], 400)
        self.assertEqual(target.read_bytes(), before)

    def test_ui_post_waits_for_import_file_lock(self):
        with self.server.FILE_LOCK, ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.request, "POST", "/api/ui/settings", {"theme": {"accent": "teal"}})
            # Release the outer lock before waiting for the pool on scope exit.
            try:
                import time
                time.sleep(0.08)
                self.assertFalse(future.done(), "UI POST ignored FILE_LOCK")
            finally:
                self.server.FILE_LOCK.release()
                try:
                    self.assertEqual(future.result()[0], 200)
                finally:
                    self.server.FILE_LOCK.acquire()

    def test_ui_post_rejects_invalid_json_without_creating_settings(self):
        target = self.root / "core/ui_settings.json"
        before = target.read_bytes() if target.exists() else None
        for raw in (b"{bad", b"theme=dark", b"\xff", b""):
            connection = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
            try:
                connection.request("POST", "/api/ui/settings", raw, {"Content-Type": "application/json"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 400)
            finally:
                connection.close()
        self.assertEqual(target.read_bytes() if target.exists() else None, before)

    def test_preview_blocks_all_outgoing_action_paths(self):
        paths = [("GET", p) for p in ("/auth/donationalerts/start", "/auth/donationalerts/callback?code=bad",
            "/auth/streamlabs/start", "/auth/streamlabs/callback?code=bad", "/api/tts/next", "/api/tts/audio/test.mp3")]
        paths += [("POST", p) for p in ("/api/tts/enqueue", "/api/tts/test", "/api/tts/job/retry", "/api/tts/control",
            "/api/tts/job/update", "/api/integrations/start", "/api/integrations/restart", "/api/integrations/enable",
            "/api/integrations/test", "/api/integrations/config", "/api/integrations/tribute/webhook/test",
            "/api/washington/test", "/api/washington/check", "/api/da/start", "/api/donation/replay")]
        with patch.object(self.server, "get_integration_manager", side_effect=AssertionError("action reached manager")), \
             patch.object(self.server.WASHINGTON, "test", side_effect=AssertionError("Washington started")), \
             patch.object(self.server.tts_store, "enqueue_job", side_effect=AssertionError("TTS enqueued")):
            for method, path in paths:
                with self.subTest(method=method, path=path):
                    code, result = self.request(method, path, {} if method == "POST" else None)
                    self.assertEqual(code, 423)
                    self.assertTrue(result["preview"])

    def test_preview_manual_donation_saves_without_outgoing_hooks(self):
        donation = {"source": "manual", "externalId": "preview-test", "username": "Fixture", "amount": 25,
                    "currency": "RUB", "includeInGoal": True, "includeInTop": True,
                    "notifyStreamerBot": True, "triggerDonationEvents": True, "speakTTS": True}
        with patch.object(self.server.WASHINGTON, "submit", side_effect=AssertionError("preview submitted Washington")):
            code, result = self.request("POST", "/api/donation", donation)
        self.assertEqual(code, 200)
        self.assertTrue(result["ok"])
        _, donations = self.request("GET", "/api/donations")
        saved = next(d for d in donations if d["externalId"] == "preview-test")
        for flag in ("notifyStreamerBot", "triggerDonationEvents", "speakTTS"):
            self.assertFalse(saved[flag])
        self.assertTrue(saved["includeInGoal"])
        self.assertTrue(saved["includeInTop"])

    def test_normal_mode_preserves_donation_flags_and_hook(self):
        donation = {"source": "manual", "externalId": "normal-test", "amount": 30, "currency": "RUB",
                    "notifyStreamerBot": True, "triggerDonationEvents": True, "speakTTS": True}
        with patch.object(self.server, "PREVIEW_MODE", False), patch.object(self.server.WASHINGTON, "submit") as submit:
            code, _ = self.request("POST", "/api/donation", donation)
            self.assertEqual(code, 200)
            submit.assert_called_once()
        _, donations = self.request("GET", "/api/donations")
        saved = next(d for d in donations if d["externalId"] == "normal-test")
        for flag in ("notifyStreamerBot", "triggerDonationEvents", "speakTTS"):
            self.assertTrue(saved[flag])

    def test_main_preview_does_not_initialize_or_start_workers(self):
        http_server = Mock()
        http_server.serve_forever.side_effect = KeyboardInterrupt
        with patch.object(self.server, "VicThreadingHTTPServer", return_value=http_server), \
             patch.object(self.server, "get_integration_manager") as manager, \
             patch.object(self.server.WASHINGTON, "start") as washington_start:
            self.server.main()
        manager.assert_not_called()
        washington_start.assert_not_called()
        http_server.server_close.assert_called_once()

    def test_preview_status_reads_catalog_without_registering_adapters(self):
        with patch.object(self.server, "DonationAlertsIntegration", side_effect=AssertionError("DA initialized")), \
             patch.object(self.server, "StreamlabsIntegration", side_effect=AssertionError("Streamlabs initialized")), \
             patch.object(self.server.IntegrationManager, "start_enabled", side_effect=AssertionError("integrations started")):
            self.server.INTEGRATION_MANAGER = None
            for path in ("/api/status", "/api/integrations", "/api/da/status"):
                self.assertEqual(self.request("GET", path)[0], 200)


if __name__ == "__main__":
    unittest.main()
