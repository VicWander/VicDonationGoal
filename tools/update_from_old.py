"""Copy validated user data into a stopped new installation, without replaying history."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'core'))
import portability

WORKERS=('server.py','tts_hub.py','streamerbot_bridge.py','_listener.py','tribute_tunnel.py')

def process_inventory():
    if os.name!='nt':
        result=[]
        for p in Path('/proc').glob('[0-9]*/cmdline'):
            try: result.append({'ProcessId':int(p.parent.name),'CommandLine':p.read_bytes().replace(b'\0',b' ').decode()})
            except (OSError,ValueError): pass
        return result
    run=subprocess.run(['powershell','-NoProfile','-Command',
        'Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress'],
        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
    if run.returncode or not run.stdout.strip():
        raise RuntimeError('Не удалось проверить запущенные процессы. Остановите обе версии и повторите перенос.')
    rows=json.loads(run.stdout)
    return [rows] if isinstance(rows,dict) else rows

def ensure_stopped(*roots,allow_core=False):
    inventory=process_inventory()
    for root in roots:
        root=Path(root).resolve()
        registered=set()
        registry=root/'runtime/integration_processes.json'
        if registry.exists():
            value=json.loads(registry.read_text(encoding='utf-8-sig'))
            registered.add(value.get('corePid'))
            registered.update(v.get('pid') for v in value.get('processes',{}).values() if isinstance(v,dict))
        for row in inventory:
            if row.get('ProcessId')==os.getpid(): continue
            cmd=str(row.get('CommandLine') or '').lower().replace('\\','/')
            worker=any(marker in cmd for marker in WORKERS)
            if allow_core and 'server.py' in cmd: worker=False
            script_tokens=[x.strip('"') for x in re.findall(r'"[^"]*"|\S+',cmd)
                           if any(marker in x for marker in WORKERS)]
            relative_worker=any(not re.match(r'^(?:[a-z]:/|/)',x) for x in script_tokens)
            if worker and (
                    root.as_posix().lower() in cmd or row.get('ProcessId') in registered or relative_worker):
                raise RuntimeError('Модули ещё работают. Для полного переноса закройте обе версии через 13_STOP_ALL.bat и запустите 16_UPDATE_FROM_OLD_VERSION.bat из новой папки.')

def encode(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')

def prepare_payload(payload,existing=None):
    def canonical(path):
        parts=path.casefold().split('/')
        if len(parts)>3 and parts[:2]==['integrations','tts'] and parts[2] in portability.CUSTOM_TTS_DIR_NAMES:
            return path
        return path.casefold()
    result={canonical(k):v for k,v in payload.items()}
    effective={**{canonical(k):v for k,v in (existing or {}).items()},**result}
    def read(rel,default): return json.loads(effective[rel].decode('utf-8-sig')) if rel in effective else default
    donations=read('core/data/donations.json',[])
    keys=set()
    for row in donations:
        for field in ('uniqueKey','accountingId','id'):
            if row.get(field) not in (None,''): keys.add(str(row[field]))
        ext=row.get('externalId') or row.get('external_id') or row.get('externalID')
        if ext not in (None,''): keys.add(f"{row.get('source','manual')}:{ext}")
    for rel,field in [('integrations/streamerbot/streamerbot_sent.json','sent'),('integrations/tts/tts_sent.json','seen')]:
        value=read(rel,{})
        if not isinstance(value,dict) or not isinstance(value.get(field,[]),list):
            raise ValueError('Некорректный журнал обработанных событий: '+rel)
        value[field]=sorted(set(map(str,value.get(field,[])))|keys)
        if field=='seen': value['initialized']=True
        result[rel]=encode(value)
    rules=read('integrations/streamerbot/donation_event_rules.json',{}).get('rules',[])
    rel='integrations/streamerbot/streamerbot_event_rules_sent.json'
    value=read(rel,{'sent':[]})
    previous=value.get('sent',[])
    if not isinstance(previous,list): raise ValueError('Некорректный журнал донат-ивентов')
    rule_keys={f"{key}::rule::{str(rule.get('id') or rule.get('rule_id') or rule.get('name') or rule.get('action_id') or rule.get('actionId') or 'unnamed_rule').strip()}"
               for key in keys for rule in rules if isinstance(rule,dict)}
    value['sent']=sorted(set(map(str,previous))|rule_keys)
    result[rel]=encode(value)
    # Old pending speech/control is retained in the original folder/snapshot,
    # but must not automatically play when a new installation starts.
    result['integrations/tts/tts_queue.json']=encode([])
    result['integrations/tts/tts_control.json']=encode({'commands':[]})
    return result,len(donations)

def migrate(source:Path,target:Path):
    source=Path(source).resolve(); target=Path(target).resolve()
    if source==target or source.is_relative_to(target):
        raise ValueError('Выберите отдельную папку старой версии; перенос в неё саму запрещён')
    source_version=(source/'VERSION').read_text(encoding='utf-8-sig').strip()
    target_version=(target/'VERSION').read_text(encoding='utf-8-sig').strip()
    def parts(v):
        if not re.fullmatch(r'\d+(?:\.\d+){1,3}',v): raise ValueError('Неизвестный формат версии')
        return tuple(int(x) for x in v.split('.'))
    if parts(source_version)>parts(target_version):
        raise ValueError('Старая папка содержит более новую версию; понижение отменено')
    ensure_stopped(source,target)
    raw,_=portability.create_backup_bytes(source,reason='migration_source')
    _,payload=portability.inspect_backup_bytes(raw,current_version=target_version)
    payload,count=prepare_payload(payload,existing=portability._capture_user_payload(target))
    portability.validate_user_payload(payload)
    backup_dir=target/'backups/migration'; backup_dir.mkdir(parents=True,exist_ok=True)
    source_backup=backup_dir/('source_'+hashlib.sha256(raw).hexdigest()[:16]+'.zip')
    source_backup.write_bytes(raw)
    if portability.collect_user_files(target):
        portability.write_backup(target,reason='before_offline_migration',group='migration')
    portability.apply_payload(target,payload)
    return {'ok':True,'sourceVersion':source_version,'targetVersion':target_version,
            'files':len(payload),'donations':count,'pendingSpeechCarriedOver':False,
            'tributeNeedsObsLink':not bool(json.loads(payload.get('integrations/tribute/tribute_config.json',b'{}')).get('widget_url'))}

def main():
    parser=argparse.ArgumentParser(description='Перенос в новую папку до первого запуска; старые озвучки не повторяются.')
    parser.add_argument('--source',type=Path);parser.add_argument('--target',type=Path,default=ROOT)
    args=parser.parse_args()
    try:
        source=args.source
        if source is None:
            try:
                import tkinter as tk
                from tkinter.filedialog import askdirectory
                window=tk.Tk();window.withdraw()
                selected=askdirectory(title='Выберите папку СТАРОЙ версии VicDonationGoal')
                window.destroy()
                if not selected:return
                source=Path(selected)
            except ImportError:
                source=Path(input('Папка старой версии: ').strip().strip('"'))
        result=migrate(source,args.target)
        print(f"Перенос завершён: {result['donations']} донатов. Старые озвучки и события не повторяются.")
        if result['tributeNeedsObsLink']:print('Если используете Tribute: вставьте ссылку для OBS в его карточке.')
        print('Теперь запустите 01_START_ALL.bat из НОВОЙ папки. Старая папка не изменена.')
    except Exception as error:
        # File content and tokens are deliberately not printed.
        print('Перенос не выполнен: '+str(error));raise SystemExit(1)

if __name__=='__main__':main()
