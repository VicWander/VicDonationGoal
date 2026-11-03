"""Offline widget persistence/security regressions; fixtures never touch live data."""
import copy
import io
import json
import sys
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / 'core')]
try:
    import widget_store as ws
except ImportError:
    ws = None

def document():
    return dict(schemaVersion=1, id='test', name='Test', width=700, height=120,
                background='transparent', palette=dict(primary='#fff', secondary='#aaa', text='white', surface='black', track='gray'), elements=[])

def element(identity='layer'):
    return dict(id=identity, type='text', name='Text', parentId=None, x=0, y=0, width=100, height=40,
      rotation=0, opacity=1, visible=True, locked=False, text='{{title}}', textFit='wrap', minFontSize=12,
      style=dict(fill='@primary', fill2='@secondary', gradient=False, gradientAngle=0, stroke='transparent', strokeWidth=0,
        radius=0, shadowColor='transparent', shadowBlur=0, shadowX=0, shadowY=0, fontFamily='Arial', fontAsset='',
        fontSize=30, fontWeight=700, lineHeight=1.2, letterSpacing=0, textAlign='left', textTransform='none', textStrokeColor='transparent', textStrokeWidth=0),
      format=dict(decimals=0, currency='code', compact=False, rounding='round'),
      progress=dict(shape='bar', direction='right', track='@track', gap=4, segments=10, startAngle=-90, sweep=360, thickness=12, maskAsset='', imageAsset='', overflow='clamp'),
      image=dict(asset='', fit='contain', positionX=50, positionY=50), group=dict(layout='free', gap=8, padding=0, align='start'),
      anchor=dict(horizontal='left', vertical='top'), condition=dict(enabled=False, metric='percent', op='gte', value=100, action='show', color='@primary'),
      animation=dict(duration=450, easing='ease-out', event='none', effect='none', threshold=50, intensity=1), custom=dict(html='', css='', js='', fields=[], values={}))

