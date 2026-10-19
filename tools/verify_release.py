"""Verify extracted archives, plus optional actual old-version datasets offline."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'core')]
from tools.update_from_old import migrate
from tools.build_release import audit_public
import portability

SMOKE=r'''
import sys,json,threading,requests
from pathlib import Path
sys.path[:0]=[str(Path.cwd()/'core'),str(Path.cwd())]
import server
server.ensure_files();server.normalize_storage()
manager=server.get_integration_manager()
# Neither start_enabled nor Washington.start is called in verification.
http=server.VicThreadingHTTPServer(('127.0.0.1',0),server.Handler)
thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
session=requests.Session();session.trust_env=False
url='http://127.0.0.1:'+str(http.server_port)
for path in ['/api/health','/admin.html','/api/integrations','/widget.html','/tts.html']:
    response=session.get(url+path,timeout=5)
    assert response.status_code==200,(path,response.status_code)
history=session.get(url+'/api/donations',timeout=5).json()
assert isinstance(history,list)
http.shutdown();http.server_close()
print('SMOKE_RESULT '+json.dumps({'httpChecks':5,'donations':len(history),'version':server.APP_VERSION}))
'''

def smoke(tree):
    run=subprocess.run([sys.executable,'-B','-c',SMOKE],cwd=tree,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40)
    if run.returncode:raise RuntimeError('Проверка HTTP не прошла: '+run.stderr[-900:])
    line=next(x for x in run.stdout.splitlines() if x.startswith('SMOKE_RESULT '))
    return json.loads(line.split(' ',1)[1])

def verify(candidate_dir,old144=None,old1451=None):
    candidate_dir=Path(candidate_dir)
    report={'artifacts':[],'upgrades':[]}
    for name in ['VicDonationGoal_my_v1.4.6','VicDonationGoal_v1.4.6']:
        with tempfile.TemporaryDirectory(prefix='vic_release_verify_') as tmp:
            with zipfile.ZipFile(candidate_dir/(name+'.zip')) as z:z.extractall(tmp)
            tree=Path(tmp)/name
            run=subprocess.run([sys.executable,'-B',str(tree/'tools/beta_readiness_check.py')],cwd=tree,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300)
            readiness=json.loads((tree/'BETA_READINESS_REPORT_v1.4.6.json').read_text(encoding='utf-8'))
            if run.returncode:raise RuntimeError('Beta Readiness: '+json.dumps(readiness['ERR'],ensure_ascii=False))
            result={'name':name,'ok':readiness['ok'],'warnings':readiness['warnings'],'errors':readiness['errors'],'smoke':smoke(tree)}
            report['artifacts'].append(result)
            print(json.dumps(result,ensure_ascii=False),flush=True)
    for label,source in [('public-1.4.4',old144),('private-1.4.5.1',old1451)]:
        if source is None:continue
        source=Path(source)
        before={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in portability.collect_user_files(source)}
        with tempfile.TemporaryDirectory(prefix='vic_actual_upgrade_') as tmp:
            with zipfile.ZipFile(candidate_dir/'VicDonationGoal_v1.4.6.zip') as z:z.extractall(tmp)
            tree=Path(tmp)/'VicDonationGoal_v1.4.6'
            first=migrate(source,tree);migrate(source,tree)
            for rel,digest in before.items():
                if rel.endswith(('tts_sent.json','streamerbot_sent.json','streamerbot_event_rules_sent.json','tts_queue.json','tts_control.json')):continue
                assert hashlib.sha256((tree/rel).read_bytes()).hexdigest()==digest,'Не совпал перенесённый файл: '+rel
            result={'source':label,'donations':first['donations'],'files':first['files'],'repeatMigration':'passed','smoke':smoke(tree)}
            assert result['smoke']['donations']==first['donations']
            report['upgrades'].append(result)
            print(json.dumps(result,ensure_ascii=False),flush=True)
        assert all(hashlib.sha256((source/rel).read_bytes()).hexdigest()==digest for rel,digest in before.items()),'Исходная папка изменилась'
    (candidate_dir/'VERIFICATION_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate-dir',type=Path,required=True)
    p.add_argument('--old-144',type=Path);p.add_argument('--old-1451',type=Path)
    args=p.parse_args();verify(args.candidate_dir,args.old_144,args.old_1451)

if __name__=='__main__':main()
