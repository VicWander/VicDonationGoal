"""Resource library regression tests; only temporary stores are modified."""
import json
import unittest
from test_widget_backend import WidgetTests, document, element, ws


class ResourceTests(WidgetTests):
    def image(self):
        return self.store.upload_asset('Моя картинка.svg', b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>')

    def test_names_persist_and_export_import_with_document(self):
        asset=self.image()
        self.store.manage_asset('rename', {'id':asset['id'],'name':'Моя маска'})
        self.assertEqual(ws.WidgetStore(self.store.path).assets()[0]['name'],'Моя маска')
        doc=document(); node=element();node['type']='image';node['image']['asset']=asset['id'];doc['elements']=[node]
        self.store.mutate('draft',dict(document=doc,revision=0))
        package=self.store.export_document('draft')
        other=ws.WidgetStore(self.root/'other/core/widget_settings.json')
        other.import_document(package,0)
        self.assertEqual(other.assets()[0]['name'],'Моя маска')
        import portability
        payload={'core/widget_settings.json':self.store.path.read_bytes(),
                 'core/widget_assets/'+asset['id']:(self.store.assets_dir/asset['id']).read_bytes()}
        self.assertIn('core/widget_settings.json',portability.validate_user_payload(payload))

    def test_used_assets_cannot_be_trashed_in_any_saved_state(self):
        asset=self.image(); doc=document();node=element();node['style']['fontAsset']=asset['id'];doc['elements']=[node]
        self.store.mutate('save',dict(document=doc,revision=0))
        self.store.mutate('apply',dict(revision=1))
        empty=document();empty['id']='other'
        self.store.mutate('draft',dict(document=empty,revision=2))
        self.store.mutate('apply',dict(revision=3))
        record=self.store.assets()[0]
        self.assertEqual({use['kind'] for use in record['usedBy']},{'previousActive','saved'})
        with self.assertRaises(ws.WidgetError):self.store.manage_asset('trash',{'id':asset['id']})
        self.assertTrue((self.store.assets_dir/asset['id']).exists())

    def test_unused_trash_and_restore_are_reversible(self):
        asset=self.image()
        self.store.manage_asset('trash',{'id':asset['id']})
        self.assertEqual(self.store.assets(),[])
        self.assertEqual(self.store.trashed_assets()[0]['name'],'Моя картинка.svg')
        self.store.manage_asset('restore',{'id':asset['id']})
        self.assertEqual(self.store.assets()[0]['id'],asset['id'])
        self.assertEqual(self.store.trashed_assets(),[])
        with self.assertRaises(ws.WidgetError):self.store.manage_asset('rename',{'id':'../server.py','name':'Bad'})

    def test_failed_name_save_does_not_leave_an_untracked_upload(self):
        from unittest.mock import patch
        with patch.object(ws,'_save_json',side_effect=OSError('fixture full disk')):
            with self.assertRaises(OSError):self.image()
        self.assertEqual(self.store.assets(),[])

    def test_corrupt_metadata_is_preserved(self):
        self.image();settings=self.store.load();settings['assetNames']={'../bad':'Name'}
        self.store.path.write_text(json.dumps(settings),encoding='utf-8')
        before=self.store.path.read_bytes()
        with self.assertRaises(ws.WidgetError):self.store.assets()
        self.assertEqual(self.store.path.read_bytes(),before)


if __name__=='__main__':unittest.main()
