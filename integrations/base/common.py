from __future__ import annotations

import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

from safe_json import load_json as _robust_load_json, save_json as _robust_save_json

try:
    import requests
except ImportError:
    requests = None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, fallback):
    return _robust_load_json(path, fallback, retries=12)


def save_json(path: Path, data):
    _robust_save_json(path, data, retries=80)


def deep_get(data, *paths, default=None):
    for path in paths:
        current = data
        ok = True
        for key in str(path).split('.'):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                ok = False
                break
        if ok and current not in (None, ""):
            return current
    return default


def to_number(value, default=0.0):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or '').strip().replace('\u00a0','').replace(' ','').replace(',','.')
    text = re.sub(r'[^0-9.\-]', '', text)
    try: return float(text)
    except Exception: return default


def parse_jsonish(value):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, bytes):
        value = value.decode('utf-8', errors='replace')
    text = str(value or '').strip()
    if not text: return None
    candidates = [text]
    # Socket.IO/WebSocket packets often start with 42, 0, etc.
    for marker in ('{','['):
        pos = text.find(marker)
        if pos > 0:
            candidates.append(text[pos:])
    for candidate in candidates:
        try: return json.loads(candidate)
        except Exception: pass
    return None


def iter_nodes(data, max_depth=10):
    stack=[(data,0)]
    seen=set()
    while stack:
        node, depth=stack.pop()
        if depth>max_depth: continue
        if isinstance(node,(dict,list)):
            marker=id(node)
            if marker in seen: continue
            seen.add(marker)
        yield node
        if isinstance(node,dict):
            for value in node.values():
                if isinstance(value,(dict,list)): stack.append((value,depth+1))
        elif isinstance(node,list):
            for value in node:
                if isinstance(value,(dict,list)): stack.append((value,depth+1))


def normalize_time(value):
    if isinstance(value, dict):
        value = value.get('date') or value.get('created_at') or value.get('createdAt')
    if isinstance(value, (int,float)):
        stamp=float(value)
        if stamp>10_000_000_000: stamp/=1000
        try: return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
        except Exception: pass
    text=str(value or '').strip()
    return text or now_iso()


def donation_from_candidate(candidate, source, default_currency='RUB', note=''):
    if not isinstance(candidate, dict):
        return None

    nested_vars = candidate.get('vars') if isinstance(candidate.get('vars'), dict) else {}
    nested_notification = candidate.get('notification') if isinstance(candidate.get('notification'), dict) else {}
    notification_vars = nested_notification.get('vars') if isinstance(nested_notification.get('vars'), dict) else {}

    amount = deep_get(
        candidate,
        'amount', 'sum', 'value', 'total',
        'donation.amount', 'payment.amount', 'data.amount',
        'vars.amount', 'vars.sum',
        'notification.amount', 'notification.vars.amount', 'notification.vars.sum',
    )
    if amount in (None, ''):
        amount = nested_vars.get('amount') or nested_vars.get('sum') or notification_vars.get('amount') or notification_vars.get('sum')
    if amount in (None, ''):
        return None

    amount_num = to_number(amount, 0)
    if amount_num <= 0:
        return None

    event_type = str(deep_get(candidate, 'type', 'event', 'eventType', 'kind', default='')).lower()
    status = str(deep_get(candidate, 'status', 'payment.status', 'data.status', default='')).lower()
    if event_type and any(x in event_type for x in ('cashout', 'withdraw', 'payout', 'refund')):
        return None
    if status and status in {'cancel', 'canceled', 'cancelled', 'failed', 'error', 'wait', 'pending'}:
        return None

    external_id = deep_get(
        candidate,
        'id', 'uuid', 'transaction_id', 'transactionId', 'donation_id', 'donationId',
        'payment_id', 'paymentId', 'event_id', 'eventId', 'message_uid', 'messageUid',
        'payment_uuid', 'donate_id', 'donateId',
        'vars.id', 'vars.notification_id', 'notification.id', 'notification.vars.id',
    )
    if external_id in (None, ''):
        external_id = nested_vars.get('id') or nested_vars.get('notification_id') or notification_vars.get('id') or notification_vars.get('notification_id')
    if external_id in (None, ''):
        # A stable ID is required for duplicate protection.
        return None

    username = deep_get(
        candidate,
        'username', 'user_name', 'userName', 'name', 'nickname', 'nick', 'from',
        'sender.name', 'user.name', 'author.name', 'donation.username',
        'vars.name', 'vars.username', 'notification.vars.name', 'notification.vars.username',
        default=None,
    )
    if not username:
        username = nested_vars.get('name') or nested_vars.get('username') or notification_vars.get('name') or notification_vars.get('username') or 'Аноним'

    message = deep_get(
        candidate,
        'message', 'comment', 'text', 'donation.message', 'payment.comment', 'description',
        'vars.comment', 'vars.message', 'notification.vars.comment', 'notification.vars.message',
        default=None,
    )
    if message in (None, ''):
        message = nested_vars.get('comment') or nested_vars.get('message') or notification_vars.get('comment') or notification_vars.get('message') or ''

    currency = str(deep_get(
        candidate,
        'currency', 'currency_code', 'currencyCode', 'donation.currency', 'payment.currency',
        'vars.currency', 'notification.vars.currency',
        default=default_currency,
    ) or default_currency).upper()

    created = deep_get(
        candidate,
        'createdAt', 'created_at', 'date', 'time', 'timestamp', 'paidAt', 'paid_at',
        'payment.created_at', 'vars.created_at', 'notification.vars.created_at',
        default=None,
    )

    return {
        'source': source,
        'externalId': str(external_id),
        'username': str(username or 'Аноним'),
        'amount': amount_num,
        'currency': currency,
        'message': str(message or ''),
        'createdAt': normalize_time(created),
        'note': note,
    }


def extract_donations(payload, source, default_currency='RUB', note=''):
    data=parse_jsonish(payload)
    if data is None: return []
    result=[]; keys=set()
    for node in iter_nodes(data):
        item=donation_from_candidate(node, source, default_currency, note)
        if item and item['externalId'] not in keys:
            keys.add(item['externalId']); result.append(item)
    return result


def post_donation(api_url, donation, timeout=12, attempts=3):
    if requests is None: raise RuntimeError('Не установлена библиотека requests')
    last=None
    for attempt in range(1,attempts+1):
        try:
            response=requests.post(api_url,json=donation,timeout=timeout)
            try: payload=response.json()
            except Exception: payload={}
            if response.ok and payload.get('ok',True): return payload
            raise RuntimeError(payload.get('message') or f'Core HTTP {response.status_code}')
        except Exception as error:
            last=error
            if attempt<attempts: time.sleep(attempt)
    raise RuntimeError(f'Не удалось передать событие в Core: {last}')


def redact_url(url):
    text=str(url or '')
    return re.sub(r'(?i)(token|jwt|key|secret|access_token)=([^&]+)', r'\1=***', text)


class StatusWriter:
    def __init__(self, path: Path, service: str, **extra):
        self.path=Path(path); self.data={'service':service,'running':False,'connected':False,'status':'stopped','lastError':None,'lastEvent':None,'updatedAt':time.time(),**extra}; self.write()
    def update(self, **values):
        self.data.update(values); self.data['updatedAt']=time.time(); self.write()
    def write(self):
        try: save_json(self.path,self.data)
        except Exception: pass
