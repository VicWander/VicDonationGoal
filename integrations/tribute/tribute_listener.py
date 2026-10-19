"""Direct Tribute OBS SSE client; no browser or incoming public server required."""
from __future__ import annotations

import json
import random
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import requests
from integrations.base.common import load_json, save_json, now_iso, redact_url

ZERO_DECIMALS = set('BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF XOF XPF'.split())
THREE_DECIMALS = set('BHD IQD JOD KWD LYD OMR TND'.split())


def stream_url(widget_url):
    parsed = urlsplit(str(widget_url or '').strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (parsed.scheme != 'https' or parsed.netloc != 'obs.tribute.tg'
            or parsed.path.rstrip('/') != '/obs/alerts' or parsed.fragment):
        raise ValueError('Нужна ссылка «Копировать ссылку для OBS» из Tribute')
    token = query.get('token', [])
    host = query.get('apiHost', ['proxy.tribute.tg'])
    protocol = query.get('apiProtocol', ['https'])
    if (len(token) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]{8,512}', token[0])
            or host != ['proxy.tribute.tg'] or protocol != ['https']):
        raise ValueError('Некорректная OBS-ссылка: проверьте токен, apiHost и HTTPS')
    return 'https://proxy.tribute.tg/api/v1/obs/alerts/stream?' + urlencode({'token': token[0]})


def parse_donation(payload):
    data = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(data, dict) or data.get('type') != 'donation':
        return None
    payment_id = data.get('donation_id') or payload.get('id')
    if not isinstance(payment_id, (str, int)) or isinstance(payment_id, bool) or not str(payment_id).strip():
        raise ValueError('В событии Tribute нет ID платежа')
    currency = str(data.get('currency') or '').upper()
    if not re.fullmatch('[A-Z]{3}', currency):
        raise ValueError('Некорректная валюта Tribute')
    try:
        raw = data.get('amount')
        amount = Decimal(str(raw))
        if isinstance(raw, bool) or not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value():
            raise ValueError('Некорректная сумма Tribute')
        digits = 0 if currency in ZERO_DECIMALS else 3 if currency in THREE_DECIMALS else 4 if currency in {'CLF', 'UYW'} else 2
        value = float(amount / (10 ** digits))
        if value > 1e15 or value <= 0:
            raise ValueError('Сумма Tribute вне допустимого диапазона')
    except (InvalidOperation, OverflowError, TypeError) as error:
        raise ValueError('Некорректная сумма Tribute') from error
    return {'source': 'tribute', 'externalId': str(payment_id),
            'username': str(data.get('display_name') or 'Аноним'), 'amount': value,
            'currency': currency, 'message': str(data.get('message') or ''),
            'createdAt': str(data.get('created_at') or now_iso()), 'note': 'Tribute OBS'}


def iter_sse(lines):
    frame = {'event': 'message', 'id': '', 'data': ''}
    data = []
    size = 0
    for raw in lines:
        line = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
        if line is None:
            continue
        if line == '':
            if data:
                frame['data'] = '\n'.join(data)
                yield frame
            frame = {'event': 'message', 'id': '', 'data': ''}
            data = []
            size = 0
        elif line.startswith(':'):
            yield {'event': 'heartbeat', 'id': '', 'data': ''}
        else:
            key, _, value = line.partition(':')
            value = value[1:] if value.startswith(' ') else value
            size += len(line)
            if size > 1024 * 1024:
                raise ValueError('Слишком большое событие Tribute')
            if key == 'data': data.append(value)
            elif key in {'event', 'id'} and '\x00' not in value: frame[key] = value


