"""Real resource library flows, using a disposable preview server."""
import unittest
import shutil
from playwright.sync_api import expect
from test_widget_editor_browser import WidgetEditorTests

SVG=b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="red"/></svg>'


class ResourceBrowserTests(WidgetEditorTests):
    def setUp(self):
        super().setUp()
        resources=(self.root/'core/widget_assets').resolve()
        self.assertTrue(resources.is_relative_to(self.root.resolve()))
        shutil.rmtree(resources,ignore_errors=True)

    def library_upload(self):
        self.editor()
        self.page.locator('[data-we-action="resources"]').click()
        self.page.locator('[data-we-resource-upload]').set_input_files({'name':'Red square.svg','mimeType':'image/svg+xml','buffer':SVG})
        expect(self.page.locator('[data-we-resource-row]')).to_have_count(1)

    def test_upload_rename_search_apply_and_delete_protection(self):
        self.library_upload()
        field=self.page.locator('[data-we-resource-name]');field.fill('Моя картинка')
        self.page.locator('[data-we-resource-op="rename"]').click()
        expect(field).to_have_value('Моя картинка')
        self.page.locator('[data-we-resource-search]').fill('несуществующий')
        expect(self.page.locator('[data-we-resource-row]')).to_have_count(0)
        self.page.locator('[data-we-resource-search]').fill('картинка')
        expect(self.page.locator('[data-we-resource-row]')).to_have_count(1)
        count=self.page.evaluate('VDGWidgetEditor.getDocument().elements.length')
        self.page.locator('[data-we-resource-op="use-image"]').click()
        self.assertTrue(self.page.evaluate("VDGWidgetEditor.getDocument().elements.some(e=>e.type==='image'&&e.image.asset)"))
        self.page.keyboard.press('Control+z')
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements.length'),count)
        self.page.keyboard.press('Control+y')
        self.assertTrue(self.page.evaluate("VDGWidgetEditor.getDocument().elements.some(e=>e.type==='image'&&e.image.asset)"))
        self.page.locator('[data-we-action="resources"]').click()
        expect(self.page.locator('[data-we-resource-op="trash"]')).to_be_disabled()
        self.page.locator('[data-we-action="close-dialog"]').click()
        self.page.reload();self.page.evaluate('async()=>await VDGWidgetEditor.ready')
        self.page.locator('[data-we-action="resources"]').click()
        expect(self.page.locator('[data-we-resource-name]')).to_have_value('Моя картинка')

    def test_unused_delete_moves_to_trash_and_restore(self):
        self.library_upload()
        self.page.locator('[data-we-resource-op="trash"]').click()
        expect(self.page.locator('[data-we-resource-row]')).to_have_count(0)
        self.page.locator('[data-we-resource-filter]').select_option('trash')
        expect(self.page.locator('[data-we-resource-row]')).to_have_count(1)
        self.page.locator('[data-we-resource-op="restore"]').click()
        expect(self.page.locator('[data-we-resource-row]')).to_have_count(0)
        self.page.locator('[data-we-resource-filter]').select_option('all')
        expect(self.page.locator('[data-we-resource-row]')).to_have_count(1)


if __name__=='__main__':unittest.main()
