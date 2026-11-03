"""Audit regressions based on actual UI scenarios, using disposable Core data."""
import unittest
from pathlib import Path
from playwright.sync_api import expect
from test_widget_editor_geometry import WidgetGeometryTests
from test_widget_resources_browser import SVG


class AuditTests(WidgetGeometryTests):
    def world_box(self, locator):
        box=locator.bounding_box();stage=self.page.locator('.we-stage').bounding_box()
        scale=stage['width']/self.page.evaluate('VDGWidgetEditor.getDocument().width')
        return {'x':(box['x']-stage['x'])/scale,'y':(box['y']-stage['y'])/scale,
                'width':box['width']/scale,'height':box['height']/scale}

    def test_canvas_undo_updates_visible_stage_size(self):
        self.editor()
        original=self.page.evaluate('VDGWidgetEditor.getDocument().width')
        width=self.page.locator('[data-we-doc-prop="width"]')
        width.fill('450');width.dispatch_event('change')
        self.page.locator('[data-we-action="undo"]').click()
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().width'),original)
        self.assertEqual(self.page.locator('.we-stage').evaluate('(e)=>parseFloat(e.style.width)'),original)

    def test_cancel_save_variant_does_not_create_variant(self):
        self.editor()
        self.page.locator('[data-we-action="save-copy"]').click()
        self.page.locator('[data-we-action="close-dialog"]').click()
        saved=self.page.request.get(self.origin+'/api/widget/editor').json()['settings']['saved']
        self.assertEqual(saved,[])

    def test_locked_text_cannot_be_changed_with_data_token(self):
        doc=self.fixture("const a=M.createElement('text');a.locked=true;a.text='Locked';d.elements=[a]")
        self.layer(doc['elements'][0]['id'])
        self.page.locator('[data-we-token="current"]').click()
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements[0].text'),'Locked')

    def test_ungroup_rotated_group_preserves_visible_child(self):
        doc=self.fixture("const g=M.createElement('group'),a=M.createElement('shape');Object.assign(g,{x:150,y:30,width:200,height:120,rotation:90});Object.assign(a,{parentId:g.id,x:20,y:15,width:70,height:30});d.elements=[g,a]")
        child=self.page.locator('[data-widget-element="'+doc['elements'][1]['id']+'"]')
        self.layer(doc['elements'][0]['id'])
        before=self.world_box(child)
        self.page.locator('[data-we-action="ungroup"]').click()
        after=self.world_box(child)
        for key in ['x','y','width','height']:
            self.assertAlmostEqual(before[key],after[key],delta=1,msg=key)

    def test_native_change_before_save_does_not_replay_after_undo(self):
        self.editor();self.page.locator('[data-we-action="add-text"]').click()
        before=self.page.evaluate('VDGWidgetEditor.getDocument().elements.at(-1).text')
        field=self.page.locator('[data-we-prop="text"]');field.fill('Changed field')
        self.page.locator('[data-we-action="save-draft"]').click()
        self.page.locator('[data-we-action="undo"]').click()
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements.at(-1).text'),before)

    def test_group_across_rotated_parents_preserves_world_geometry(self):
        doc=self.fixture("const g=M.createElement('group'),a=M.createElement('shape'),b=M.createElement('shape');Object.assign(g,{x:80,y:25,width:180,height:100,rotation:45});Object.assign(a,{parentId:g.id,x:15,y:10,width:60,height:25});Object.assign(b,{x:420,y:50,width:80,height:35});d.elements=[g,a,b]")
        ids=[doc['elements'][1]['id'],doc['elements'][2]['id']]
        self.layer(ids[0]);self.layer(ids[1],True)
        before=[self.world_box(self.page.locator('[data-widget-element="'+identity+'"]')) for identity in ids]
        self.page.locator('[data-we-action="group"]').click()
        after=[self.world_box(self.page.locator('[data-widget-element="'+identity+'"]')) for identity in ids]
        for old,new in zip(before,after):
            for key in old:self.assertAlmostEqual(old[key],new[key],delta=1,msg=key)

    def test_editor_and_dialogs_light_dark_narrow_do_not_overflow(self):
        self.editor()
        for mode in ['dark','light']:
            self.page.evaluate('(mode)=>VDGThemes.apply({mode,family:"monocrome",base:"neutral",accent:"sky"})',mode)
            for width in [1500,768,390]:
                self.page.set_viewport_size({'width':width,'height':950})
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width+2)
                for name in ['resources']:
                    self.page.locator('[data-we-action="'+name+'"]').click()
                    dialog=self.page.locator('.we-dialog')
                    expect(dialog).to_be_visible()
                    self.assertLessEqual(dialog.evaluate('(e)=>e.scrollWidth'),dialog.evaluate('(e)=>e.clientWidth')+2)
                    self.page.locator('[data-we-action="close-dialog"]').click()

    def test_batch_upload_shows_successful_files_when_one_file_is_invalid(self):
        self.editor();self.page.locator('[data-we-action="resources"]').click()
        self.page.locator('[data-we-resource-upload]').set_input_files([
            {'name':'Audit batch.svg','mimeType':'image/svg+xml','buffer':SVG},
            {'name':'Bad audit.svg','mimeType':'image/svg+xml','buffer':b'<svg><script>alert(1)</script></svg>'}])
        self.page.wait_for_function("document.querySelector('[data-we-resource-status]').textContent.includes('SVG')")
        assets=self.page.request.get(self.origin+'/api/widget/resources').json()['assets']
        self.assertTrue(any(asset['name']=='Audit batch.svg' for asset in assets))
        expect(self.page.locator('[data-we-resource-name][value="Audit batch.svg"]')).to_have_count(1)

    def test_conflicting_tab_keeps_local_work_and_does_not_overwrite_saved_draft(self):
        self.editor()
        other=self.context.new_page();other.goto(self.origin+'/admin.html#widget/editor')
        other.evaluate('async()=>await VDGWidgetEditor.ready')
        self.page.locator('[data-we-action="add-shape"]').click()
        self.page.locator('[data-we-action="save-draft"]').click()
        self.page.wait_for_function("document.querySelector('[data-we-status]').dataset.state==='saved'")
        server=self.page.request.get(self.origin+'/api/widget/editor').json()['settings']['draft']
        other.locator('[data-we-action="add-image"]').click()
        other.locator('[data-we-action="save-draft"]').click()
        other.wait_for_function("document.querySelector('[data-we-status]').dataset.state==='error'")
        self.assertTrue(other.evaluate("VDGWidgetEditor.getDocument().elements.some(e=>e.type==='image')"))
        self.assertEqual(self.page.request.get(self.origin+'/api/widget/editor').json()['settings']['draft'],server)
        other.close()

    def test_preview_pause_stops_progress_and_resume_continues(self):
        self.page.emulate_media(reduced_motion='no-preference')
        self.fixture("const a=M.createElement('progress');a.width=300;a.animation.duration=1200;a.animation.easing='linear';d.elements=[a]")
        self.page.locator('[data-we-preview="enabled"]').check()
        slider=self.page.locator('[data-we-preview="percent"]');slider.fill('0')
        self.page.wait_for_timeout(1300)
        slider.fill('100');self.page.wait_for_timeout(100)
        self.page.locator('[data-we-action="pause-preview"]').click()
        fill=self.page.locator('.we-render [data-widget-type="progress"] svg > rect:last-child')
        before=float(fill.get_attribute('width'))
        self.page.wait_for_timeout(350)
        after=float(fill.get_attribute('width'))
        self.assertAlmostEqual(before,after,delta=2)
        self.page.locator('[data-we-action="pause-preview"]').click()
        self.page.wait_for_timeout(300)
        self.assertGreater(float(fill.get_attribute('width')),after+10)

    def test_all_presets_boundary_states_and_applied_widget_match(self):
        self.editor()
        presets=self.page.evaluate('VDGWidgetPresets.list().map(p=>p.id)')
        for identity in presets:
            self.open_preset(identity)
            self.page.locator('[data-we-preview="enabled"]').check()
            self.page.locator('[data-we-preview="title"]').fill('Очень длинное название цели — '*12)
            for percent in ['0','50','100','150']:
                self.page.locator('[data-we-preview="percent"]').fill(percent)
                self.assertTrue(self.page.evaluate('VDGWidgetModel.validate(VDGWidgetEditor.getDocument()).ok'))
                text=self.page.locator('.we-render').inner_text()
                self.assertNotIn('NaN',text);self.assertNotIn('undefined',text)
            self.assertEqual(self.page.locator('.we-render [data-widget-element]').count(),
                             self.page.evaluate('VDGWidgetEditor.getDocument().elements.length'))
        self.page.locator('[data-we-preview="enabled"]').uncheck()
        self.page.locator('[data-we-action="apply"]').click()
        self.page.wait_for_function("document.querySelector('[data-we-status]').textContent.includes('Применено')")
        widget=self.context.new_page();widget.goto(self.origin+'/widget.html')
        expect(widget.locator('#designedWidget')).to_be_visible()
        self.assertEqual(widget.locator('#designedWidget').inner_text(),self.page.locator('.we-render').inner_text())
        widget.close()

    def test_saved_variant_can_be_reopened_without_overwriting_it(self):
        self.editor();self.page.locator('[data-we-action="add-text"]').click()
        self.page.locator('[data-we-prop="text"]').fill('Saved variant text')
        self.page.locator('[data-we-action="save-copy"]').click()
        self.page.get_by_role('textbox',name='Название варианта',exact=True).fill('Audit saved variant')
        self.page.locator('[data-we-save-variant] button').click()
        self.page.wait_for_function("document.querySelector('[data-we-status]').textContent.includes('Вариант сохранён')")
        self.page.locator('[data-we-prop="text"]').fill('Unsaved later text')
        self.page.evaluate("location.hash='widget/presets'")
        button=self.page.locator('[data-we-library-edit^="saved:"]')
        button.locator('xpath=ancestor::details').locator('summary').click()
        button.click()
        expect(self.page.locator('.we-dialog')).not_to_be_visible()
        self.assertTrue(self.page.evaluate("VDGWidgetEditor.getDocument().elements.some(e=>e.text==='Saved variant text')"))

    def test_real_font_upload_loads_in_renderer_and_library(self):
        font=Path('C:/Windows/Fonts/arial.ttf')
        if not font.is_file():self.skipTest('Installed Arial unavailable')
        self.editor();self.page.locator('[data-we-action="add-text"]').click()
        self.page.locator('[data-we-upload="font"]').set_input_files(str(font))
        self.page.wait_for_function("VDGWidgetEditor.getDocument().elements.some(e=>e.type==='text'&&e.style.fontAsset)")
        asset=self.page.evaluate("VDGWidgetEditor.getDocument().elements.find(e=>e.style.fontAsset).style.fontAsset")
        self.page.wait_for_function("""id=>[...document.fonts].some(f=>f.family.replaceAll('"','')==='vdg-'+id&&f.status==='loaded')""",arg=asset)
        self.page.locator('[data-we-action="resources"]').click()
        expect(self.page.locator('[data-we-resource-row="'+asset+'"] .we-resource-font')).to_be_visible()
        expect(self.page.locator('[data-we-resource-row="'+asset+'"] [data-we-resource-op="trash"]')).to_be_disabled()

    def test_currency_and_zero_goal_format_do_not_produce_invalid_numbers(self):
        self.editor()
        results=self.page.evaluate("""()=>['RUB','USD','EUR'].map(currency=>({currency,
          text:VDGWidgetRenderer.format('{{current}} {{currency}} / {{goal}} — {{percent}}%',
          {current:1234.5,goal:2000,currency},{decimals:2,currency:'symbol'}),
          zero:VDGWidgetRenderer.format('{{percent}}%',{current:0,goal:0,currency},{decimals:0})}))""")
        for row,symbol in zip(results,['₽','$','€']):
            self.assertIn(symbol,row['text']);self.assertIn('1\u00a0234,50',row['text'])
            self.assertEqual(row['zero'],'0%')

    def test_cancel_drag_does_not_leave_intermediate_position_in_saved_draft(self):
        doc=self.fixture("const a=M.createElement('shape');Object.assign(a,{x:40,y:30,width:80,height:50});d.elements=[a]")
        self.layer(doc['elements'][0]['id'])
        x=self.page.locator('[data-we-prop="x"]');x.fill('45');x.dispatch_event('change');x.blur()
        box=self.page.locator('[data-we-hit]').bounding_box()
        self.page.mouse.move(box['x']+20,box['y']+20);self.page.mouse.down()
        self.page.mouse.move(box['x']+100,box['y']+20)
        self.page.wait_for_timeout(1150)
        self.page.keyboard.press('Escape');self.page.mouse.up()
        self.page.locator('[data-we-action="save-draft"]').click()
        self.page.wait_for_function("document.querySelector('[data-we-status]').dataset.state==='saved'")
        saved=self.page.request.get(self.origin+'/api/widget/editor').json()['settings']['draft']
        self.assertEqual(saved['elements'][0]['x'],45)

    def test_nested_negative_rotations_remain_valid_when_grouped(self):
        doc=self.fixture("const g=M.createElement('group'),h=M.createElement('group'),a=M.createElement('shape'),b=M.createElement('shape');Object.assign(g,{x:100,y:30,width:200,height:140,rotation:-350});Object.assign(h,{parentId:g.id,x:20,y:15,width:130,height:90,rotation:-330});Object.assign(a,{parentId:h.id,x:15,y:10,width:50,height:20,rotation:-170});Object.assign(b,{x:420,y:60,width:60,height:30});d.elements=[g,h,a,b]")
        self.layer(doc['elements'][2]['id']);self.layer(doc['elements'][3]['id'],True)
        self.page.locator('[data-we-action="group"]').click()
        self.assertTrue(self.page.evaluate('VDGWidgetModel.validate(VDGWidgetEditor.getDocument()).ok'))

    def test_uploaded_svg_can_be_assigned_as_progress_mask(self):
        import hashlib
        doc=self.fixture("const a=M.createElement('progress');a.width=300;a.height=70;d.elements=[a]")
        self.layer(doc['elements'][0]['id'])
        self.page.locator('[data-we-action="resources"]').click()
        self.page.locator('[data-we-resource-upload]').set_input_files({'name':'Audit mask.svg','mimeType':'image/svg+xml','buffer':SVG})
        identity=hashlib.sha256(SVG).hexdigest()+'.svg'
        self.page.locator('[data-we-resource-row="'+identity+'"] [data-we-resource-op="use-mask"]').click()
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements[0].progress.maskAsset'),identity)
        expect(self.page.locator('.we-render mask image')).to_have_attribute('href','/widget-assets/'+identity)
        self.assertEqual(self.page.request.get(self.origin+'/widget-assets/'+identity).status,200)


if __name__=='__main__':unittest.main()
