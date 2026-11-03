"""End-to-end Studio checks against a disposable, preview-only Core fixture.

Requires Playwright and a cached Chromium or installed Microsoft Edge. All browser
requests outside the fixture origin are blocked; no integration worker starts.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect, Error

ROOT = Path(__file__).resolve().parent.parent
MESSAGE = '<img src="x" onerror="window.fixtureXSS=true"> ' + "Длинное сообщение для проверки раскрытия. " * 8
USERNAME = '<svg id="fixture-injected" onload="window.fixtureXSS=true">'
ROUTES = {
    "home": ["dashboard"],
    "donations": ["history", "top", "goal", "manual", "rates"],
    "widget": ["editor", "presets", "obs"],
    "tts": ["queue", "profiles", "rules", "providers", "history", "logs"],
    "integrations": ["services", "streamerbot"],
    "settings": ["appearance", "data", "diagnostics"],
}


class StudioBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vdg_studio_browser_")
        cls.root = Path(cls.temp.name) / "app"
        shutil.copytree(ROOT, cls.root, ignore=shutil.ignore_patterns(
            "__pycache__", "runtime", "backups", "diagnostics", "audio_cache", "integration_inspector_reports"))
        data = cls.root / "core/data"
        data.mkdir(parents=True, exist_ok=True)
        fixtures = {
            "state.json": {"title": "Browser Fixture", "goal": 1000, "current": 0, "baseAmount": 0, "currency": "RUB"},
            "donations.json": [
                {"uniqueKey": "manual:browser-long", "source": "manual", "externalId": "browser-long", "username": USERNAME,
                 "message": MESSAGE, "amount": 50, "currency": "RUB", "receivedAt": "not-a-date", "includeInGoal": True,
                 "notifyStreamerBot": False, "triggerDonationEvents": False, "speakTTS": False, "includeInTop": True},
                {"uniqueKey": "manual:browser-short", "source": "manual", "externalId": "browser-short", "username": "Short Fixture",
                 "message": "Короткое сообщение", "amount": 10, "currency": "RUB", "receivedAt": "2026-10-20T12:00:00+00:00",
                 "notifyStreamerBot": False, "triggerDonationEvents": False, "speakTTS": False}],
            "donor_profiles.json": [], "donor_adjustments.json": [],
        }
        for name, content in fixtures.items():
            (data / name).write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        (cls.root / "core/ui_settings.json").unlink(missing_ok=True)
        (cls.root / "core/widget_settings.json").unlink(missing_ok=True)
        sys.path[:0] = [str(cls.root / "core"), str(cls.root)]
        with patch.dict(os.environ, {"VDG_PREVIEW": "1", "VDG_PORT": "3347"}):
            spec = importlib.util.spec_from_file_location("vdg_studio_browser_server", cls.root / "core/server.py")
            cls.server = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.server)
        cls.server.UI_PREFERENCES=cls.server.UIPreferencesStore(cls.root / "core/ui_settings.json")
        cls.server.ensure_files()
        cls.server.normalize_storage()
        class FixtureHTTPServer(cls.server.VicThreadingHTTPServer):
            def handle_error(self, request, client_address):
                # Reload/close can cancel an in-flight periodic status response.
                if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
                    return
                super().handle_error(request, client_address)
        cls.http = FixtureHTTPServer(("127.0.0.1", 0), cls.server.Handler)
        cls.origin = f"http://127.0.0.1:{cls.http.server_port}"
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Error:
            cls.browser = cls.playwright.chromium.launch(channel="msedge", headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(3)
        cls.temp.cleanup()

    def setUp(self):
        with self.server.FILE_LOCK:
            self.server.UI_PREFERENCES.path.unlink(missing_ok=True)
        self.context = self.browser.new_context(viewport={"width": 1500, "height": 1000}, reduced_motion="reduce")
        self.external_requests = []
        def only_fixture(route):
            if route.request.url.startswith(self.origin + "/"):
                route.continue_()
            else:
                self.external_requests.append(route.request.url)
                route.abort()
        self.context.route("**/*", only_fixture)
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.page_errors = []
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.goto(self.origin + "/admin.html#home/dashboard")
        self.page.evaluate("async () => { await window.VDGDashboard.ready; await window.VDGThemes.ready; }")
        expect(self.page.locator('[data-route="home/dashboard"]')).to_be_visible()
        self.page.wait_for_function("document.querySelectorAll('#studioLatest [data-studio-record]').length >= 2")

    def tearDown(self):
        try:
            duplicates = self.page.evaluate("""() => {const seen=new Set();return [...document.querySelectorAll('[id]')].filter(el=>seen.has(el.id)||!seen.add(el.id)).map(el=>el.id);} """)
            self.assertEqual(duplicates, [], "Duplicate live DOM IDs")
            self.assertEqual(self.page_errors, [], "Uncaught JavaScript errors")
            self.assertEqual(self.external_requests, [], "UI attempted an external network request")
            self.assertFalse(self.page.evaluate("Boolean(window.fixtureXSS)"), "Fixture text executed as HTML")
            self.assertEqual(self.page.locator("#fixture-injected").count(), 0)
        finally:
            self.context.close()

    def navigate(self, route):
        self.page.keyboard.press("Escape")
        section, subsection = route.split("/")
        self.page.locator(f'.studio-nav-link[href="#{section}/{ROUTES[section][0]}"]').click()
        if subsection != ROUTES[section][0]:
            self.page.locator(f'.studio-subnav a[href="#{route}"]').click()
        expect(self.page.locator(f'[data-route="{route}"]')).to_be_visible()

    def test_all_routes_providers_and_file_import_controls(self):
        for section, pages in ROUTES.items():
            for subsection in pages:
                with self.subTest(route=f"{section}/{subsection}"):
                    self.navigate(f"{section}/{subsection}")
                    self.assertEqual(self.page.locator(".studio-view:visible").count(), 1)
        self.navigate("tts/providers")
        for selector in ("#speakerUrlInput", "#edgeVoiceInput", "#yandexEndpointInput", "#xttsEndpointInput", "#httpUrlInput"):
            expect(self.page.locator(selector)).to_be_visible()
        self.navigate("settings/data")
        for selector in ("#backupRestoreInput", "#oldVersionFolderInput", "#donationsImportInput", "#donationAlertsImportInput"):
            expect(self.page.locator(selector)).to_be_visible()

    def test_manual_form_values_survive_routes_dashboard_cancel_and_real_submit(self):
        self.navigate("donations/manual")
        self.page.locator("#usernameInput").fill("Browser Manual Saved")
        self.page.locator("#amountInput").fill("123")
        self.page.locator("#messageInput").fill("Browser fixture manual donation")
        flags = {"includeInput": False, "notifyInput": True, "eventInput": False, "speakInput": True, "includeTopInput": True}
        for element_id, checked in flags.items():
            self.page.locator("#" + element_id).set_checked(checked)
        self.navigate("tts/providers")
        self.navigate("home/dashboard")
        expect(self.page.locator("#usernameInput")).to_have_value("Browser Manual Saved")
        self.page.locator('[data-board-action="edit"]').click()
        self.page.locator('[data-board-action="remove"][data-id="manual"]').click()
        self.page.locator('[data-board-action="cancel"]').click()
        expect(self.page.locator("#usernameInput")).to_have_value("Browser Manual Saved")
        self.navigate("donations/manual")
        for element_id, checked in flags.items():
            self.assertEqual(self.page.locator("#" + element_id).is_checked(), checked)
        with self.page.expect_response(lambda response: response.url.endswith("/api/donation") and response.request.method == "POST") as response:
            self.page.locator("#addDonationButton").click()
        self.assertEqual(response.value.status, 200)
        submitted = response.value.request.post_data_json
        for field, expected in {"includeInGoal": False, "notifyStreamerBot": True, "triggerDonationEvents": False, "speakTTS": True, "includeInTop": True}.items():
            self.assertEqual(submitted[field], expected)
        rows = self.page.request.get(self.origin + "/api/donations").json()
        saved = next(row for row in rows if row["username"] == "Browser Manual Saved")
        self.assertEqual(saved["amount"], 123)
        self.assertFalse(saved["includeInGoal"])
        self.assertTrue(saved["includeInTop"])
        for field in ("notifyStreamerBot", "triggerDonationEvents", "speakTTS"):
            self.assertFalse(saved[field], "Preview must suppress outgoing effects")

    def test_dashboard_and_theme_save_survive_reload(self):
        self.page.locator('[data-board-action="edit"]').click()
        self.page.locator('[data-board-action="remove"][data-id="manual"]').click()
        with self.page.expect_response(lambda r: r.url.endswith("/api/ui/settings") and r.request.method == "POST") as response:
            self.page.locator('[data-board-action="save"]').click()
        self.assertEqual(response.value.status, 200)
        expect(self.page.locator('[data-board-action="edit"]')).to_be_visible()
        saved_layout = self.page.request.get(self.origin + "/api/ui/settings").json()["settings"]["dashboard"]
        self.assertNotIn("manual", [w["id"] for w in saved_layout["widgets"]])
        self.navigate("settings/appearance")
        form = self.page.locator("#studioAppearanceSettings .studio-theme-form")
        form.locator('[name="family"]').select_option("palette")
        form.locator('[name="mode"]').select_option("light")
        form.locator('[name="base"]').select_option("slate")
        form.locator('[name="accent"]').select_option("mauve")
        with self.page.expect_response(lambda r: r.url.endswith("/api/ui/settings") and r.request.method == "POST") as response:
            form.locator("[data-theme-save]").click()
        self.assertEqual(response.value.status, 200)
        self.page.reload()
        self.page.evaluate("async () => { await window.VDGDashboard.ready; await window.VDGThemes.ready; }")
        theme = self.page.evaluate("window.VDGThemes.get()")
        self.assertEqual(theme, {"mode": "light", "family": "palette", "base": "slate", "accent": "mauve", "baseSaturation": 35})
        self.navigate("home/dashboard")
        self.assertEqual(self.page.locator('[data-block="manual"]').count(), 0)
        current = self.page.request.get(self.origin + "/api/ui/settings").json()["settings"]
        self.assertEqual(current["dashboard"], saved_layout)

    def test_delayed_dashboard_load_and_save_preserve_active_manual_form(self):
        pending_reads = []
        def delay_read(route):
            if route.request.method == "GET":
                pending_reads.append(route)
            else:
                route.continue_()
        pattern = "**/api/ui/settings"
        self.page.route(pattern, delay_read)
        # A query forces a real navigation rather than a same-document hash change.
        self.page.goto(self.origin + "/admin.html?delayed-ui=1#donations/manual")
        expect(self.page.locator('[data-route="donations/manual"]')).to_be_visible()
        expect(self.page.locator("#usernameInput")).to_be_visible()
        self.page.locator("#usernameInput").fill("Draft during delayed UI load")
        self.assertGreaterEqual(len(pending_reads), 1)
        for route in pending_reads:
            route.continue_()
        self.page.evaluate("async () => { await window.VDGDashboard.ready; await window.VDGThemes.ready; }")
        expect(self.page.locator("#usernameInput")).to_be_visible()
        expect(self.page.locator("#usernameInput")).to_have_value("Draft during delayed UI load")
        expect(self.page.locator("#addDonationButton")).to_be_visible()
        self.page.unroute(pattern, delay_read)

        self.navigate("home/dashboard")
        self.page.locator('[data-board-action="edit"]').click()
        pending_writes = []
        def delay_write(route):
            if route.request.method == "POST":
                pending_writes.append(route)
            else:
                route.continue_()
        self.page.route(pattern, delay_write)
        self.page.locator('[data-board-action="save"]').click()
        self.navigate("donations/manual")
        expect(self.page.locator("#usernameInput")).to_be_visible()
        self.page.locator("#usernameInput").fill("Draft during pending dashboard save")
        self.assertEqual(len(pending_writes), 1)
        with self.page.expect_response(lambda r: r.url.endswith("/api/ui/settings") and r.request.method == "POST") as response:
            pending_writes[0].continue_()
        self.assertEqual(response.value.status, 200)
        self.page.wait_for_function("!window.VDGDashboard.isEditing()")
        expect(self.page.locator('[data-route="donations/manual"]')).to_be_visible()
        expect(self.page.locator("#usernameInput")).to_be_visible()
        expect(self.page.locator("#usernameInput")).to_have_value("Draft during pending dashboard save")
        expect(self.page.locator("#addDonationButton")).to_be_visible()
        self.page.unroute(pattern, delay_write)

    def test_latest_drawer_and_history_row_toggle_escape_and_invalid_date(self):
        row = self.page.locator('[data-studio-record="manual:browser-long"]')
        expect(row).to_contain_text(USERNAME)
        row.click()
        expect(self.page.locator("#studioDonationDetail")).to_be_visible()
        expect(self.page.locator("#studioDonationDetail")).to_contain_text(MESSAGE)
        row.click()
        expect(self.page.locator("#studioDonationDetail")).to_be_hidden()
        self.navigate("donations/history")
        entry = self.page.locator('.donation-entry[data-key="manual:browser-long"]')
        expect(entry).to_be_visible()
        entry.locator(".donation-user").click()
        expect(entry).to_have_class(re.compile(r"\bexpanded\b"))
        expect(entry.locator(".donation-expanded-message")).to_be_visible()
        entry.locator(".donation-user").click()
        expect(entry.locator(".donation-expanded-message")).to_be_hidden()

    def test_pointer_drag_resize_and_keyboard_changes_save_to_core(self):
        self.page.locator('[data-board-action="edit"]').click()
        grid = self.page.locator(".dashboard-grid")
        self.assertEqual(grid.evaluate("el=>getComputedStyle(el).display"), "grid")
        steps = grid.evaluate("""el=>{const s=getComputedStyle(el);return {
            x:(el.getBoundingClientRect().width+parseFloat(s.columnGap))/12,
            y:parseFloat(s.gridAutoRows)+parseFloat(s.rowGap)}}""")
        def drag(selector, dx, dy):
            handle = self.page.locator(selector)
            handle.scroll_into_view_if_needed()
            bounds = handle.bounding_box()
            self.assertIsNotNone(bounds)
            x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
            self.page.mouse.move(x, y)
            self.page.mouse.down()
            self.page.mouse.move(x + dx, y + dy, steps=8)
            self.page.mouse.up()
        drag('[data-drag="goal"]', -2 * steps["x"], 2 * steps["y"])
        goal = self.page.evaluate("window.VDGDashboard.get().widgets.find(w=>w.id==='goal')")
        # Horizontal move is retained; automatic gravity removes the empty rows.
        self.assertEqual((goal["x"], goal["y"]), (6, 2))
        drag('[data-resize="goal"]', steps["x"], steps["y"])
        goal = self.page.evaluate("window.VDGDashboard.get().widgets.find(w=>w.id==='goal')")
        self.assertEqual((goal["w"], goal["h"]), (5, 5))
        self.page.locator('[data-drag="goal"]').focus()
        self.page.keyboard.press("ArrowLeft")
        self.page.locator('[data-resize="goal"]').focus()
        self.page.keyboard.press("ArrowDown")
        goal = self.page.evaluate("window.VDGDashboard.get().widgets.find(w=>w.id==='goal')")
        self.assertEqual((goal["x"], goal["h"]), (5, 6))
        with self.page.expect_response(lambda r: r.url.endswith("/api/ui/settings") and r.request.method == "POST") as response:
            self.page.locator('[data-board-action="save"]').click()
        self.assertEqual(response.value.status, 200)
        settings = self.page.request.get(self.origin + "/api/ui/settings").json()["settings"]
        self.assertEqual(next(w for w in settings["dashboard"]["widgets"] if w["id"] == "goal"), goal)

    def test_light_wide_and_narrow_routes_do_not_overflow(self):
        self.page.evaluate("window.VDGThemes.apply({mode:'light',family:'palette',base:'neutral',accent:'sky'})")
        failures = []
        for width in (1500, 768, 390):
            self.page.set_viewport_size({"width": width, "height": 900})
            for route in ("home/dashboard", "donations/history", "donations/manual", "tts/providers", "settings/data", "settings/appearance"):
                self.navigate(route)
                sizes = self.page.evaluate("({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth})")
                if sizes["document"] > width + 2 or sizes["body"] > width + 2:
                    culprit = self.page.evaluate("""() => [...document.querySelectorAll('.studio-view:not([hidden]) *')]
                        .filter(el=>el.getClientRects().length&&el.getBoundingClientRect().right>innerWidth+2)
                        .slice(0,8).map(el=>({id:el.id,tag:el.tagName,cls:el.className,
                            right:Math.round(el.getBoundingClientRect().right),minWidth:getComputedStyle(el).minWidth}))""")
                    failures.append({"width": width, "route": route, **sizes, "culprits": culprit})
        self.assertEqual(failures, [], "Horizontal overflow")


if __name__ == "__main__":
    unittest.main()
