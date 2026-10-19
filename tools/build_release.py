"""Build separate private/public release candidates from an explicit source allowlist."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'core'))
import portability
from tools.update_from_old import migrate

VERSION='1.4.6'
CODE_DIRS={'core','integrations','tools','docs'}
CODE_SUFFIXES={'.py','.js','.css','.html','.md','.svg','.png','.jpg','.jpeg','.webp','.ico','.woff','.woff2'}
ROOT_FILES={'VERSION','README.md','ROADMAP.md','requirements.txt','requirements_all.txt','LICENSE','LICENSE.md',
            'LICENSE.txt','.gitignore','safe_json.py','source_registry.py','UPDATE_GUIDE.md','CHANGELOG_v1.4.6.md'}
SECRET_KEYS=re.compile(r'(^|_)(token|secret|password|api_key|client_id|action_id|channel|login)($|_)|apiKey|iamToken|folderId',re.I)

def clean_example(value):
    if isinstance(value,dict):
        return {k:('' if SECRET_KEYS.search(k) or k in {'widget_url','sse_url','webhook_secret','public_base_url'}
                   else clean_example(v)) for k,v in value.items()}
    if isinstance(value,list): return [clean_example(v) for v in value]
    return value

def allowed(relative):
    parts=relative.parts; name=relative.name
    if any(p in {'__pycache__','.git','audio_cache','superpowers'} for p in parts):return False
    folded=tuple(x.casefold() for x in parts)
    if len(parts)>=3 and folded[:2]==('integrations','tts') and folded[2] in portability.CUSTOM_TTS_DIR_NAMES:return False
    if len(parts)>=2 and folded[:2]==('core','data'):return name.casefold().endswith('.example.json')
    if len(parts)==1:return name in ROOT_FILES or (name.endswith('.bat') and not name.startswith('APPLY_PATCH'))
    if parts[0] not in CODE_DIRS:return False
    if name.endswith('.example.json') or (parts[0]=='integrations' and name=='manifest.json'):return True
    if name=='tribute_tunnel.py':return False
    if parts[0]!='docs' and relative.suffix.lower()=='.md' and name not in {'GUIDE.md','README.md','LICENSE.md'}:return False
    if parts[0]=='docs' and name not in {'MANUAL.md','index.html','QUICK_START.md','README.md','docs-theme.css','docs-theme.js'}:return False
    return relative.suffix.lower() in CODE_SUFFIXES

def initialize_clean(root):
    for path in sorted(root.rglob('*.example.json')):
        data=clean_example(json.loads(path.read_text(encoding='utf-8-sig')))
        rel=path.relative_to(root).as_posix()
        if rel.startswith('integrations/') and isinstance(data,dict) and 'enabled' in data:
            data['enabled']=False
        if rel=='integrations/integrations_onboarding.example.json':data={'completed':False,'selected':[]}
        if rel in {'core/data/donations.example.json','core/data/donor_profiles.example.json','core/data/donor_adjustments.example.json'}:data=[]
        raw=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        path.write_bytes(raw)
        path.with_name(path.name.replace('.example.json','.json')).write_bytes(raw)
    data_dir=root/'core/data';data_dir.mkdir(parents=True,exist_ok=True)
    for name in ['donations.json','donor_profiles.json','donor_adjustments.json']:
        (data_dir/name).write_text('[]\n',encoding='utf-8')

def build_public(source:Path,target:Path):
    source=Path(source).resolve();target=Path(target).resolve()
    if target.exists():raise FileExistsError('Папка сборки уже существует; выберите новый каталог')
    if source==target or source.is_relative_to(target):raise ValueError('Неверная папка сборки')
    target.mkdir(parents=True)
    paths=[p for p in source.iterdir() if p.is_file()]
    for name in sorted(CODE_DIRS):
        if (source/name).exists():paths.extend((source/name).rglob('*'))
    for path in sorted(paths):
        relative=path.relative_to(source)
        if target.is_relative_to(source) and path.is_relative_to(target):continue
        if not path.is_file() or not allowed(relative):continue
        if path.is_symlink() or not path.resolve().is_relative_to(source):raise ValueError('Ссылка вне исходной папки запрещена')
        dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    (target/'VERSION').write_text(VERSION+'\n',encoding='utf-8')
    admin=target/'core/public/admin.html'
    if admin.exists():
        text=admin.read_text(encoding='utf-8').replace('v1.4.5.1','v1.4.6').replace('DA Reliability &amp; Admin UX','Reliability &amp; Safe Update')
        admin.write_text(text,encoding='utf-8')
    for rel in ['docs/index.html','docs/MANUAL.md']:
        path=target/rel
        if path.exists():
            text=path.read_text(encoding='utf-8').replace('VicDonationGoal v1.4.5.1','VicDonationGoal v1.4.6').replace('<br>v1.4.5.1','<br>v1.4.6')
            path.write_text(text,encoding='utf-8')
    readme=target/'README.md'
    if readme.exists():
        text=readme.read_text(encoding='utf-8').replace('v1.4.5.1 — DA Reliability & Admin UX','v1.4.6 — Reliability & Safe Update')
        text=text.replace('Эта папка является личной рабочей сборкой и содержит OAuth-токены, widget URL, историю донатов и другие приватные данные. Не публикуйте её целиком. Для GitHub после теста собирается отдельная sanitized beta.',
                          'Публичная сборка содержит чистые настройки. Личные данные появляются только после настройки или переноса. Не публикуйте свою настроенную папку; для распространения используйте исходный публичный архив.')
        readme.write_text(text,encoding='utf-8')
    for path in target.glob('*.bat'):
        text=path.read_text(encoding='utf-8-sig')
        text=re.sub(r'v1\.4\.5\.1(?: - DA Reliability)?','v1.4.6 - Reliability & Safe Update',text)
        path.write_text(text,encoding='utf-8')
    initialize_clean(target)
    return target

def archive_tree(root,archive):
    archive=Path(archive)
    if archive.exists():raise FileExistsError('Архив уже существует')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(Path(root).rglob('*')):
            if path.is_file():z.write(path,Path(root).name+'/'+path.relative_to(root).as_posix())
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    return {'file':archive.name,'sha256':digest,'bytes':archive.stat().st_size}

def private_secrets(source):
    result=set()
    def walk(value,key=''):
        if isinstance(value,dict):
            for k,v in value.items():walk(v,k)
        elif isinstance(value,list):
            for v in value:walk(v,key)
        elif isinstance(value,str) and len(value)>=8 and (SECRET_KEYS.search(key) or key in {'widget_url','sse_url'}):
            if not any(s in value for s in ('PASTE_','ВСТАВЬ','CHANGE_ME')):
                result.add(value.encode('utf-8'))
                if '?' in value:
                    from urllib.parse import parse_qs,urlsplit
                    for k,items in parse_qs(urlsplit(value).query).items():
                        if SECRET_KEYS.search(k):result.update(x.encode() for x in items if len(x)>=8)
    for path in portability.collect_user_files(source):
        if path.suffix=='.json':
            try:walk(json.loads(path.read_text(encoding='utf-8-sig')))
            except (ValueError,UnicodeError):pass
    return result

def audit_public(tree,source):
    tree=Path(tree);secrets=private_secrets(source);bad=[]
    for path in tree.rglob('*'):
        if not path.is_file():continue
        raw=path.read_bytes()
        if any(secret in raw for secret in secrets):bad.append(path.relative_to(tree).as_posix())
    if bad:raise ValueError('Найдены приватные значения в файлах: '+', '.join(bad))
    for name in ['runtime','backups','diagnostics','release','.git','_patch']:
        if (tree/name).exists():raise ValueError('Лишняя папка в публичной сборке: '+name)
    for rel in ['core/data/donations.json','core/data/donor_profiles.json','core/data/donor_adjustments.json']:
        if json.loads((tree/rel).read_text())!=[]:raise ValueError('Публичная сборка содержит историю')
    return {'files':sum(p.is_file() for p in tree.rglob('*')),'privateValuesChecked':len(secrets),'secretMatches':0}

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=ROOT)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    output=args.output.resolve()
    if output.exists():raise FileExistsError('Выберите новый выходной каталог')
    output.mkdir(parents=True)
    # Build/test private candidate first. Public tree is independently generated.
    private=build_public(args.source,output/f'VicDonationGoal_my_v{VERSION}')
    migration=migrate(args.source,private)
    (private/'PRIVATE_BUILD.txt').write_text('ЛИЧНАЯ СБОРКА: содержит историю, настройки и токены. Не публиковать.\n',encoding='utf-8')
    public=build_public(args.source,output/f'VicDonationGoal_v{VERSION}')
    audit=audit_public(public,args.source)
    artifacts=[archive_tree(private,output/f'VicDonationGoal_my_v{VERSION}.zip'),
               archive_tree(public,output/f'VicDonationGoal_v{VERSION}.zip')]
    (output/'BUILD_REPORT.json').write_text(json.dumps({'version':VERSION,'migration':migration,'publicAudit':audit,'artifacts':artifacts},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(''.join(a['sha256']+'  '+a['file']+'\n' for a in artifacts),encoding='utf-8')
    print(json.dumps({'version':VERSION,'publicAudit':audit,'artifacts':artifacts},ensure_ascii=False))

if __name__=='__main__':main()
