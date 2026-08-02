from __future__ import annotations

import importlib.util
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "integrations" / "tts"))

from source_registry import AUTOMATIC_SOURCE_IDS, SOURCE_REGISTRY
from safe_json import load_json, save_json

OK=[]; WARN=[]; ERR=[]
def ok(x): OK.append(x); print('[ OK ]',x)
def warn(x): WARN.append(x); print('[WARN]',x)
def err(x): ERR.append(x); print('[ERR ]',x)

print('='*68)
print(' VicDonationGoal v1.4.4 — Beta Readiness Check')
print('='*68)

# 1. Existing stability check.
try:
    r=subprocess.run([sys.executable,str(ROOT/'tools/stability_check.py')],cwd=ROOT,capture_output=True,text=True,timeout=240)
    if r.returncode==0: ok('Stability Check завершён без критических ошибок')
    else: err('Stability Check завершился с ошибкой')
    (ROOT/'BETA_READINESS_STABILITY_OUTPUT.txt').write_text((r.stdout or '')+(('\nSTDERR:\n'+r.stderr) if r.stderr else ''),encoding='utf-8')
except Exception as e: err(f'Stability Check не запустился: {type(e).__name__}: {e}')

# 2. Registry and manifests are synchronized.
manifest_ids=set()
for path in sorted((ROOT/'integrations').glob('*/manifest.json')):
    try:
        d=json.loads(path.read_text(encoding='utf-8')); mid=str(d.get('id') or '')
        manifest_ids.add(mid)
        if mid not in SOURCE_REGISTRY: err(f'{mid}: отсутствует в source_registry.py')
        else:
            if not d.get('stability'): err(f'{mid}: manifest не содержит stability')
            else: ok(f'{mid}: registry/manifest синхронизированы ({d.get("stability")})')
    except Exception as e: err(f'{path}: {e}')
missing=set(AUTOMATIC_SOURCE_IDS)-manifest_ids
if missing: err('Нет manifests для: '+', '.join(sorted(missing)))
else: ok('Для всех автоматических источников есть manifests')

# 3. Import/runtime smoke tests — catches NameError like _robust_load_json.
modules=[
 'core/server.py','core/integration_manager.py','core/donor_store.py','core/tts_hub_store.py',
 'integrations/streamerbot/streamerbot_bridge.py','integrations/tts/tts_hub.py',
 'integrations/donatty/donatty_listener.py','integrations/streamelements/streamelements_listener.py',
 'integrations/donatepay/donatepay_listener.py','integrations/donatestream/donatestream_listener.py',
 'integrations/donatex/donatex_listener.py','integrations/tribute/tribute_tunnel.py',
 'integrations/donationalerts/donationalerts_integration.py','integrations/streamlabs/streamlabs_integration.py',
 'tools/create_diagnostic_report.py','tools/stop_all.py','tools/install_cloudflared.py'
]
for rel in modules:
    path=ROOT/rel
    try:
        py_compile.compile(str(path),doraise=True)
        code=(
            'import importlib.util,sys; from pathlib import Path; '
            f'root=Path({str(ROOT)!r}); sys.path[:0]=[str(root),str(root/"core"),str(root/"integrations"/"tts")]; '
            f'p=Path({str(path)!r}); s=importlib.util.spec_from_file_location("beta_smoke_{path.stem}",p); '
            'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); print("ok")'
        )
        rr=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True,timeout=35)
        if rr.returncode==0: ok('Runtime import: '+rel)
        else: err('Runtime import '+rel+': '+(rr.stderr or rr.stdout)[-700:])
    except Exception as e: err(f'Runtime import {rel}: {type(e).__name__}: {e}')

# 4. All automatic sources pass Streamer.bot and TTS source gates.
try:
    from integrations.streamerbot import streamerbot_bridge as sb
    config=dict(sb.DEFAULT_CONFIG); config['send_sources']=[]
    for source in AUTOMATIC_SOURCE_IDS:
        donation={'source':source,'notifyStreamerBot':True,'username':'Beta Test','amount':100,'currency':'RUB','message':'test'}
        if not sb.should_send(donation,config): err(f'Streamer.bot rejects source {source}')
    if not any(x.startswith('Streamer.bot rejects') for x in ERR): ok('Streamer.bot принимает все источники реестра')
except Exception as e: err(f'Streamer.bot source gate: {type(e).__name__}: {e}')

try:
    import tts_hub
    config={'donations':{'enabled':True,'sources':list(AUTOMATIC_SOURCE_IDS)+['manual'],'amountField':'amountForGoal','minAmount':0,'currency':'RUB'}}
    for source in AUTOMATIC_SOURCE_IDS:
        allowed,reason=tts_hub.donation_allowed({'eventType':'donation','source':source,'amountForGoal':100,'currency':'RUB'},config)
        if not allowed: err(f'TTS rejects source {source}: {reason}')
    if not any(x.startswith('TTS rejects') for x in ERR): ok('TTS принимает все источники реестра')
