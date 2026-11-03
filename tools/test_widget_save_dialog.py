"""Save variants without native browser prompt support."""
import unittest
from playwright.sync_api import expect
from test_widget_editor_browser import WidgetEditorTests

class SaveDialogTests(WidgetEditorTests):
    def test_save_and_cancel_without_native_prompt(self):
        self.editor()
        self.page.evaluate("()=>{window.prompt=()=>{throw Error('prompt unavailable')}}")
        self.page.get_by_role('button', name='Сохранить вариант', exact=True).click()
        dialog=self.page.locator('.we-dialog')
        expect(dialog).to_be_visible()
        name=dialog.get_by_role('textbox', name='Название варианта', exact=True)
        name.fill('UI-only variant')
        name.press('Enter')
        expect(dialog).not_to_be_visible()
        self.page.wait_for_function("document.querySelector('[data-we-status]').textContent.includes('Вариант сохранён')")
        self.page.reload()
        self.page.get_by_role('button', name='Оформления', exact=True).click()
        expect(self.page.get_by_role('button', name='UI-only variant', exact=True)).to_be_visible()
        self.page.get_by_role('button', name='Закрыть', exact=True).click()
        before=self.page.request.get(self.origin+'/api/widget/editor').json()['settings']
        self.page.get_by_role('button', name='Сохранить вариант', exact=True).click()
        dialog.get_by_role('button', name='Закрыть', exact=True).click()
        after=self.page.request.get(self.origin+'/api/widget/editor').json()['settings']
        self.assertEqual(before,after)

if __name__=='__main__':
    unittest.main()