class Listener:
    def __init__(self, root, config):
        self.root = Path(root)
        self.config = config
        self.url = stream_url(config.get('widget_url'))
        self.token = parse_qs(urlsplit(self.url).query)['token'][0]
        self.state_file = self.root / 'integrations/tribute/stream_state.json'
        self.status_file = self.root / 'runtime/integrations/tribute_status.json'
        self.control_file = self.root / 'runtime/integrations/tribute_control.json'
        self.state = load_json(self.state_file, {'pending': {}, 'ignoredIds': [], 'deliveredIds': [], 'lastEventId': ''})
        for key, default in [('pending', {}), ('ignoredIds', []), ('deliveredIds', []), ('lastEventId', '')]:
            self.state.setdefault(key, default)
        self.status = load_json(self.status_file, {})
        self.retry_at = 0

    def update(self, **values):
        self.status.update({'service':'tribute', 'mode':'obs_sse', 'running':True, 'updatedAt':time.time(), **values})
        save_json(self.status_file, self.status)

    def safe_error(self, error):
        return redact_url(str(error).replace(self.config.get('widget_url', ''), 'OBS-ссылка').replace(self.token, '***'))[:700]

    def persist(self):
        save_json(self.state_file, self.state)

    def send(self, donation):
        # A local Core request must bypass the browser/VPN HTTP proxy.
        with requests.Session() as session:
            session.trust_env = False
            response = session.post('http://127.0.0.1:3333/api/donation', json=donation, timeout=8)
            result = response.json()
            if response.ok and result.get('ok'):
                return True
            if response.status_code == 400 and 'уже' in str(result.get('message', '')).lower():
                return True
            raise RuntimeError(f"Core HTTP {response.status_code}: {str(result.get('message', 'ошибка доставки'))[:200]}")

    def flush_pending(self):
        if time.time() < self.retry_at:
            return
        for key, donation in list(self.state['pending'].items()):
            try:
                if not self.send(donation):
                    raise ConnectionError('Core не подтвердил сохранение')
                self.state['pending'].pop(key)
                self.state['deliveredIds'] = (self.state['deliveredIds'] + [key])[-5000:]
                self.persist()
                self.update(lastEvent=f"{donation['username']} — {donation['amount']} {donation['currency']}",
                            lastError=None, pendingCount=len(self.state['pending']))
                print('[Tribute] Донат сохранён в Core', flush=True)
            except Exception as error:
                self.retry_at = time.time() + 5
                self.update(lastError='Донат в очереди: ' + self.safe_error(error), pendingCount=len(self.state['pending']))
                break

    def accept(self, payload):
        donation = parse_donation(payload)
        if donation is None: return
        key = donation['externalId']
        if key in self.state['ignoredIds'] or key in self.state['deliveredIds']:
            return
        control = load_json(self.control_file, {})
        testing = float(control.get('testUntil') or 0) > time.time()
        if testing:
            current_config = load_json(self.root / 'integrations/tribute/tribute_config.json', self.config)
            preview = {k: donation[k] for k in ('username', 'amount', 'currency', 'message')}
            preview.update(receivedAt=now_iso(), requestId=control.get('requestId'),
                           counted=bool(current_config.get('count_during_test', False)))
            if not preview['counted']:
                self.state['ignoredIds'] = (self.state['ignoredIds'] + [key])[-5000:]
                self.persist()
                self.update(lastTest=preview)
                print('[Tribute] Проверочное событие получено; в цель не добавлено', flush=True)
                return
            self.update(lastTest=preview)
        if key not in self.state['pending']:
            self.state['pending'][key] = donation
            self.persist()
        self.flush_pending()

    def listen(self):
        self.update(status='connecting_sse', connected=False, lastError=None)
        headers = {'Accept': 'text/event-stream', 'Origin': 'https://obs.tribute.tg', 'Cache-Control': 'no-cache'}
        if self.state['lastEventId']:
            headers['Last-Event-ID'] = self.state['lastEventId']
        with requests.Session() as session:
            session.trust_env = bool(self.config.get('use_system_proxy', True))
            with session.get(self.url, headers=headers, stream=True, timeout=(15, 45), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ConnectionError(f'Tribute HTTP {response.status_code}; проверьте OBS-ссылку и сеть')
                if response.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'text/event-stream':
                    raise ConnectionError('Tribute ответил без потока SSE')
                response.encoding = 'utf-8'
                first_frame = True
                for frame in iter_sse(response.iter_lines(chunk_size=1, decode_unicode=True)):
                    if first_frame:
                        self.status['connectedSince'] = time.time()
                        self.status['nextRetryAt'] = None
                        first_frame = False
                    self.update(status='connected', connected=True, lastHeartbeatAt=now_iso())
                    self.flush_pending()
                    if frame['event'] == 'donation':
                        try:
                            self.accept(json.loads(frame['data']))
                        except (ValueError, TypeError, KeyError) as error:
                            self.update(lastWarning='Событие отклонено: ' + self.safe_error(error))
                            continue
                    if frame['id']:
                        self.state['lastEventId'] = frame['id']
                        self.persist()
        raise ConnectionError('Tribute закрыл поток; переподключаюсь')


def main():
    config = load_json(ROOT / 'integrations/tribute/tribute_config.json', {})
    if not config.get('enabled'):
        return
    listener = Listener(ROOT, config)
    delay = 2
    print('[Tribute] Подключаюсь по OBS-ссылке напрямую', flush=True)
    try:
        while True:
            try:
                listener.flush_pending()
                listener.listen()
            except Exception as error:
                message = listener.safe_error(error)
                listener.update(status='reconnecting', connected=False, lastError=message, nextRetryAt=time.time()+delay)
                print('[Tribute] ' + message, flush=True)
                # Successful traffic resets the backoff after a long session.
                if time.time() - listener.status.get('connectedSince', time.time()) > 60:
                    delay = 2
                time.sleep(delay + random.uniform(0, 0.5))
                delay = min(30, delay * 2)
    except KeyboardInterrupt:
        listener.update(status='stopped', running=False, connected=False)


if __name__ == '__main__':
    main()