class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ws, 'widget_store must implement the editor persistence contract')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = ws.WidgetStore(self.root / 'core/widget_settings.json')

    def test_open_is_read_only_and_draft_never_changes_active(self):
        self.assertIsNone(self.store.load()['active'])
        self.assertFalse(self.store.path.exists())
        self.store.mutate('draft', dict(revision=0, document=document()))
        self.assertIsNone(self.store.load()['active'])
        applied = self.store.mutate('apply', dict(revision=1))
        self.assertEqual(applied['active']['name'], 'Test')
        changed = document(); changed['name'] = 'Changed'
        self.store.mutate('draft', dict(revision=2, document=changed))
        self.assertEqual(self.store.load()['active']['name'], 'Test')
        with self.assertRaises(ws.RevisionConflict):
            self.store.mutate('apply', dict(revision=1))

    def test_future_corrupt_store_cannot_be_overwritten(self):
        self.store.path.parent.mkdir(parents=True)
        for raw in (b'{broken', b'{"schemaVersion":2}', b'null'):
            self.store.path.write_bytes(raw)
            with self.assertRaises(ws.WidgetError): self.store.mutate('draft', dict(revision=0, document=document()))
            self.assertEqual(self.store.path.read_bytes(), raw)

    def test_schema_rejects_nonfinite_css_and_unknown_fields(self):
        for key, value in [('width', True), ('width', 8193), ('background', 'url(https://bad)'), ('schemaVersion', 2), ('extra', 1)]:
            bad = document(); bad[key] = value
            with self.assertRaises(ws.WidgetError): ws.validate_document(bad)

    def test_asset_and_export_import_roundtrip_and_zip_traversal(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="4" height="4"/></svg>'
        asset = self.store.upload_asset('picture.svg', svg)
        self.assertEqual(self.store.asset_bytes(asset['id'])[0], svg)
        for bad in (b'<svg><script>alert(1)</script></svg>', b'<svg><image href="https://bad"/></svg>',
                    b'<?xml-stylesheet type="text/xsl" href="https://bad"?><svg/>'):
            with self.assertRaises(ws.WidgetError): self.store.upload_asset('evil.svg', bad)
        with self.assertRaises(ws.WidgetError): self.store.asset_bytes('../server.py')
        self.store.mutate('draft', dict(revision=0, document=document()))
        archive = self.store.export_document('draft')
        other = ws.WidgetStore(self.root / 'other/widget_settings.json')
        self.assertEqual(other.import_document(archive, 0)['draft']['name'], 'Test')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as z:
            z.writestr('widget.json', json.dumps(document())); z.writestr('../evil', b'x')
        with self.assertRaises(ws.WidgetError): other.import_document(output.getvalue(), 1)

    def test_atomic_write_failure_keeps_last_good_store(self):
        self.store.mutate('draft', dict(revision=0, document=document()))
        before = self.store.path.read_bytes()
        with patch.object(ws, '_save_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.store.mutate('apply', dict(revision=1))
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_full_backup_allowlist_and_asset_validation(self):
        import portability
        asset = self.store.upload_asset('ok.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.store.mutate('draft', dict(revision=0, document=document()))
        self.assertTrue(portability.is_user_data_path('core/widget_settings.json'))
        self.assertTrue(portability.is_user_data_path('core/widget_assets/'+asset['id']))
        self.assertFalse(portability.is_user_data_path('core/widget_assets/server.py'))
        archive, _ = portability.create_backup_bytes(self.root)
        _, payload = portability.inspect_backup_bytes(archive)
        self.assertIn('core/widget_assets/'+asset['id'], payload)
        payload['core/widget_assets/'+asset['id']] = b'<svg><script/></svg>'
        with self.assertRaises(portability.PortabilityError): portability.validate_user_payload(payload)

    def test_complete_elements_hierarchy_and_references(self):
        doc = document(); doc['elements'] = [element()]
        self.store.mutate('save', dict(document=doc, revision=0))
        invalid = []
        for mutate in [lambda e: e.update(x=float('nan')), lambda e: e.update(parentId='missing'),
                       lambda e: e['style'].update(fill='red;position:fixed'),
                       lambda e: e['image'].update(asset='a'*64+'.svg'),
                       lambda e: e['custom'].update(values={'undeclared':'value'})]:
            bad = copy.deepcopy(doc); mutate(bad['elements'][0]); invalid.append(bad)
        cycle = copy.deepcopy(doc); cycle['elements'][0].update(type='group', parentId='layer'); invalid.append(cycle)
        duplicate = copy.deepcopy(doc); duplicate['elements'].append(element()); invalid.append(duplicate)
        for bad in invalid:
            with self.subTest(doc=bad), self.assertRaises(ws.WidgetError):
                self.store.mutate('draft', dict(document=bad, revision=1))
        self.assertEqual(self.store.load()['revision'], 1)

    def test_concurrent_writers_conflict_instead_of_losing_update(self):
        def write(name):
            doc = document(); doc['name'] = name
            try: self.store.mutate('draft', dict(document=doc, revision=0)); return 'saved'
            except ws.RevisionConflict: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(write, ['one', 'two'])), ['conflict', 'saved'])
        self.assertEqual(self.store.load()['revision'], 1)

    def test_import_store_failure_rolls_back_new_assets(self):
        asset = self.store.upload_asset('ok.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>')
        doc = document(); doc['elements'] = [element()]; doc['elements'][0]['image']['asset'] = asset['id']
        self.store.mutate('draft', dict(revision=0, document=doc))
        archive = self.store.export_document('draft')
        other = ws.WidgetStore(self.root / 'other/widget_settings.json')
        with patch.object(ws, '_save_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): other.import_document(archive, 0)
        self.assertFalse(other.path.exists())
        self.assertEqual(other.assets(), [])

    def test_revert_restores_prior_active_and_saved_load_preserves_active(self):
        first = document()
        self.store.mutate('save', dict(revision=0, document=first))
        self.store.mutate('apply', dict(revision=1))
        second = document(); second.update(id='second', name='Second')
        self.store.mutate('draft', dict(revision=2, document=second))
        self.store.mutate('apply', dict(revision=3))
        loaded = self.store.mutate('load', dict(revision=4, id='test'))
        self.assertEqual(loaded['active']['name'], 'Second')
        self.assertEqual(loaded['draft']['name'], 'Test')
        reverted = self.store.mutate('revert', dict(revision=5))
        self.assertEqual(reverted['active']['name'], 'Test')
        self.assertEqual(reverted['previousActive']['name'], 'Second')

    def test_archive_unsupported_compression_is_validation_error(self):
        import struct
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as z: z.writestr('widget.json', json.dumps(document()))
        raw = bytearray(output.getvalue())
        struct.pack_into('<H', raw, 8, 99)
        struct.pack_into('<H', raw, raw.index(b'PK\x01\x02')+10, 99)
        with self.assertRaises(ws.WidgetError): self.store.import_document(bytes(raw), 0)

    def test_full_restore_failure_rolls_back_assets_and_settings_together(self):
        import portability
        asset = self.store.upload_asset('ok.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>')
        doc = document(); doc['elements'] = [element()]; doc['elements'][0]['image']['asset'] = asset['id']
        self.store.mutate('draft', dict(revision=0, document=doc))
        archive, _ = portability.create_backup_bytes(self.root)
        _, payload = portability.inspect_backup_bytes(archive)
        destination = self.root / 'restore'
        original = portability._atomic_write
        def fail_settings(path, data):
            if path.name == 'widget_settings.json': raise OSError('disk full')
            return original(path, data)
        with patch.object(portability, '_atomic_write', fail_settings):
            with self.assertRaises(OSError): portability.apply_payload(destination, payload)
        self.assertFalse((destination/'core/widget_settings.json').exists())
        self.assertFalse((destination/'core/widget_assets'/asset['id']).exists())

    def test_svg_processing_instructions_are_rejected_in_all_xml_encodings(self):
        svg = '<?xml-stylesheet type="text/xsl" href="https://example.invalid/style.xsl"?><svg/>'
        for encoding in ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32']:
            with self.subTest(encoding=encoding), self.assertRaises(ws.WidgetError):
                self.store.upload_asset('external.svg', svg.encode(encoding))
        for encoding in ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be']:
            with self.subTest(encoding=encoding), self.assertRaises(ws.WidgetError):
                self.store.upload_asset('entity.svg', '<!DOCTYPE svg [<!ENTITY t "text">]><svg>&t;</svg>'.encode(encoding))
        self.assertEqual(self.store.upload_asset('safe.svg', '<svg width="2"/>'.encode('utf-16'))['kind'], 'image')

    def test_assets_directory_junction_cannot_read_or_write_outside_core(self):
        import subprocess
        import os
        outside = self.root / 'outside'; outside.mkdir()
        self.store.assets_dir.parent.mkdir(parents=True)
        if os.name == 'nt':
            # Directory junctions do not require Windows symlink privileges.
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(self.store.assets_dir), str(outside)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.addCleanup(lambda: os.rmdir(self.store.assets_dir))
        else:
            self.store.assets_dir.symlink_to(outside, target_is_directory=True)
        data = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        import hashlib
        asset = hashlib.sha256(data).hexdigest()+'.svg'
        (outside/asset).write_bytes(data)
        for operation in [lambda: self.store.assets(), lambda: self.store.asset_bytes(asset),
                          lambda: self.store.upload_asset('other.svg', b'<svg width="1"/>')]:
            with self.subTest(operation=operation), self.assertRaises(ws.WidgetError): operation()
        self.assertEqual([p.name for p in outside.iterdir()], [asset])
        import portability
        with self.assertRaises(portability.PortabilityError): portability.create_backup_bytes(self.root)
        with self.assertRaises(portability.PortabilityError):
            portability.apply_payload(self.root, {'core/widget_assets/'+asset: data})

    def test_restore_asset_file_symlink_cannot_overwrite_project_code(self):
        import portability
        import hashlib
        from contextlib import ExitStack
        data = b'<svg/>'; asset = hashlib.sha256(data).hexdigest()+'.svg'
        self.store.assets_dir.mkdir(parents=True)
        target = self.root/'core/server.py'; target.write_bytes(b'original code')
        link = self.store.assets_dir/asset
        with ExitStack() as stack:
            try: link.symlink_to(target)
            except OSError:
                # Windows lacks file-symlink permission here. Emulate only that
                # OS boundary while exercising actual import/path/write logic.
                original_resolve, original_islink = Path.resolve, Path.is_symlink
                # resolve() may canonicalize the user's Windows TEMP prefix.
                is_asset = lambda p: p.name == asset and p.parent.name == 'widget_assets'
                stack.enter_context(patch.object(Path, 'resolve', lambda p, *a, **kw: target if is_asset(p) else original_resolve(p, *a, **kw)))
                stack.enter_context(patch.object(Path, 'is_symlink', lambda p: True if is_asset(p) else original_islink(p)))
            with self.assertRaises(portability.PortabilityError):
                portability.apply_payload(self.root, {'core/widget_assets/'+asset: data})
        self.assertEqual(target.read_bytes(), b'original code')

if __name__ == '__main__': unittest.main()
