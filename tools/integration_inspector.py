from __future__ import annotations
import json,re,time,sys
from datetime import datetime
from pathlib import Path
try: from playwright.sync_api import sync_playwright
except ImportError: raise SystemExit('Playwright не установлен. Запусти 00_INSTALL_ALL.bat')
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'integration_inspector_reports'; OUT.mkdir(exist_ok=True)
def redact(text):
 text=str(text or '')
 text=re.sub(r'(?i)(token|jwt|key|secret|access_token)([=:\" ]+)([^&\s\"}]+)',r'\1\2***',text)
 text=re.sub(r'(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s\"}]+',r'\1***',text)
 return text[:200000]
def main():
 url=input('Вставь URL виджета/страницы интеграции: ').strip()
 if not url: return
 seconds=int(input('Сколько секунд записывать после открытия [60]: ') or '60')
 stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); out=OUT/f'inspector_{stamp}.jsonl'; events=[]
 def record(kind,data,extra=None):
  row={'time':time.time(),'kind':kind,'data':redact(data)}
  if extra: row.update(extra)
  events.append(row); out.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in events)+'\n',encoding='utf-8')
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=False); context=browser.new_context(ignore_https_errors=True); page=context.new_page()
  page.on('request',lambda r:record('request',r.url,{'method':r.method,'resourceType':r.resource_type}))
  page.on('response',lambda r:record('response',r.url,{'status':r.status}))
  page.on('console',lambda m:record('console',m.text))
  def on_ws(ws):
   record('websocket-open',ws.url); ws.on('framesent',lambda d:record('websocket-sent',d,{'url':redact(ws.url)})); ws.on('framereceived',lambda d:record('websocket-received',d,{'url':redact(ws.url)}))
  page.on('websocket',on_ws)
  try: page.goto(url,wait_until='domcontentloaded',timeout=60000)
  except Exception as e: record('goto-error',str(e))
  print(f'Запись идёт {seconds} сек. Сейчас нажми тестовый донат в сервисе.')
  for _ in range(seconds): page.wait_for_timeout(1000)
  browser.close()
 print(f'Отчёт сохранён: {out}')
if __name__=='__main__': main()