except Exception as e: err(f'TTS source gate: {type(e).__name__}: {e}')

# 5. safe_json concurrency and file release.
try:
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'stress.json'
        failures=[]
        def worker(index):
            try:
                for n in range(30):
                    save_json(path,{'worker':index,'n':n},retries=80)
                    data=load_json(path,{},retries=20)
                    if not isinstance(data,dict): raise RuntimeError('not dict')
            except Exception as e: failures.append(e)
        threads=[threading.Thread(target=worker,args=(i,)) for i in range(5)]
        [x.start() for x in threads]; [x.join() for x in threads]
        if failures: raise failures[0]
        renamed=path.with_name('renamed.json'); os.replace(path,renamed); renamed.unlink()
    ok('Конкурентная JSON-запись и освобождение файла работают')
except Exception as e: err(f'safe_json stress: {type(e).__name__}: {e}')

# 6. Dashboard API can be built offline.
try:
    import server
    status=server.build_system_status()
    ids={x.get('id') for x in status.get('systemModules',[])}
    expected={'core','integration-manager','streamerbot','tts'}
    if ids!=expected: err(f'System dashboard modules: {ids}, ожидалось {expected}')
    else: ok('System dashboard содержит Core, Integration Manager, Bridge и TTS')
    returned={x.get('id') for x in status.get('sourceRegistry',[])}
    if set(SOURCE_REGISTRY)-returned: err('API status не возвращает полный source registry')
    else: ok('API status возвращает полный source registry')
except Exception as e: err(f'Dashboard status build: {type(e).__name__}: {e}')

# 7. Optional heavy component must not be bundled.
if (ROOT/'tools/cloudflared.exe').exists(): warn('cloudflared.exe включён в сборку и увеличивает размер примерно на 52 МБ')
else: ok('cloudflared не встроен; Tribute установит его только по запросу')

# 8. Diagnostic report generation.
try:
    from tools.create_diagnostic_report import create_report, collect_secret_values
    import zipfile
    archive=create_report(ROOT)
    if archive.exists() and archive.stat().st_size>0:
        ok('Безопасный диагностический ZIP создаётся')
        with tempfile.TemporaryDirectory() as temp:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(temp)
            blob = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in Path(temp).rglob("*") if path.is_file())
        leaked = [value for value in collect_secret_values() if value and value in blob]
        if leaked:
            err(f'Диагностический ZIP содержит {len(leaked)} секретных значений')
        else:
            ok('Диагностический ZIP не содержит локальные секреты')
    else:
        err('Диагностический ZIP не создан')
except Exception as e: err(f'Diagnostic report: {type(e).__name__}: {e}')

# 9. Required beta UI and docs markers.
for rel,markers in {
 'core/public/admin.html':['systemStatusGrid','serviceStatusGrid','createDiagnosticButton'],
 'core/public/admin.js':['sourceRegistryCache','createDiagnosticReport','pluralRu'],
 'source_registry.py':['AUTOMATIC_SOURCE_IDS','SOURCE_REGISTRY'],
 '14_CREATE_DIAGNOSTIC_REPORT.bat':['create_diagnostic_report.py'],
 'README.md':['Closed Beta','t.me/wander_streams','CHANGELOG.md'],
 'index.html':['Closed Beta','TopDonation','VicWander'],
}.items():
    text=(ROOT/rel).read_text(encoding='utf-8',errors='replace') if (ROOT/rel).exists() else ''
    missing=[m for m in markers if m not in text]
    if missing: err(f'{rel}: отсутствуют markers {missing}')
    else: ok(f'Beta marker check: {rel}')

summary={'version':(ROOT/'VERSION').read_text(encoding='utf-8').strip(),'ok':len(OK),'warnings':len(WARN),'errors':len(ERR),'OK':OK,'WARN':WARN,'ERR':ERR}
report_dir=ROOT/'diagnostics'
report_dir.mkdir(parents=True,exist_ok=True)
(report_dir/'BETA_READINESS_REPORT_v1.4.4.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
md=['# VicDonationGoal v1.4.4 — Beta Readiness Report','',f'- OK: **{len(OK)}**',f'- WARN: **{len(WARN)}**',f'- ERR: **{len(ERR)}**','']
if WARN: md += ['## Предупреждения','']+[f'- {x}' for x in WARN]+['']
if ERR: md += ['## Ошибки','']+[f'- {x}' for x in ERR]+['']
(report_dir/'BETA_READINESS_REPORT_v1.4.4.md').write_text('\n'.join(md),encoding='utf-8')
print('\n'+'-'*68); print(f'OK: {len(OK)} | WARN: {len(WARN)} | ERR: {len(ERR)}')
raise SystemExit(1 if ERR else 0)
