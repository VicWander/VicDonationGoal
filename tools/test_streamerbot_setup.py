import sys,json,threading,tempfile,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'core')]
from integrations.streamerbot.streamerbot_api import normalize_config,list_actions,check_connection,execute_action
from integration_manager import IntegrationManager

class FakeStreamerBot(BaseHTTPRequestHandler):
    calls=[]
    actions=[{'id':'action-1','name':'Оповещение','enabled':True}]
    def do_GET(self):
        self.calls.append(('GET',self.path,None))
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps({'actions':self.actions}).encode())
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(('POST',self.path,data));self.send_response(204);self.end_headers()
    def log_message(self,*args):pass

class SetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),FakeStreamerBot)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
        cls.url=f'http://127.0.0.1:{cls.http.server_port}/DoAction'
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close()
    def setUp(self):FakeStreamerBot.calls=[]
    def test_check_and_list_are_read_only_and_action_id_wins(self):
        config={'streamerbot_http_url':self.url,'action_name':'Old name','action_id':'action-1'}
        self.assertEqual(list_actions(config)[0]['id'],'action-1')
        self.assertEqual(check_connection(config)['id'],'action-1')
        self.assertTrue(all(c[0]=='GET' for c in FakeStreamerBot.calls))
        with self.assertRaisesRegex(ValueError,'не найдено'):check_connection(dict(config,action_id='missing'))
    def test_execute_sends_one_action_with_args(self):
        execute_action({'streamerbot_http_url':self.url},{'id':'action-1'},{'user':'TestUser','amount':133})
        self.assertEqual(FakeStreamerBot.calls,[('POST','/DoAction',{'action':{'id':'action-1'},'args':{'user':'TestUser','amount':133}})])
    def test_normalization_rejects_bad_address(self):
        cfg=normalize_config({'streamerbot_http_url':self.url.removesuffix('/DoAction'),'action_name':' Test ','extra_args':{'keep':1}})
        self.assertEqual(cfg['streamerbot_http_url'],self.url);self.assertEqual(cfg['action_name'],'Test')
        self.assertEqual(cfg['extra_args'],{'keep':1})
        with self.assertRaises(ValueError):normalize_config({'streamerbot_http_url':'file:///tmp/test'})
    def test_manifest_and_config_preserve_advanced_fields(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=root/'integrations/streamerbot';d.mkdir(parents=True)
            for name in ['manifest.json','streamerbot_config.example.json','GUIDE.md']:
                shutil.copy2(ROOT/'integrations/streamerbot'/name,d/name)
            manager=IntegrationManager(root)
            manager._save_config('streamerbot',{'enabled':False,'streamerbot_http_url':self.url,'action_name':'Оповещение','extra_args':{'keep':1}})
            manager.save_config('streamerbot',{'action_id':'action-1'})
            self.assertEqual(manager._load_config('streamerbot')['extra_args'],{'keep':1})
            self.assertFalse(manager.detail('streamerbot')['summary']['enabled'])
            self.assertTrue(manager.test('streamerbot')['ok'])
            self.assertFalse(any(c[0]=='POST' for c in FakeStreamerBot.calls))
            self.assertTrue(manager.test_streamerbot_action()['ok'])
            self.assertEqual(len([c for c in FakeStreamerBot.calls if c[0]=='POST']),1)
            self.assertFalse((root/'core/data/donations.json').exists())
            self.assertFalse((d/'streamerbot_sent.json').exists())

if __name__=='__main__':unittest.main()
