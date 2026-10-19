from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from integrations.donationalerts import donationalerts_integration as da
from integrations.donatty import donatty_listener as dt
from tools.test_donationalerts_reliability import create_integration


def publication(event_id):
    return {"result": {"channel": "$alerts:donation_1", "data": {"data": {
        "id": event_id, "username": "Test", "amount": 10, "currency": "RUB",
    }}}}


class TransportTests(unittest.TestCase):
    def test_standard_donatty_widget_connects_without_browser(self):
        calls = []

        class Response:
            status_code = 200
            def json(self): return {"response": {"accessToken": "fresh-sse-token"}}

        class Session:
            trust_env = True
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def get(self, url, **kwargs):
                calls.append((url, self.trust_env))
                return Response()

        cfg = {"widget_url": "https://widgets.donatty.com/donations/?ref=00000000-0000-0000-0000-00000000005e&token=private-widget-token"}
        fake = types.SimpleNamespace(Session=Session)
        with patch.object(dt, "requests", fake), patch.object(dt, "write_status"), \
             patch.object(dt, "capture_sse_url_with_browser", return_value="browser-fallback") as browser:
            url = dt.resolve_sse_url(cfg)
        self.assertFalse(browser.called, "A standard widget must not need Chromium")
        self.assertEqual(urlsplit(url).hostname, "api-008.donatty.com")
        self.assertEqual(parse_qs(urlsplit(url).query)["jwt"], ["fresh-sse-token"])
        self.assertEqual(calls, [("https://api-008.donatty.com/auth/tokens/private-widget-token", False)])

    def test_native_donatty_does_not_send_token_to_untrusted_host(self):
        cfg = {"widget_url": "https://widgets.donatty.com.example.invalid/donations/?ref=00000000-0000-0000-0000-00000000005e&token=private-widget-token"}
        with patch.object(dt, "requests") as requests_mock, \
             patch.object(dt, "capture_sse_url_with_browser", return_value="legacy-sse"):
            self.assertEqual(dt.resolve_sse_url(cfg), "legacy-sse")
        requests_mock.Session.assert_not_called()

    def test_native_donatty_protocol_failure_keeps_browser_fallback(self):
        cfg = {"widget_url": "https://widgets.donatty.com/donations/?ref=00000000-0000-0000-0000-00000000005e&token=private-widget-token"}
        session = types.SimpleNamespace(trust_env=False, get=lambda *a, **k: types.SimpleNamespace(status_code=503))
        from contextlib import nullcontext
        with patch.object(dt, "requests", types.SimpleNamespace(Session=lambda: nullcontext(session))), \
             patch.object(dt, "write_status"), \
             patch.object(dt, "capture_sse_url_with_browser", return_value="legacy-sse"):
            self.assertEqual(dt.resolve_sse_url(cfg), "legacy-sse")

    def run_da(self, frames):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        added = []
        integration = create_integration(Path(temp.name), added)
        statuses = []
        original_update = integration._update_status

        def update(**values):
            statuses.append(dict(values))
            original_update(**values)

        integration._update_status = update
        integration._catch_up_after_connect = lambda: True
        integration.api_request = lambda method, endpoint, **kwargs: (
            {"data": {"id": 1, "socket_connection_token": "socket"}}
            if endpoint == "/user/oauth" else
            {"channels": [{"channel": "$alerts:donation_1", "token": "subscription"}]}
        )
        pending = deque(frames)
        sent = []

        class Socket:
            def send(self, value): sent.append(value)
            def settimeout(self, value): pass
            def close(self): pass
            def recv(self):
                if pending:
                    return pending.popleft()
                integration._stop.set()
                return ""

        def stop_wait(seconds):
            integration._stop.set()
            return True

        with patch.object(da, "websocket", types.SimpleNamespace(create_connection=lambda *a, **k: Socket())), \
             patch.object(integration._stop, "wait", side_effect=stop_wait):
            integration._listener_loop()
        return added, sent, statuses

    def test_da_batched_auth_and_publications_are_not_lost(self):
        added, sent, _ = self.run_da([
            '{}\n' + json.dumps({"id": 1, "result": {"client": "client"}}),
            '\n'.join(map(json.dumps, [publication(10), {"id": 2, "result": {}}, publication(11), {}])),
        ])
        self.assertEqual(added, ["10", "11"])
        self.assertEqual(sent.count("{}"), 2)

    def test_da_failed_subscription_never_reports_connected(self):
        _, _, statuses = self.run_da([
            json.dumps({"id": 1, "result": {"client": "client"}}),
            json.dumps({"id": 2, "error": {"code": 103, "message": "permission denied"}}),
        ])
        self.assertFalse(any(item.get("connected") for item in statuses))

    def test_da_api_uses_direct_session_unless_requested(self):
        with tempfile.TemporaryDirectory() as folder:
            integration = create_integration(Path(folder), [])
            routes = []

            class Response:
                status_code = 200
                text = "{}"
                def raise_for_status(self): pass
                def json(self): return {}

            class Session:
                trust_env = True
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def request(self, *args, **kwargs):
                    routes.append(self.trust_env)
                    return Response()

            legacy_request = lambda *a, **k: (routes.append(True) or Response())
            with patch.object(da, "requests", types.SimpleNamespace(Session=Session, request=legacy_request)):
                integration.api_request("GET", "/user/oauth")
                config = json.loads(integration.config_file.read_text(encoding="utf-8"))
                config["use_system_proxy"] = True
                integration.config_file.write_text(json.dumps(config), encoding="utf-8")
                integration.api_request("GET", "/user/oauth")
            self.assertEqual(routes, [False, True])

    def test_donatty_status_preserves_last_event_on_heartbeat(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(dt, "STATUS_FILE", Path(folder) / "status.json"):
            dt.write_status("connected", connected=True, last_event="synthetic test event")
            dt.write_status("connected", connected=True)
            status = json.loads(dt.STATUS_FILE.read_text(encoding="utf-8"))
            self.assertEqual(status["lastEvent"], "synthetic test event")

    def test_donatty_local_delivery_does_not_use_system_proxy(self):
        routes = []

        class Response:
            status_code = 200

        class Session:
            trust_env = True
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def post(self, *args, **kwargs):
                routes.append(self.trust_env)
                return Response()

        with patch.object(dt, "requests", types.SimpleNamespace(Session=Session)), patch.object(dt, "write_status"):
            self.assertTrue(dt.send_donation_to_widget({"username": "Test", "amount": 10, "currency": "RUB"}, {"use_system_proxy": True}))
        self.assertEqual(routes, [False])

    def test_donatty_browser_uses_direct_route_by_default(self):
        launches = []

        class Page:
            def on(self, event, callback):
                if event == "request":
                    callback(types.SimpleNamespace(url="https://api.donatty.com/sse?jwt=synthetic"))
            def goto(self, *args, **kwargs): pass

        class Browser:
            def new_context(self, **kwargs): return self
            def new_page(self): return Page()
            def close(self): pass

        class Playwright:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            @property
            def chromium(self): return self
            def launch(self, **kwargs):
                launches.append(kwargs)
                return Browser()

        with patch.object(dt, "sync_playwright", Playwright), patch.object(dt, "write_status"):
            dt.capture_sse_url_with_browser({"widget_url": "https://example.invalid/widget"})
            dt.capture_sse_url_with_browser({"widget_url": "https://example.invalid/widget", "use_system_proxy": True})
        self.assertIn("--no-proxy-server", launches[0]["args"])
        self.assertNotIn("--no-proxy-server", launches[1]["args"])

    def test_da_explicit_proxy_applies_to_websocket_as_well(self):
        integration = da.DonationAlertsIntegration.__new__(da.DonationAlertsIntegration)
        with patch.object(da, "getproxies", return_value={"https": "http://127.0.0.1:2080"}), \
             patch.object(da, "proxy_bypass", return_value=False):
            options = integration._websocket_options({"use_system_proxy": True})
        self.assertEqual((options["http_proxy_host"], options["http_proxy_port"]), ("127.0.0.1", 2080))
        self.assertEqual(integration._websocket_options({}), {"http_no_proxy": ["*"]})

    def test_donatty_http_success_without_sse_data_is_not_connected(self):
        statuses = []

        class Response:
            status_code = 200
            headers = {"Content-Type": "text/event-stream"}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def raise_for_status(self): pass
            def iter_lines(self, **kwargs):
                raise TimeoutError("synthetic idle stream")
                yield

        class Session:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def get(self, *a, **k): return Response()

        fake = types.SimpleNamespace(Session=Session, get=lambda *a, **k: Response())
        with patch.object(dt, "requests", fake), patch.object(dt, "write_status", side_effect=lambda *a, **k: statuses.append(k)):
            with self.assertRaises(TimeoutError):
                dt.listen_sse("https://example.invalid/sse", {})
        self.assertFalse(any(status.get("connected") for status in statuses))

    @unittest.skipIf(dt.requests is None, "requests is required for the streaming regression")
    def test_short_sse_event_is_delivered_before_idle_timeout(self):
        import requests

        event = {"action": "DATA", "data": {"streamEventType": "DONATTY_DONATION",
            "streamEventData": {"id": "short-event", "displayName": "Test", "amount": 10}}}
        wire = ("data: " + json.dumps(event) + "\n\n").encode("utf-8")
        self.assertLess(len(wire), 512)
        response = requests.Response()
        response.status_code = 200
        response.headers["Content-Type"] = "text/event-stream;charset=UTF-8"

        class Raw:
            def stream(self, amt, decode_content=True):
                for offset in range(0, len(wire) - amt + 1, amt):
                    yield wire[offset:offset + amt]
                raise TimeoutError("synthetic idle stream")
            def close(self): pass
            def release_conn(self): pass

        response.raw = Raw()

        class Session:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def get(self, *a, **k): return response

        fake = types.SimpleNamespace(Session=Session, get=lambda *a, **k: response)
        with patch.object(dt, "requests", fake), patch.object(dt, "write_status"), \
             patch.object(dt, "send_donation_to_widget", return_value=True) as deliver:
            with self.assertRaises(TimeoutError):
                dt.listen_sse("https://example.invalid/sse", {})
        self.assertEqual(deliver.call_count, 1)
        self.assertEqual(deliver.call_args.args[0]["externalId"], "short-event")


if __name__ == "__main__":
    unittest.main(verbosity=2)
