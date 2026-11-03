import unittest
from pathlib import Path
from playwright.sync_api import expect
from test_studio_browser import StudioBrowserTests

class AlertGuideTests(StudioBrowserTests):
    def test_guide_and_inline_example_share_copyable_code(self):
        self.page.goto(self.origin+'/admin.html#guidebook/appearance')
        self.page.locator('.guidebook-tile[href="#guidebook/appearance/streamerbot"]').click()
        expect(self.page.locator('#guidebook-sb-start')).to_be_visible()
        self.page.locator('[data-guidebook-chapter="sb-code"]').click()
        expect(self.page.locator('[data-alert-code]')).to_contain_text('SoundFile = @""')
        code=self.page.locator('[data-alert-code]').text_content()
        self.page.evaluate('navigator.clipboard.writeText=async text=>{window.copiedAlert=text}')
        self.page.locator('[data-alert-copy]').click()
        self.assertEqual(self.page.evaluate('window.copiedAlert'),code)
        self.page.goto(self.origin+'/admin.html#integrations/streamerbot')
        self.page.locator('#streamerbotAlertExample > summary').click()
        expect(self.page.locator('#streamerbotAlertExample [data-alert-code]')).to_have_text(code)
        self.page.locator('#streamerbotAlertExample a[href="#guidebook/appearance/streamerbot"]').click()
        expect(self.page.locator('#guidebook-sb-start')).to_be_visible()
        self.page.reload()
        expect(self.page.locator('#guidebook-sb-start')).to_be_visible()
        self.page.screenshot(path=str(Path(__file__).resolve().parents[2]/'alert-guide-dark.png'))
        self.page.evaluate('VDGThemes.apply({mode:"light",family:"monocrome",base:"neutral",accent:"sky"})')
        self.page.screenshot(path=str(Path(__file__).resolve().parents[2]/'alert-guide-light.png'))
        self.page.set_viewport_size({'width':390,'height':850})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),392)

    def test_provider_cards_follow_each_other_without_row_gaps(self):
        self.page.goto(self.origin+'/admin.html#tts/providers')
        cards=self.page.evaluate('''()=>['ttsEnabledInput','speakerUrlInput','edgeVoiceInput','yandexApiKeyInput','xttsEndpointInput','httpUrlInput'].map(id=>{const c=document.getElementById(id).closest('.card');const r=c.getBoundingClientRect();return {top:r.top,bottom:r.bottom,x:r.x}})''')
        for upper,lower in [(0,2),(2,4),(1,3),(3,5)]:
            self.assertLessEqual(cards[lower]['top']-cards[upper]['bottom'],24)
            self.assertGreaterEqual(cards[lower]['top']-cards[upper]['bottom'],10)
        self.page.locator('#speakerUrlInput').fill('ws://127.0.0.1:9999/')
        self.page.set_viewport_size({'width':390,'height':850})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),392)
        expect(self.page.locator('#speakerUrlInput')).to_have_value('ws://127.0.0.1:9999/')
        self.page.set_viewport_size({'width':1500,'height':1000})
        expect(self.page.locator('#speakerUrlInput')).to_have_value('ws://127.0.0.1:9999/')
        self.page.screenshot(path=str(Path(__file__).resolve().parents[2]/'provider-columns-dark.png'))
        self.page.evaluate('VDGThemes.apply({mode:"light",family:"monocrome",base:"neutral",accent:"sky"})')
        self.page.screenshot(path=str(Path(__file__).resolve().parents[2]/'provider-columns-light.png'))

if __name__=='__main__':unittest.main()
