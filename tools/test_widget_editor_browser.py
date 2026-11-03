"""Working editor checks on disposable Core data; external effects are disabled."""
import base64
import io
import json
import zipfile
from playwright.sync_api import expect
import test_studio_browser as baseline
import unittest

class WidgetEditorTests(baseline.StudioBrowserTests):
    def setUp(self):
        super().setUp()
        (self.root / "core/widget_settings.json").unlink(missing_ok=True)

    def editor(self):
        self.page.goto(self.origin+'/admin.html#widget/editor')
        expect(self.page.locator('#widgetEditorRoot')).to_be_visible()
        self.page.wait_for_function('window.VDGWidgetEditor && window.VDGWidgetEditor.ready')
        self.page.evaluate('async()=>await window.VDGWidgetEditor.ready')

    def open_preset(self, name):
        self.page.evaluate("location.hash='widget/presets'")
        button=self.page.locator('[data-we-library-edit="preset:'+name+'"]')
        button.locator('xpath=ancestor::details').locator('summary').click()
        button.click()
        expect(self.page.locator('#widgetEditorRoot')).to_be_visible()

    def test_real_editor_mounts_without_applying_widget(self):
        self.editor()
        self.assertGreater(self.page.locator('[data-we-layer]').count(),0)
        expect(self.page.locator('[data-we-action="apply"]')).to_be_visible()
        state=self.page.request.get(self.origin+'/api/widget/active').json()
        self.assertIsNone(state['document'])

    def test_edit_template_draft_apply_and_reload(self):
        self.editor()
        self.open_preset('line')
        self.page.locator('[data-we-action="add-text"]').click()
        self.page.locator('[data-we-prop="text"]').fill('My {{current}}')
        self.page.locator('[data-we-prop="text"]').dispatch_event('change')
        self.page.locator('[data-we-action="save-draft"]').click()
        self.page.wait_for_function('document.querySelector("[data-we-status]").dataset.state === "saved"')
        editor=self.page.request.get(self.origin+'/api/widget/editor').json()
        self.assertTrue(any(n['text']=='My {{current}}' for n in editor['settings']['draft']['elements']))
        self.assertIsNone(editor['settings']['active'])
        self.page.locator('[data-we-action="apply"]').click()
        self.page.wait_for_function('document.querySelector("[data-we-status]").textContent.includes("Применено")')
        active=self.page.request.get(self.origin+'/api/widget/active').json()['document']
        self.assertEqual(active, self.page.request.get(self.origin+'/api/widget/editor').json()['settings']['draft'])
        self.page.reload()
        expect(self.page.locator("#widgetEditorRoot")).to_be_visible()
        self.page.evaluate('async()=>await window.VDGWidgetEditor.ready')
        self.assertTrue(self.page.evaluate("VDGWidgetEditor.getDocument().elements.some(n=>n.text==='My {{current}}')"))

    def test_geometry_undo_group_and_preview_do_not_modify_goal(self):
        self.editor()
        before=self.page.request.get(self.origin+'/api/state').json()
        self.page.locator('[data-we-action="add-shape"]').click()
        x=self.page.locator('[data-we-prop="x"]')
        original=float(x.input_value())
        x.fill('123');x.dispatch_event('change')
        self.page.locator('[data-we-action="undo"]').click()
        expect(x).to_have_value(str(int(original)))
        self.page.locator('[data-we-preview="percent"]').fill('75')
        self.page.locator('[data-we-preview="percent"]').dispatch_event('input')
        self.assertEqual(self.page.request.get(self.origin+'/api/state').json(),before)

    def test_uploaded_image_in_export_and_custom_code_is_isolated(self):
        self.editor()
        self.page.locator('[data-we-action="add-image"]').click()
        data=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lM8AAAAASUVORK5CYII=')
        self.page.locator('[data-we-upload="image"]').set_input_files({'name':'fixture.png','mimeType':'image/png','buffer':data})
        self.page.wait_for_function("VDGWidgetEditor.getDocument().elements.some(n=>n.type==='image'&&n.image.asset)")
        self.page.locator('[data-we-action="save-draft"]').click()
        self.page.wait_for_function('document.querySelector("[data-we-status]").dataset.state === "saved"')
        package=self.page.request.get(self.origin+'/api/widget/export?kind=draft')
        self.assertEqual(package.status,200)
        with zipfile.ZipFile(io.BytesIO(package.body())) as archive:
            self.assertIn('widget.json',archive.namelist())
            self.assertTrue(any(name.startswith('assets/') for name in archive.namelist()))
        original=self.page.evaluate('VDGWidgetEditor.getDocument()')
        self.open_preset('ring')
        self.page.locator('[data-we-import]').set_input_files({'name':'widget.zip','mimeType':'application/zip','buffer':package.body()})
        self.page.wait_for_function('(id)=>VDGWidgetEditor.getDocument().id===id', arg=original['id'])
        self.assertIsNone(self.page.request.get(self.origin+'/api/widget/active').json()['document'])
        self.page.locator('[data-we-action="add-custom"]').click()
        frame=self.page.locator('.vdg-widget-element iframe').last
        expect(frame).to_be_attached()
        self.assertEqual(frame.get_attribute('sandbox'),'allow-scripts')
        sandbox=frame.element_handle().content_frame()
        self.assertFalse(sandbox.evaluate("()=>{try{return Boolean(parent.document.body)}catch{return false}}"))

    def test_apply_waits_for_latest_edit_during_pending_save(self):
        self.editor()
        self.page.locator('[data-we-action="add-text"]').click()
        self.page.evaluate("""()=>{const original=window.fetch;window.draftHeld=false;window.fetch=async(...args)=>{
          if(String(args[0])==='/api/widget/draft'&&!window.draftHeld){window.draftHeld=true;
            await new Promise(resolve=>{window.releaseDraft=resolve});}
          return original(...args);
        }}""")
        self.page.locator('[data-we-prop="text"]').fill('Before pending save')
        self.page.locator('[data-we-action="save-draft"]').click()
        self.page.wait_for_function('window.draftHeld')
        self.page.locator('[data-we-prop="text"]').fill('Latest pending edit')
        self.page.locator('[data-we-action="apply"]').click()
        self.page.evaluate('window.releaseDraft()')
        self.page.wait_for_function('document.querySelector("[data-we-status]").textContent.includes("Применено")')
        active=self.page.request.get(self.origin+'/api/widget/active').json()['document']
        self.assertTrue(any(n['text']=='Latest pending edit' for n in active['elements']))

if __name__=='__main__':unittest.main()
