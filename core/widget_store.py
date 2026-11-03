"""Strict portable widget documents and atomic, revision-controlled local storage."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import math
import mimetypes
import os
import re
import threading
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from safe_json import save_json as _save_json

LOCK = threading.RLock()
MAX_ASSET_BYTES = 16 * 1024 * 1024
MAX_IMPORT_BYTES = 64 * 1024 * 1024
ASSET_RE = re.compile(r'[0-9a-f]{64}\.(?:png|jpg|jpeg|webp|gif|svg|woff|woff2|ttf|otf)\Z')
PALETTE = {'primary', 'secondary', 'text', 'surface', 'track'}

class WidgetError(ValueError): pass
class RevisionConflict(WidgetError):
    def __init__(self, revision):
        self.revision = revision
        super().__init__('Документ изменён в другом окне. Обновите редактор.')

def obj(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys.split() if isinstance(keys, str) else keys):
        raise WidgetError(f'{label}: неверные или отсутствующие поля')
    return value

def number(value, lo, hi, label, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi or (integer and type(value) is not int):
        raise WidgetError(f'{label}: число вне допустимых границ')

def string(value, limit, label, nonempty=False):
    if not isinstance(value, str) or len(value) > limit or (nonempty and not value.strip()) or '\x00' in value:
        raise WidgetError(f'{label}: неверная строка')

def choice(value, choices, label):
    if not isinstance(value, str) or value not in choices.split(): raise WidgetError(f'{label}: неверное значение')

def boolean(value, label):
    if type(value) is not bool: raise WidgetError(f'{label}: ожидалось логическое значение')

def color(value, label, tokens=True):
    string(value, 120, label)
    if tokens and value.startswith('@') and value[1:] in PALETTE: return
    # Literal colours only. No var(), url(), expressions, declarations or CSS escapes.
    if re.fullmatch(r'#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[A-Za-z]{1,30}|(?:rgb|rgba|hsl|hsla)\([0-9.,%+\- /]+\)', value): return
    raise WidgetError(f'{label}: недопустимый цвет')

def asset_id(value, label):
    if value != '' and (not isinstance(value, str) or not ASSET_RE.fullmatch(value)): raise WidgetError(f'{label}: неверный ID ресурса')

def referenced_assets(doc):
    result = set()
    for e in doc['elements']:
        for value in (e['style']['fontAsset'], e['image']['asset'], e['progress']['maskAsset'], e['progress']['imageAsset']):
            if value: result.add(value)
    return result

def validate_document(value, assets=None):
    obj(value, 'schemaVersion id name width height background palette elements', 'document')
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1: raise WidgetError('Неподдерживаемая схема виджета')
    string(value['id'], 80, 'id', True); string(value['name'], 160, 'name', True)
    for k in ('width', 'height'): number(value[k], 16, 8192, k, True)
    color(value['background'], 'background', False)
    obj(value['palette'], PALETTE, 'palette')
    for k, v in value['palette'].items(): color(v, k, False)
    if not isinstance(value['elements'], list) or len(value['elements']) > 100: raise WidgetError('Допускается до 100 слоёв')
    ids = {}
    for e in value['elements']:
        obj(e, 'id type name parentId x y width height rotation opacity visible locked style text format textFit minFontSize progress image group anchor condition animation custom', 'element')
        string(e['id'], 80, 'element.id', True); string(e['name'], 160, 'element.name')
        if e['id'] in ids: raise WidgetError('Повторяющийся ID слоя')
        ids[e['id']] = e
        choice(e['type'], 'text progress shape image group custom', 'type')
        if e['parentId'] is not None: string(e['parentId'], 80, 'parentId', True)
        for k in ('x', 'y'): number(e[k], -16384, 16384, k)
        for k in ('width', 'height'): number(e[k], 1, 8192, k)
        number(e['rotation'], -360, 360, 'rotation'); number(e['opacity'], 0, 1, 'opacity')
        for k in ('visible', 'locked'): boolean(e[k], k)
        s = obj(e['style'], 'fill fill2 gradient gradientAngle stroke strokeWidth radius shadowColor shadowBlur shadowX shadowY fontFamily fontAsset fontSize fontWeight lineHeight letterSpacing textAlign textTransform textStrokeColor textStrokeWidth', 'style')
        for k in ('fill', 'fill2', 'stroke', 'shadowColor', 'textStrokeColor'): color(s[k], k)
        boolean(s['gradient'], 'gradient')
        for k, lo, hi in [('gradientAngle', -360, 360), ('strokeWidth', 0, 1024), ('radius', 0, 9999), ('shadowBlur', 0, 1024), ('shadowX', -8192, 8192), ('shadowY', -8192, 8192), ('fontSize', 1, 2048), ('fontWeight', 100, 1000), ('lineHeight', .1, 10), ('letterSpacing', -100, 100), ('textStrokeWidth', 0, 100)]: number(s[k], lo, hi, k)
        string(s['fontFamily'], 160, 'fontFamily'); asset_id(s['fontAsset'], 'fontAsset')
        if not re.fullmatch(r'[\w ,\-]+', s['fontFamily'], re.UNICODE): raise WidgetError('Неверное имя шрифта')
        choice(s['textAlign'], 'left center right', 'textAlign'); choice(s['textTransform'], 'none uppercase lowercase capitalize', 'textTransform')
        string(e['text'], 4000, 'text'); choice(e['textFit'], 'wrap shrink ellipsis scroll', 'textFit'); number(e['minFontSize'], 1, 2048, 'minFontSize')
        f = obj(e['format'], 'decimals currency compact rounding', 'format')
        number(f['decimals'], 0, 4, 'decimals', True); choice(f['currency'], 'code symbol none', 'currency'); boolean(f['compact'], 'compact'); choice(f['rounding'], 'round floor', 'rounding')
        p = obj(e['progress'], 'shape direction track gap segments startAngle sweep thickness maskAsset imageAsset overflow', 'progress')
        choice(p['shape'], 'bar ring arc segments mask', 'shape'); choice(p['direction'], 'right left up down center', 'direction'); color(p['track'], 'track'); choice(p['overflow'], 'clamp', 'overflow')
        for k, lo, hi in [('gap', 0, 8192), ('segments', 1, 1000), ('startAngle', -360, 360), ('sweep', 0, 360), ('thickness', 0, 8192)]: number(p[k], lo, hi, k, k == 'segments')
        for k in ('maskAsset', 'imageAsset'): asset_id(p[k], k)
        i = obj(e['image'], 'asset fit positionX positionY', 'image'); asset_id(i['asset'], 'asset'); choice(i['fit'], 'contain cover stretch', 'fit')
        for k in ('positionX', 'positionY'): number(i[k], 0, 100, k)
        g = obj(e['group'], 'layout gap padding align', 'group'); choice(g['layout'], 'free horizontal vertical', 'layout'); choice(g['align'], 'start center end', 'align')
        for k in ('gap', 'padding'): number(g[k], 0, 8192, k)
        a = obj(e['anchor'], 'horizontal vertical', 'anchor'); choice(a['horizontal'], 'left center right', 'horizontal'); choice(a['vertical'], 'top center bottom', 'vertical')
        c = obj(e['condition'], 'enabled metric op value action color', 'condition'); boolean(c['enabled'], 'enabled'); choice(c['metric'], 'percent current remaining', 'metric'); choice(c['op'], 'gte lte', 'op'); number(c['value'], -1e15, 1e15, 'value'); choice(c['action'], 'show hide color', 'action'); color(c['color'], 'color')
        a = obj(e['animation'], 'duration easing event effect threshold intensity', 'animation'); number(a['duration'], 0, 60000, 'duration'); choice(a['easing'], 'linear ease ease-in ease-out ease-in-out', 'easing'); choice(a['event'], 'none donation goal milestone', 'event'); choice(a['effect'], 'none fade pulse slide glow', 'effect'); number(a['threshold'], 0, 1000000, 'threshold'); number(a['intensity'], 0, 100, 'intensity')
        c = obj(e['custom'], 'html css js fields values', 'custom')
        for k in ('html', 'css', 'js'): string(c[k], 200000, k)
        if not isinstance(c['fields'], list) or len(c['fields']) > 100 or not isinstance(c['values'], dict): raise WidgetError('Неверные поля custom')
        keys = set()
        for f in c['fields']:
            obj(f, 'key label type default', 'field'); string(f['key'], 80, 'key', True); string(f['label'], 160, 'label'); choice(f['type'], 'text number color boolean', 'field.type')
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', f['key']) or f['key'] in keys: raise WidgetError('Неверный ключ custom')
            keys.add(f['key'])
            for v in (f['default'], c['values'].get(f['key'], f['default'])):
                if f['type'] == 'number': number(v, -1e15, 1e15, 'custom.number')
                elif f['type'] == 'boolean': boolean(v, 'custom.boolean')
                elif f['type'] == 'color': color(v, 'custom.color')
                else: string(v, 4000, 'custom.text')
        if set(c['values']) - keys: raise WidgetError('Необъявленные значения custom')
    for e in ids.values():
        seen = {e['id']}; parent = e['parentId']; depth = 0
        while parent is not None:
            if parent in seen or parent not in ids or ids[parent]['type'] != 'group': raise WidgetError('Цикл или неверная группа')
            seen.add(parent); depth += 1
            if depth > 8: raise WidgetError('Слишком глубокая вложенность')
            parent = ids[parent]['parentId']
    if assets is not None and referenced_assets(value) - set(assets): raise WidgetError('Ресурс документа отсутствует')
    return copy.deepcopy(value)

def default_settings():
    return dict(schemaVersion=1, revision=0, draft=None, active=None, previousActive=None, saved=[])

def validate_asset_names(value):
    if not isinstance(value, dict) or len(value) > 10000: raise WidgetError('Неверный список названий ресурсов')
    for identity, name in value.items():
        if not isinstance(identity, str) or not ASSET_RE.fullmatch(identity): raise WidgetError('Неверный ID ресурса')
        string(name, 160, 'Название ресурса', True)
    return copy.deepcopy(value)


def validate_settings(value, assets=None):
    if isinstance(value, dict) and 'assetNames' in value:
        validate_asset_names(value['assetNames'])
    keys = 'schemaVersion revision draft active previousActive saved' + (' assetNames' if isinstance(value, dict) and 'assetNames' in value else '')
    obj(value, keys, 'settings')
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1: raise WidgetError('Неподдерживаемая схема хранилища')
    number(value['revision'], 0, 2**53-1, 'revision', True)
    if not isinstance(value['saved'], list) or len(value['saved']) > 100: raise WidgetError('Слишком много сохранённых виджетов')
    docs = [v for v in [value['draft'], value['active'], value['previousActive']] if v is not None] + value['saved']
    for doc in docs: validate_document(doc, assets)
    if len({d['id'] for d in value['saved']}) != len(value['saved']): raise WidgetError('Повторяющиеся сохранённые ID')
    return copy.deepcopy(value)

def validate_asset(name, data):
    ext = Path(name).suffix.lower().lstrip('.')
    if ext not in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'woff', 'woff2', 'ttf', 'otf'} or not data or len(data) > MAX_ASSET_BYTES: raise WidgetError('Неподдерживаемый ресурс или размер больше 16 МБ')
    signatures = {'png': b'\x89PNG\r\n\x1a\n', 'jpg': b'\xff\xd8\xff', 'jpeg': b'\xff\xd8\xff', 'gif': b'GIF8', 'webp': b'RIFF', 'woff': b'wOFF', 'woff2': b'wOF2', 'ttf': b'\x00\x01\x00\x00', 'otf': b'OTTO'}
    if ext != 'svg' and not data.startswith(signatures[ext]): raise WidgetError('Содержимое не соответствует типу ресурса')
    if ext == 'webp' and data[8:12] != b'WEBP': raise WidgetError('Некорректный WebP')
    if ext == 'svg':
        if re.search(br'<!DOCTYPE|<!ENTITY|<\?(?!xml\s)', data, re.I): raise WidgetError('SVG entities и инструкции обработки запрещены')
        class SVGBuilder(ET.TreeBuilder):
            # XML events operate after encoding detection, unlike raw-byte scans.
            def pi(self, target, text):
                raise WidgetError('Инструкции обработки SVG запрещены')
            def doctype(self, name, pubid, system):
                raise WidgetError('SVG doctype и entities запрещены')
        try: root = ET.fromstring(data, parser=ET.XMLParser(target=SVGBuilder()))
        except ET.ParseError as error: raise WidgetError('Некорректный SVG') from error
        if root.tag.split('}')[-1] != 'svg': raise WidgetError('Ожидался SVG')
        for node in root.iter():
            if node.tag.split('}')[-1].lower() in {'script', 'foreignobject', 'iframe', 'object', 'embed', 'audio', 'video', 'style', 'animate', 'set', 'animatetransform', 'animatemotion'}: raise WidgetError('Активное содержимое SVG запрещено')
            for key, val in node.attrib.items():
                key = key.split('}')[-1].lower()
                if key.startswith('on') or key == 'style' or (key in {'href', 'src'} and not val.startswith('#')) or re.search(r'url\(\s*[\'"]?(?!#)', val, re.I): raise WidgetError('Внешние ссылки SVG запрещены')
    return ext

class WidgetStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).parent / 'widget_settings.json'
        self.assets_dir = self.path.parent / 'widget_assets'

    def _assets_root(self):
        """A local resource directory must not redirect through a link/junction."""
        try:
            expected = self.path.parent.resolve() / 'widget_assets'
            resolved = self.assets_dir.resolve()
            if (self.assets_dir.is_symlink() or getattr(self.assets_dir, 'is_junction', lambda: False)()
                    or resolved != expected):
                raise WidgetError('Каталог ресурсов не должен быть ссылкой или выходить за пределы core')
            return resolved
        except (OSError, RuntimeError) as error:
            raise WidgetError('Небезопасный путь каталога ресурсов') from error

    def _asset_ids(self):
        self._assets_root()
        return {p.name for p in self.assets_dir.iterdir() if p.is_file() and not p.is_symlink() and ASSET_RE.fullmatch(p.name)} if self.assets_dir.exists() else set()

    def load(self):
        with LOCK:
            if not self.path.exists(): return default_settings()
            try: return validate_settings(json.loads(self.path.read_text(encoding='utf-8')), self._asset_ids())
            except (ValueError, UnicodeError, TypeError) as error: raise WidgetError('Хранилище виджетов повреждено или несовместимо; оригинал сохранён') from error

    def mutate(self, action, request, asset_names=None):
        keys = {'revision', 'document'} if action in {'draft', 'save'} else {'revision', 'id'} if action in {'load', 'delete'} else {'revision'}
        obj(request, keys, 'request')
        with LOCK:
            settings = self.load()
            number(request['revision'], 0, 2**53-1, 'revision', True)
            if request['revision'] != settings['revision']: raise RevisionConflict(settings['revision'])
            if action in {'draft', 'save'}:
                doc = validate_document(request['document'], self._asset_ids()); settings['draft'] = doc
                if action == 'save': settings['saved'] = [d for d in settings['saved'] if d['id'] != doc['id']] + [copy.deepcopy(doc)]
            elif action == 'apply':
                if settings['draft'] is None: raise WidgetError('Сначала создайте черновик')
                settings['previousActive'] = settings['active']; settings['active'] = copy.deepcopy(settings['draft'])
            elif action == 'load':
                found = next((d for d in settings['saved'] if d['id'] == request['id']), None)
                if found is None: raise WidgetError('Сохранённый виджет не найден')
                settings['draft'] = copy.deepcopy(found)
            elif action == 'delete':
                found = next((d for d in settings['saved'] if d['id'] == request['id']), None)
                if found is None: raise WidgetError('Сохранённый виджет не найден')
                settings['saved'] = [d for d in settings['saved'] if d['id'] != request['id']]
            elif action == 'revert':
                settings['active'], settings['previousActive'] = settings['previousActive'], settings['active']
                settings['draft'] = copy.deepcopy(settings['active'])
            else: raise WidgetError('Неизвестная операция')
            if asset_names is not None: settings['assetNames'] = {**settings.get('assetNames', {}), **validate_asset_names(asset_names)}
            settings['revision'] += 1
            validate_settings(settings, self._asset_ids()); _save_json(self.path, settings)
            return settings

    def asset_bytes(self, asset):
        if not isinstance(asset, str) or not ASSET_RE.fullmatch(asset): raise WidgetError('Неверный ID ресурса')
        root = self._assets_root()
        path = self.assets_dir / asset
        if path.is_symlink() or path.resolve().parent != root or not path.is_file(): raise WidgetError('Ресурс не найден')
        data = path.read_bytes(); validate_asset(asset, data)
        if hashlib.sha256(data).hexdigest() != asset.split('.')[0]: raise WidgetError('Повреждённый ресурс')
        return data, mimetypes.guess_type(asset)[0] or 'application/octet-stream'

    def _trash_root(self):
        root = self._assets_root(); trash = self.assets_dir / '.trash'
        if trash.is_symlink() or getattr(trash, 'is_junction', lambda: False)() or trash.resolve() != root / '.trash':
            raise WidgetError('Небезопасный путь корзины')
        return trash

    def _asset_record(self, identity, path, settings):
        uses = []
        for kind in ('draft', 'active', 'previousActive'):
            doc = settings[kind]
            if doc and identity in referenced_assets(doc):
                uses.append(dict(kind=kind, name={'draft':'Черновик','active':'Виджет в OBS','previousActive':'Предыдущее оформление'}[kind]))
        for doc in settings['saved']:
            if identity in referenced_assets(doc): uses.append(dict(kind='saved', name=doc['name']))
        return dict(id=identity, name=settings.get('assetNames', {}).get(identity, identity),
                    kind='font' if identity.endswith(('.woff', '.woff2', '.ttf', '.otf')) else 'image',
                    size=path.stat().st_size, url='/widget-assets/'+identity, usedBy=uses)

    def assets(self):
        with LOCK:
            settings = self.load()
            return [self._asset_record(a, self.assets_dir/a, settings) for a in sorted(self._asset_ids())]

    def trashed_assets(self):
        with LOCK:
            settings = self.load(); trash = self._trash_root()
            return [self._asset_record(p.name, p, settings) for p in sorted(trash.iterdir())
                    if ASSET_RE.fullmatch(p.name) and p.is_file() and not p.is_symlink()] if trash.exists() else []

    def manage_asset(self, action, request):
        obj(request, 'id name' if action == 'rename' else 'id', 'request')
        identity = request['id']
        if not isinstance(identity, str) or not ASSET_RE.fullmatch(identity): raise WidgetError('Неверный ID ресурса')
        with LOCK:
            settings = self.load(); self._assets_root(); trash = self._trash_root()
            live = self.assets_dir / identity; deleted = trash / identity
            if live.is_symlink() or deleted.is_symlink(): raise WidgetError('Недопустимый путь ресурса')
            if action == 'rename':
                string(request['name'], 160, 'Название ресурса', True)
                if not live.is_file(): raise WidgetError('Ресурс не найден')
                settings.setdefault('assetNames', {})[identity] = request['name'].strip()
                _save_json(self.path, settings)
            elif action == 'trash':
                if not live.is_file(): raise WidgetError('Ресурс не найден')
                if self._asset_record(identity, live, settings)['usedBy']:
                    raise WidgetError('Ресурс используется в оформлении. Сначала уберите его из всех вариантов.')
                trash.mkdir(parents=True, exist_ok=True); os.replace(live, deleted)
            elif action == 'restore':
                if not deleted.is_file(): raise WidgetError('Ресурс не найден в корзине')
                data = deleted.read_bytes(); validate_asset(identity, data)
                if hashlib.sha256(data).hexdigest() != identity.split('.')[0]: raise WidgetError('Повреждённый ресурс')
                os.replace(deleted, live)
            else: raise WidgetError('Неизвестная операция с ресурсом')

    def upload_asset(self, name, data, persist_name=True):
        with LOCK:
            self._assets_root()
            settings = self.load()  # Never mutate anything alongside an invalid store.
            ext = validate_asset(name, data); asset = hashlib.sha256(data).hexdigest()+'.'+ext
            self.assets_dir.mkdir(parents=True, exist_ok=True)
            dest = self.assets_dir / asset
            if dest.is_symlink(): raise WidgetError('Недопустимый путь ресурса')
            added = not dest.exists()
            if added:
                temp = dest.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                try: temp.write_bytes(data); os.replace(temp, dest)
                finally: temp.unlink(missing_ok=True)
            try:
                if persist_name:
                    settings.setdefault('assetNames', {}).setdefault(asset, Path(str(name).replace('\\', '/')).name[:160] or asset)
                    validate_asset_names(settings['assetNames'])
                    _save_json(self.path, settings)
            except Exception:
                if added: dest.unlink(missing_ok=True)
                raise
            return self._asset_record(asset, dest, settings)

    def export_document(self, kind, identity=''):
        with LOCK:
            settings = self.load()
            if kind == 'saved': doc = next((d for d in settings['saved'] if d['id'] == identity), None)
            elif kind in {'draft', 'active'}: doc = settings[kind]
            else: raise WidgetError('Неизвестный тип экспорта')
            if doc is None: raise WidgetError('Нет документа для экспорта')
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr('widget.json', json.dumps(doc, ensure_ascii=False))
                names = {a: settings.get('assetNames', {}).get(a, a) for a in referenced_assets(doc)}
                z.writestr('asset-names.json', json.dumps(names, ensure_ascii=False))
                for a in sorted(referenced_assets(doc)): z.writestr('assets/'+a, self.asset_bytes(a)[0])
            return output.getvalue()

    def import_document(self, raw, revision):
        if not raw or len(raw) > MAX_IMPORT_BYTES: raise WidgetError('Импорт превышает 64 МБ')
        assets = {}; names = {}
        try:
            if raw[:2] == b'PK':
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    seen = set(); total = 0
                    for info in z.infolist():
                        name = info.filename; total += info.file_size
                        if name in seen or len(seen) > 500 or total > MAX_IMPORT_BYTES or (info.external_attr >> 16) & 0o170000 == 0o120000: raise WidgetError('Недопустимый ZIP')
                        seen.add(name)
                        if name not in {'widget.json', 'asset-names.json'} and not (name.startswith('assets/') and ASSET_RE.fullmatch(name[7:])): raise WidgetError('Небезопасный путь ZIP')
                        if name.startswith('assets/'):
                            data = z.read(info); validate_asset(name[7:], data)
                            if hashlib.sha256(data).hexdigest() != name[7:].split('.')[0]: raise WidgetError('Контрольная сумма ресурса не совпала')
                            assets[name[7:]] = data
                    doc = json.loads(z.read('widget.json').decode('utf-8'))
                    if 'asset-names.json' in seen: names = validate_asset_names(json.loads(z.read('asset-names.json').decode('utf-8')))
                    validate_document(doc)
                    if set(names) - referenced_assets(doc): raise WidgetError('Названия относятся к посторонним ресурсам')
            else: doc = json.loads(raw.decode('utf-8-sig'))
        except (ValueError, KeyError, UnicodeError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error: raise WidgetError('Некорректный файл виджета') from error
        with LOCK:
            settings = self.load()
            number(revision, 0, 2**53-1, 'revision', True)
            if revision != settings['revision']: raise RevisionConflict(settings['revision'])
            validate_document(doc, self._asset_ids() | set(assets))
            added = []
            try:
                for name, data in assets.items():
                    if name not in self._asset_ids(): self.upload_asset(name, data, persist_name=False); added.append(name)
                return self.mutate('draft', dict(document=doc, revision=revision), asset_names=names)
            except Exception:
                for name in added: (self.assets_dir/name).unlink(missing_ok=True)
                raise
