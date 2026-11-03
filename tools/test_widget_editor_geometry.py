"""Focused geometry regressions; run WidgetGeometryTests.test_* cases explicitly."""
from test_widget_editor_browser import WidgetEditorTests


class WidgetGeometryTests(WidgetEditorTests):
    def fixture(self, script):
        self.editor()
        document = self.page.evaluate("() => { const M=VDGWidgetModel,d=M.createDocument('Geometry');" + script + ";return d;}")
        revision = self.page.request.get(self.origin + '/api/widget/editor').json()['settings']['revision']
        result = self.page.request.post(self.origin + '/api/widget/draft', data={'document': document, 'revision': revision})
        self.assertEqual(result.status, 200)
        self.page.reload()
        self.page.evaluate('async()=>await window.VDGWidgetEditor.ready')
        return document

    def layer(self, id, shift=False):
        self.page.locator('[data-we-select="' + id + '"]').click(modifiers=['Shift'] if shift else [])

    def test_locked_multiselection_drag_and_inspector(self):
        d = self.fixture("const a=M.createElement('shape'),b=M.createElement('shape');Object.assign(a,{x:30,y:30,width:60,height:60,locked:true});Object.assign(b,{x:200,y:30,width:60,height:60});d.elements=[a,b]")
        a,b = d['elements']
        self.layer(a['id']); self.layer(b['id'], True)
        self.page.locator('[data-we-prop="x"]').fill('80')
        self.page.locator('[data-we-prop="x"]').dispatch_event('change')
        result = self.page.evaluate('VDGWidgetEditor.getDocument()')
        self.assertEqual(result['elements'][0]['x'], 30)
        box = self.page.locator('[data-we-hit="' + b['id'] + '"]').bounding_box()
        self.page.mouse.move(box['x']+10, box['y']+10); self.page.mouse.down()
        self.page.mouse.move(box['x']+50, box['y']+10); self.page.mouse.up()
        result = self.page.evaluate('VDGWidgetEditor.getDocument()')
        self.assertEqual(result['elements'][0]['x'], 30)

    def test_paste_child_after_original_group_deleted(self):
        d = self.fixture("const g=M.createElement('group'),a=M.createElement('shape');Object.assign(g,{x:50,y:40});Object.assign(a,{parentId:g.id,x:30,y:20,width:60,height:40});d.elements=[g,a]")
        g,a = d['elements']
        self.layer(a['id']); self.page.keyboard.press('Control+c')
        self.layer(g['id']); self.page.keyboard.press('Delete'); self.page.keyboard.press('Control+v')
        result = self.page.evaluate('VDGWidgetEditor.getDocument()')
        self.assertEqual(len(result['elements']), 1)
        self.assertIsNone(result['elements'][0]['parentId'])
        self.assertEqual(result['elements'][0]['x'], 96)
        self.assertEqual(result['elements'][0]['y'], 76)
        self.assertTrue(self.page.evaluate('VDGWidgetModel.validate(VDGWidgetEditor.getDocument()).ok'))

    def test_group_precise_resize_scales_nested_geometry_and_undo(self):
        d = self.fixture("const g=M.createElement('group'),a=M.createElement('shape');Object.assign(g,{x:30,y:30,width:200,height:100});Object.assign(a,{parentId:g.id,x:20,y:10,width:60,height:40});d.elements=[g,a]")
        self.layer(d['elements'][0]['id'])
        self.page.locator('[data-we-prop="width"]').fill('400')
        self.page.locator('[data-we-prop="width"]').dispatch_event('change')
        result = self.page.evaluate('VDGWidgetEditor.getDocument()')
        self.assertEqual(result['elements'][1]['x'], 40)
        self.assertEqual(result['elements'][1]['width'], 120)
        self.assertEqual(result['elements'][1]['height'], 40)
        self.page.locator('[data-we-action="undo"]').click()
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements[1].width'), 60)

    def test_rotated_group_child_overlay_and_drag_match_renderer(self):
        d = self.fixture("const g=M.createElement('group'),a=M.createElement('shape');Object.assign(g,{x:150,y:40,width:200,height:200,rotation:90});Object.assign(a,{parentId:g.id,x:20,y:30,width:50,height:40});d.elements=[g,a]")
        a = d['elements'][1]
        self.page.locator('[data-we-setting="snap"]').uncheck()
        self.page.wait_for_timeout(100)
        hit=self.page.locator('[data-we-hit="'+a['id']+'"]')
        render=self.page.locator('[data-widget-element="'+a['id']+'"]')
        hb,rb=hit.bounding_box(),render.bounding_box()
        self.assertAlmostEqual(hb['x'],rb['x'],delta=1)
        self.assertAlmostEqual(hb['y'],rb['y'],delta=1)
        self.page.mouse.move(hb['x']+hb['width']/2,hb['y']+hb['height']/2);self.page.mouse.down()
        self.page.mouse.move(hb['x']+hb['width']/2+30,hb['y']+hb['height']/2);self.page.mouse.up()
        result=self.page.evaluate('VDGWidgetEditor.getDocument().elements[1]')
        self.assertAlmostEqual(result['x'],a['x'],delta=1)
        self.assertLess(result['y'],a['y']-20)

    def test_group_pointer_resize_scales_child_and_locked_delete_is_ignored(self):
        d = self.fixture("const g=M.createElement('group'),a=M.createElement('shape'),b=M.createElement('shape');Object.assign(g,{x:30,y:30,width:200,height:100});Object.assign(a,{parentId:g.id,x:20,y:10,width:60,height:40});Object.assign(b,{x:450,y:40,width:30,height:30,locked:true});d.elements=[g,a,b]")
        g,a,b=d['elements']
        self.layer(g['id']);self.page.wait_for_timeout(100)
        handle=self.page.locator('[data-we-hit="'+g['id']+'"] [data-we-resize="se"]').bounding_box()
        self.page.mouse.move(handle['x']+handle['width']/2,handle['y']+handle['height']/2);self.page.mouse.down()
        self.page.mouse.move(handle['x']+handle['width']/2+50,handle['y']+handle['height']/2+25);self.page.mouse.up()
        result=self.page.evaluate('VDGWidgetEditor.getDocument()')
        self.assertGreater(result['elements'][0]['width'],200)
        self.assertAlmostEqual(result['elements'][1]['width']/60,result['elements'][0]['width']/200,delta=.01)
        self.layer(b['id']);self.page.keyboard.press('Delete')
        self.assertTrue(self.page.evaluate('(id)=>VDGWidgetEditor.getDocument().elements.some(e=>e.id===id)',b['id']))

    def test_automatic_group_child_cannot_silently_move(self):
        d=self.fixture("const g=M.createElement('group'),a=M.createElement('shape');Object.assign(g,{x:30,y:30,width:400,height:100});g.group.layout='horizontal';Object.assign(a,{parentId:g.id,x:20,y:10,width:60,height:40});d.elements=[g,a]")
        a=d['elements'][1]
        self.layer(a['id']);self.page.wait_for_timeout(100)
        self.assertTrue(self.page.locator('[data-we-prop="x"]').is_disabled())
        box=self.page.locator('[data-we-hit="'+a['id']+'"]').bounding_box()
        self.page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);self.page.mouse.down()
        self.page.mouse.move(box['x']+box['width']/2+40,box['y']+box['height']/2);self.page.mouse.up()
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements[1].x'),20)
        self.assertIn('Положение задаёт группа',self.page.locator('[data-we-status]').inner_text())


if __name__ == '__main__':
    import unittest
    unittest.main()
