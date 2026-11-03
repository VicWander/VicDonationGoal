"""HTTP editor integration using a copied project and ephemeral local server."""
import http.client
import json
import unittest
from test_preview_api import PreviewAPITests
from test_widget_backend import document

class WidgetAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PreviewAPITests.setUpClass()
        cls.fixture = PreviewAPITests
        cls.fixture.server.WIDGET_STORE.path.unlink(missing_ok=True)

    @classmethod
    def tearDownClass(cls): PreviewAPITests.tearDownClass()

    def request(self, method, path, value=None, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.fixture.http.server_port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if origin: headers['Origin'] = origin
        try:
            conn.request(method, path, None if value is None else json.dumps(value).encode(), headers)
            response = conn.getresponse(); raw = response.read()
            return response.status, json.loads(raw)
        finally: conn.close()

    def test_end_to_end_draft_apply_conflict_and_origin_guard(self):
        status, editor = self.request('GET', '/api/widget/editor')
        self.assertEqual(status, 200)
        self.assertIsNone(editor['settings']['active'])
        self.assertFalse(self.fixture.server.WIDGET_STORE.path.exists())
        request = dict(revision=0, document=document())
        for origin in ['http://localhost.evil.example', 'http://127.0.0.1.evil.example', 'null']:
            self.assertEqual(self.request('POST', '/api/widget/draft', request, origin)[0], 403)
        self.assertEqual(self.request('POST', '/api/widget/draft', request)[0], 200)
        status, active = self.request('GET', '/api/widget/active')
        self.assertEqual(status, 200); self.assertIsNone(active['document'])
        self.assertEqual(self.request('POST', '/api/widget/apply', dict(revision=0))[0], 409)
        self.assertEqual(self.request('POST', '/api/widget/apply', dict(revision=1))[0], 200)
        self.assertEqual(self.request('GET', '/api/widget/active')[1]['document']['name'], 'Test')
        newer = document(); newer['name'] = 'Draft only'
        self.assertEqual(self.request('POST', '/api/widget/draft', dict(revision=2, document=newer))[0], 200)
        self.assertEqual(self.request('GET', '/api/widget/active')[1]['document']['name'], 'Test')

if __name__ == '__main__': unittest.main()
