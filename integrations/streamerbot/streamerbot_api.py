"""HTTP setup and read-only health checks shared by the UI and Bridge."""
from urllib.parse import urlsplit,urlunsplit
import requests

def normalize_config(config):
    result=dict(config)
    url=str(result.get('streamerbot_http_url') or '').strip().rstrip('/')
    parsed=urlsplit(url)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Укажи HTTP-адрес Streamer.bot, например http://127.0.0.1:7474/DoAction')
    # Access .port here too, so invalid ports fail before saving.
    parsed.port
    path=parsed.path.rstrip('/')
    if not path.endswith('/DoAction'):path+='/DoAction'
    result['streamerbot_http_url']=urlunsplit((parsed.scheme,parsed.netloc,path,'',''))
    for key in ('action_name','action_id'):
        result[key]=str(result.get(key) or '').strip()
    return result

def _request(config,method,path,**kwargs):
    url=normalize_config(config)['streamerbot_http_url'].removesuffix('/DoAction')+path
    try:
        with requests.Session() as session:
            session.trust_env=False
            response=session.request(method,url,timeout=(2,4),allow_redirects=False,**kwargs)
        if response.status_code>=300:
            raise ValueError(f'Streamer.bot вернул HTTP {response.status_code}. Проверь HTTP Server и выбранное действие.')
        return response
    except requests.RequestException as error:
        raise ValueError('Нет ответа от Streamer.bot. Запусти его HTTP Server и проверь адрес и порт.') from error

def list_actions(config):
    response=_request(config,'GET','/GetActions')
    try:data=response.json()
    except ValueError as error:raise ValueError('По этому адресу отвечает не HTTP API Streamer.bot: список действий не получен.') from error
    if not isinstance(data,dict) or not isinstance(data.get('actions'),list):
        raise ValueError('Streamer.bot не вернул список действий. Проверь адрес HTTP Server.')
    return [{'id':str(a.get('id') or ''),'name':str(a.get('name') or ''),'enabled':a.get('enabled',True)} for a in data['actions'] if isinstance(a,dict) and a.get('id')]

def check_connection(config):
    config=normalize_config(config);actions=list_actions(config)
    action_id=config['action_id'];name=config['action_name']
    matches=[a for a in actions if a['id']==action_id] if action_id else [a for a in actions if a['name']==name]
    if not matches:raise ValueError('Действие не найдено. Создай его в Streamer.bot или выбери из списка; сохрани настройки.')
    if len(matches)>1:raise ValueError('Найдено несколько действий с этим именем. Выбери нужное действие по ID из списка.')
    if matches[0]['enabled'] is False:raise ValueError('Выбранное действие выключено в Streamer.bot. Включи его перед проверкой.')
    return matches[0]

def execute_action(config,action,args):
    response=_request(config,'POST','/DoAction',json={'action':action,'args':args})
    if response.status_code==204 or not response.content:return
    try:data=response.json()
    except ValueError as error:raise ValueError('Вместо подтверждения Streamer.bot вернул постороннюю страницу.') from error
    if not isinstance(data,dict) or data.get('success') is False or str(data.get('status','')).lower() in {'error','failed'} or data.get('error'):
        raise ValueError('Streamer.bot отклонил запуск действия. Проверь действие и его настройки.')
