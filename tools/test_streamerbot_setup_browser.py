import json,threading,time,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import expect
from test_studio_browser import StudioBrowserTests
from test_streamerbot_setup import FakeStreamerBot

class StreamerbotSetupBrowserTests(StudioBrowserTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server.PREVIEW_MODE=False
        config_path=cls.root/'integrations/streamerbot/streamerbot_config.json'
        config=json.loads(config_path.read_text(encoding='utf-8'))
        config.update(enabled=False,action_id='')
        config_path.write_text(json.dumps(config),encoding='utf-8')
        (config_path.parent/'donation_event_rules.json').write_text('{"enabled":false,"rules":[]}',encoding='utf-8')
        for name in ('streamerbot_sent.json','streamerbot_event_rules_sent.json'):
            (config_path.parent/name).unlink(missing_ok=True)
        cls.sb=ThreadingHTTPServer(('127.0.0.1',0),FakeStreamerBot)
        threading.Thread(target=cls.sb.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.server.get_integration_manager().stop_all()
        cls.sb.shutdown();cls.sb.server_close()
        super().tearDownClass()
    def test_new_user_can_pick_test_enable_stop_without_editing_files(self):
        FakeStreamerBot.calls=[]
        self.page.goto(self.origin+'/admin.html#integrations/services')
        expect(self.page.locator('[data-integration-id="donationalerts"]')).to_be_visible()
        expect(self.page.locator('[data-integration-id="streamerbot"]')).to_have_count(0)
        self.page.locator('.studio-subnav a[href="#integrations/streamerbot"]').click()
        expect(self.page).to_have_url(self.origin+'/admin.html#integrations/streamerbot')
        expect(self.page.locator('#streamerbotSetup')).to_be_visible()
        self.page.locator('[data-config-key="streamerbot_http_url"]').fill(f'http://127.0.0.1:{self.sb.server_port}')
        self.page.locator('#streamerbotLoadActions').click()
        expect(self.page.locator('#streamerbotActionSelect option[value="action-1"]')).to_have_count(1)
        self.page.locator('#streamerbotActionSelect').select_option('action-1')
        self.page.locator('#integrationSaveButton').click()
        expect(self.page.locator('[data-config-key="action_id"]')).to_have_value('action-1')
        self.page.locator('#integrationTestButton').click()
        expect(self.page.locator('#integrationActionResult')).to_contain_text('Оповещение не запускалось')
        self.assertFalse(any(c[0]=='POST' for c in FakeStreamerBot.calls))
        before=(self.root/'core/data/donations.json').read_bytes()
        self.page.locator('#streamerbotTestAction').click()
        expect(self.page.locator('#integrationActionResult')).to_contain_text('принял тестовое')
        self.assertEqual((self.root/'core/data/donations.json').read_bytes(),before)
        self.assertEqual(len([c for c in FakeStreamerBot.calls if c[0]=='POST']),1)
        self.page.locator('#integrationEnabledInput').check()
        manager=self.server.get_integration_manager()
        deadline=time.time()+12
        while time.time()<deadline and not manager.integration_status('streamerbot').get('connected'):time.sleep(.2)
        self.assertTrue(manager.integration_status('streamerbot').get('connected'))
        self.assertEqual(len([c for c in FakeStreamerBot.calls if c[0]=='POST']),1)
        pid=manager.integration_status('streamerbot')['pid']
        manager.start('streamerbot')
        self.assertEqual(pid,manager.integration_status('streamerbot')['pid'])
        old_actions=FakeStreamerBot.actions
        try:
            FakeStreamerBot.actions=[]
            deadline=time.time()+9
            while time.time()<deadline and manager.integration_status('streamerbot').get('connected'):time.sleep(.2)
            self.assertFalse(manager.integration_status('streamerbot').get('connected'))
            self.assertNotEqual(manager.detail('streamerbot')['summary']['commonState'],'connected')
        finally:FakeStreamerBot.actions=old_actions
        self.page.locator('#integrationStopButton').click()
        expect(self.page.locator('#integrationStartButton')).to_be_enabled()
        self.assertFalse(manager.integration_status('streamerbot').get('connected'))
        self.page.locator('#integrationEnabledInput').uncheck()
        expect(self.page.locator('#integrationDetailBadge')).to_have_text('Выключено')
        self.page.locator('.studio-subnav a[href="#integrations/services"]').click()
        expect(self.page.locator('#integrationDetailName')).to_have_text('DonationAlerts')
        expect(self.page.locator('[data-integration-id="streamerbot"]')).to_have_count(0)
        self.page.locator('.studio-subnav a[href="#integrations/streamerbot"]').click()
        expect(self.page.locator('#streamerbotSetup')).to_be_visible()
        self.page.reload()
        expect(self.page.locator('#streamerbotSetup')).to_be_visible()
        expect(self.page.locator('[data-config-key="action_id"]')).to_have_value('action-1')
        self.page.screenshot(path=str(Path(__file__).resolve().parents[2]/'streamerbot-setup-dark.png'))
        self.page.evaluate('VDGThemes.apply({mode:"light",family:"monocrome",base:"neutral",accent:"sky"})')
        self.page.screenshot(path=str(Path(__file__).resolve().parents[2]/'streamerbot-setup-light.png'))
        self.page.set_viewport_size({'width':390,'height':850})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),392)
        self.page.goto(self.origin+'/admin.html#tts/providers')
        expect(self.page.locator('#speakerUrlInput')).to_be_visible()
        expect(self.page.get_by_text('Первое подключение Speaker.bot',exact=True)).to_be_visible()

if __name__=='__main__':unittest.main()
