import unittest
from playwright.sync_api import expect
from test_widget_editor_browser import WidgetEditorTests


class GuidebookTests(WidgetEditorTests):
    def test_guides_live_in_studio_and_help_opens_them(self):
        self.editor()
        expect(self.page.locator('.studio-sidebar .global-link[href="#guidebook/appearance"]')).to_be_visible()
        self.page.locator('[data-we-action="help"]').click()
        expect(self.page).to_have_url(self.origin+'/admin.html#guidebook/appearance/editor')
        expect(self.page.locator('[data-guidebook-article] #guidebook-start')).to_be_visible()
        self.page.locator('.guidebook-back').click()
        self.page.locator('.guidebook-tile[href="#guidebook/appearance/ai"]').click()
        expect(self.page.locator('[data-guidebook-article] #guidebook-ai-workflow')).to_be_visible()
        expect(self.page.locator('[data-guidebook-article] #guidebook-start')).to_have_count(0)
        self.page.locator('[data-guidebook-chapter="ai-motion"]').click()
        expect(self.page).to_have_url(self.origin+'/admin.html#guidebook/appearance/ai/ai-motion')
        self.page.reload()
        expect(self.page.locator('#guidebook-ai-motion')).to_be_visible()
        self.assertEqual(len(self.context.pages),1)

    def test_ai_help_and_small_light_layout(self):
        self.page.goto(self.origin+'/admin.html#widget/ai')
        self.page.get_by_role('link',name='Как создать и доработать виджет с ИИ').click()
        expect(self.page.locator('[data-guidebook-article] #guidebook-ai-workflow')).to_be_visible()
        self.page.evaluate('VDGThemes.apply({mode:"light",family:"monocrome",base:"neutral",accent:"sky"})')
        self.page.set_viewport_size({'width':390,'height':850})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),392)
        expect(self.page.locator('.guidebook-back')).to_be_visible()
        expect(self.page.locator('.guidebook-tabs')).to_have_count(0)
        self.assertIsNone(self.page.request.get(self.origin+'/api/widget/active').json()['document'])


if __name__=='__main__':unittest.main()
