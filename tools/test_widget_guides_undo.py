"""Small editor increment: object guides and keyboard undo, on disposable data."""
import unittest
from playwright.sync_api import expect
from test_widget_editor_geometry import WidgetGeometryTests


class GuidesUndoTests(WidgetGeometryTests):
    def shapes(self):
        return self.fixture("const a=M.createElement('shape'),b=M.createElement('shape');Object.assign(a,{x:40,y:45,width:80,height:50});Object.assign(b,{x:310,y:160,width:90,height:60});d.elements=[a,b]")

    def begin_drag(self, element):
        self.layer(element['id'])
        self.page.locator('[data-we-prop="x"]').blur()
        box=self.page.locator('[data-we-hit="'+element['id']+'"]').bounding_box()
        # Canvas scales uniformly; selection is stable before measuring.
        factor=box['width']/element['width']
        start=(box['x']+box['width']/2, box['y']+box['height']/2)
        self.page.mouse.move(*start); self.page.mouse.down()
        return start,factor

    def test_object_guides_snap_edges_and_drag_is_one_undo(self):
        d=self.shapes();a,b=d['elements']
        start,factor=self.begin_drag(a)
        self.page.mouse.move(start[0]+(b['x']-a['x']-3)*factor,start[1]+35*factor,steps=4)
        expect(self.page.locator('[data-we-guide="x"]')).to_be_visible()
        self.assertAlmostEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements[0].x'),b['x'],delta=.1)
        self.page.mouse.up()
        expect(self.page.locator('[data-we-guide]')).to_have_count(0)
        self.page.keyboard.press('Control+z')
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements[0].x'),a['x'])
        self.page.keyboard.press('Control+Shift+z')
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements[0].x'),b['x'])

    def test_alt_temporarily_disables_object_snap(self):
        d=self.shapes();a,b=d['elements']
        start,factor=self.begin_drag(a)
        self.page.keyboard.down('Alt')
        self.page.mouse.move(start[0]+(b['x']-a['x']-3)*factor,start[1]+35*factor)
        self.assertAlmostEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements[0].x'),b['x']-3,delta=.1)
        expect(self.page.locator('[data-we-guide]')).to_have_count(0)
        self.page.mouse.up();self.page.keyboard.up('Alt')

    def test_ctrl_z_with_russian_layout_uses_physical_key(self):
        self.editor();self.page.locator('[data-we-action="add-shape"]').click()
        count=self.page.evaluate('VDGWidgetEditor.getDocument().elements.length')
        self.page.dispatch_event('body','keydown',{'key':'я','code':'KeyZ','ctrlKey':True,'bubbles':True})
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements.length'),count-1)
        self.page.dispatch_event('body','keydown',{'key':'Я','code':'KeyZ','ctrlKey':True,'shiftKey':True,'bubbles':True})
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements.length'),count)

    def test_ctrl_z_in_property_field_commits_pending_edit_then_undoes(self):
        self.editor();self.page.locator('[data-we-action="add-shape"]').click()
        field=self.page.locator('[data-we-prop="x"]');before=field.input_value()
        field.fill('123')
        field.press('Control+z')
        expect(self.page.locator('[data-we-prop="x"]')).to_have_value(before)
        self.page.keyboard.press('Control+y')
        expect(self.page.locator('[data-we-prop="x"]')).to_have_value('123')

    def test_undo_last_canvas_action_while_unchanged_property_has_focus(self):
        self.editor()
        count=self.page.evaluate('VDGWidgetEditor.getDocument().elements.length')
        self.page.locator('[data-we-action="add-shape"]').click()
        self.page.locator('[data-we-prop="x"]').focus()
        self.page.keyboard.press('Control+z')
        self.assertEqual(self.page.evaluate('VDGWidgetEditor.getDocument().elements.length'),count)


if __name__=='__main__':unittest.main()
