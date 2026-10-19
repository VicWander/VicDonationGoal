"""Optional best-effort donation reactions. Never runs network work on ingestion."""
import copy
import json
import math
import queue
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from safe_json import load_json, save_json
from source_registry import AUTOMATIC_SOURCE_IDS

DEFAULTS = {
    'enabled': False, 'url': 'http://127.0.0.1:5000',
    'sources': list(AUTOMATIC_SOURCE_IDS),
    'manual': False, 'minimumAmount': 10, 'chance': 70,
    'cooldownSeconds': 60, 'largeAmount': 500, 'largeChance': 100,
    'afterAlertWaitSeconds': 30, 'delaySeconds': 3,
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def validate_config(data):
    if not isinstance(data, dict):
        raise ValueError('Настройки должны быть объектом')
    c = {**DEFAULTS, **data}
    for key in ('enabled', 'manual'):
        if not isinstance(c[key], bool):
            raise ValueError(f'{key}: нужно логическое значение')
    u = urlparse(str(c['url']))
    if (u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1')
            or u.username or u.password or u.query or u.fragment or u.path not in ('', '/')):
        raise ValueError('Укажите локальный HTTP-адрес Washington без пути и пароля')
    try:
        _ = u.port
    except ValueError:
        raise ValueError('Некорректный порт')
    c['url'] = c['url'].rstrip('/')
    for key, maximum in [('minimumAmount', 1e9), ('chance', 100), ('largeAmount', 1e9),
                         ('largeChance', 100), ('cooldownSeconds', 3600),
                         ('afterAlertWaitSeconds', 120), ('delaySeconds', 60)]:
        value = c[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
            raise ValueError(f'Некорректное значение {key}')
    if not isinstance(c['sources'], list) or not all(isinstance(s, str) and len(s) <= 50 for s in c['sources']):
        raise ValueError('Некорректный список источников')
    c['sources'] = sorted(set(s.strip().lower() for s in c['sources'] if s.strip()))
    return c


class WashingtonIntegration:
    def __init__(self, root, log=print):
        self.root = root
        self.file = root / 'integrations/washington/config.json'
        self.log = log
        self.queue = queue.Queue(maxsize=32)
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.last_attempt = 0
        self.state = {'state': 'disabled', 'lastEvent': '', 'lastError': ''}
        self.thread = None

    def config(self):
        return validate_config(load_json(self.file, {}))

    def save_config(self, data):
        with self.lock:
            c = validate_config({**self.config(), **data})
            save_json(self.file, c)
            return c

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True, name='Washington reactions')
            self.thread.start()

    def status(self):
        with self.lock:
            return {**self.state, 'state': self.state['state'] if self.config()['enabled'] else 'disabled',
                    'queueLength': self.queue.qsize()}

    def _record(self, event, error=''):
        with self.lock:
            self.state.update(lastEvent=event, lastError=error)
            if error:
                self.state['state'] = 'offline'
        self.log('[Washington] ' + event + (': ' + error if error else ''))

    def submit(self, donation, base_currency, test=False):
        """No disk/network access: ingestion only copies a bounded in-memory job."""
        try:
            self.queue.put_nowait((copy.deepcopy(donation), base_currency, test, time.monotonic()))
            return True
        except queue.Full:
            self._record('queue_full')
            return False

    def test(self, currency='RUB'):
        return self.submit({'uniqueKey': 'test:' + uuid.uuid4().hex, 'source': 'test',
                            'username': 'TestUser', 'amount': 100, 'currency': currency,
                            'amountForGoal': 100, 'message': 'Ваш, тебе тоже что-нибудь купят?',
                            'receivedAt': datetime.now(timezone.utc).isoformat()}, currency, True)

    def _http(self, path, body=None):
        c = self.config()
        req = Request(c['url'] + path, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
        with build_opener(NoRedirect).open(req, timeout=2) as r:
            return json.loads(r.read(32768))

    def check(self):
        try:
            result = self._http('/wash/events/donation/status')
            if result.get('service') != 'WashingtonService' or result.get('protocolVersion') != 1:
                raise ValueError('incompatible_service')
            with self.lock:
                ready = result.get('enabled') and result.get('senderConfigured')
                self.state.update(state='connected' if ready else 'not_ready', lastError='', washington=result)
        except Exception as ex:
            self._record('connection_check_failed', type(ex).__name__)
        return self.status()

    def _process(self, d, currency, test, queued_at):
        c = self.config()
        if not test and not c['enabled']:
            return
        if time.monotonic() - queued_at > 120:
            self._record('skipped_stale'); return
        source = str(d.get('source', 'manual')).lower()
        amount = float(d.get('amountForGoal', d['amount']))
        if not math.isfinite(amount):
            return
        if not test:
            if (source == 'manual' and not c['manual']) or (source != 'manual' and source not in c['sources']):
                self._record('skipped_source'); return
            if amount < c['minimumAmount']:
                self._record('skipped_minimum'); return
            if time.monotonic() - self.last_attempt < c['cooldownSeconds']:
                self._record('skipped_cooldown'); return
            chance = c['largeChance'] if c['largeAmount'] > 0 and amount >= c['largeAmount'] else c['chance']
            if random.random() * 100 >= chance:
                self._record('skipped_probability'); return
            if d.get('notifyStreamerBot') and c['afterAlertWaitSeconds'] > 0:
                deadline = time.monotonic() + c['afterAlertWaitSeconds']
                while not self.stop.is_set():
                    sent = load_json(self.root / 'integrations/streamerbot/streamerbot_sent.json', {'sent': []})
                    if d['uniqueKey'] in (sent if isinstance(sent, list) else sent.get('sent', [])):
                        break
                    if time.monotonic() >= deadline:
                        self._record('skipped_alert_not_dispatched'); return
                    self.stop.wait(.25)
            if self.stop.wait(c['delaySeconds']):
                return
            if not self.config()['enabled']:
                return
            self.last_attempt = time.monotonic()
        anonymous = bool(d.get('anonymous')) or str(d.get('username', '')).strip().lower() in ('', 'аноним', 'anonymous')
        body = {'eventId': d['uniqueKey'], 'source': source,
                'donorName': 'Аноним' if anonymous else str(d.get('username', 'зритель'))[:80],
                'amount': d['amount'], 'currency': d['currency'], 'normalizedAmount': amount,
                'normalizedCurrency': currency, 'message': str(d.get('message', ''))[:2000],
                'timestamp': d.get('receivedAt') or datetime.now(timezone.utc).isoformat(),
                'anonymous': anonymous, 'isTest': test,
                'largeDonation': c['largeAmount'] > 0 and amount >= c['largeAmount']}
        self._record('request_started')
        result = self._http('/wash/events/donation', body)
        with self.lock:
            self.state.update(state='connected', lastError='')
        self._record('washington_' + str(result.get('status', 'accepted')))

    def _run(self):
        while not self.stop.is_set():
            try:
                job = self.queue.get(timeout=.5)
            except queue.Empty:
                continue
            try:
                self._process(*job)
            except Exception as ex:
                # Never print request bodies, donor text, URL credentials or provider errors.
                self._record('request_failed', type(ex).__name__)
            finally:
                self.queue.task_done()
