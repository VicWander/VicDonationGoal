from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.tribute import tribute_listener as tr
sys.path.insert(0, str(ROOT / 'core'))
from integration_manager import IntegrationManager

URL = 'https://obs.tribute.tg/obs/alerts?token=private-test-token&apiHost=proxy.tribute.tg&apiProtocol=https'

def event(id='payment-1', amount=99900, currency='RUB'):
    return {'id': 'stream-'+id, 'data': {'type': 'donation', 'donation_id': id,
        'author': 123, 'display_name': 'Anonymous', 'amount': amount, 'currency': currency, 'message': 'hello'}}

class TributeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.listener = tr.Listener(self.root, {'widget_url': URL})

    def test_widget_url_only_sends_token_to_tribute(self):
        self.assertEqual(tr.stream_url(URL), 'https://proxy.tribute.tg/api/v1/obs/alerts/stream?token=private-test-token')
        for url in [URL.replace('proxy.tribute.tg','evil.example'), URL.replace('https://obs.', 'https://evil.'),
                    URL.replace('apiProtocol=https','apiProtocol=http'), URL+'&token=second',
                    URL.replace('proxy.tribute.tg','proxy.tribute.tg@evil.example')]:
            with self.subTest(url=url), self.assertRaises(ValueError): tr.stream_url(url)

    def test_minor_units_and_stable_payment_id(self):
        for currency, raw, expected in [('RUB',99900,999),('USD',1234,12.34),('EUR',5678,56.78),('JPY',999,999),('KWD',12345,12.345),('CLF',12345,1.2345)]:
            donation=tr.parse_donation(event(amount=raw,currency=currency))
            self.assertEqual(donation['amount'],expected)
            self.assertEqual(donation['externalId'],'payment-1')
            self.assertEqual(donation['username'],'Anonymous')

    def test_currency_reaches_history_and_goal_conversion_unchanged(self):
        from tools.test_file_safety import server
        rates={'ratesToRUB':{'RUB':1,'USD':90,'EUR':100}}
        with patch.object(server,'load_rates',return_value=rates):
            for currency in ('RUB','USD','EUR'):
                donation=tr.parse_donation(event(amount=1234,currency=currency))
                row=server.normalize_donation_record(donation,{'currency':'RUB'})
                self.assertEqual(row['amount'],12.34)
                self.assertEqual(row['currency'],currency)
                self.assertEqual(row['amountForGoal'],round(12.34*rates['ratesToRUB'][currency],2))
            row=server.normalize_donation_record(tr.parse_donation(event(amount=1234,currency='USD')),{'currency':'EUR'})
            self.assertEqual(row['amountForGoal'],11.11)

    def test_bad_events_never_create_donations(self):
        for raw in [0,-100,float('nan'),float('inf'),True,'bad',1.5]:
            with self.subTest(raw=raw), self.assertRaises(ValueError): tr.parse_donation(event(amount=raw))
        self.assertIsNone(tr.parse_donation({'data':{'type':'subscription'}}))
        raw=event(); raw['data'].pop('donation_id'); raw.pop('id')
        with self.assertRaises(ValueError): tr.parse_donation(raw)

    def test_sse_named_multiline_event_and_ping(self):
        lines=[': ping','','id: cursor','event: donation','data: {"id":"x",','data: "data":{"type":"donation"}}','']
        frames=list(tr.iter_sse(lines))
        self.assertEqual(frames[0], {'event':'heartbeat','id':'','data':''})
        self.assertEqual(json.loads(frames[1]['data'])['id'],'x')
        self.assertEqual(frames[1]['id'],'cursor')

    def test_diagnostic_event_is_never_replayed_into_goal(self):
        tr.save_json(self.listener.control_file, {'testUntil':tr.time.time()+60, 'requestId':'test-1'})
        with patch.object(self.listener,'send') as send:
            self.listener.accept(event())
            tr.save_json(self.listener.control_file, {})
            restarted=tr.Listener(self.root, {'widget_url':URL})
            with patch.object(restarted,'send') as later:
                restarted.accept(event())
                later.assert_not_called()
            send.assert_not_called()
        status=tr.load_json(self.listener.status_file,{})
        self.assertEqual(status['lastTest']['amount'],999)

    def test_delivery_failure_is_persisted_and_retried_after_restart(self):
        with patch.object(self.listener,'send',side_effect=ConnectionError('Core unavailable')):
            self.listener.accept(event())
        restarted=tr.Listener(self.root,{'widget_url':URL})
        with patch.object(restarted,'send',return_value=True) as send:
            restarted.flush_pending()
            self.assertEqual(send.call_count,1)
        self.assertEqual(tr.load_json(restarted.state_file,{})['pending'],{})

    def test_duplicate_success_is_not_sent_twice(self):
        with patch.object(self.listener,'send',return_value=True) as send:
            self.listener.accept(event()); self.listener.accept(event())
            self.assertEqual(send.call_count,1)

    def test_no_test_window_after_expiry(self):
        tr.save_json(self.listener.control_file, {'testUntil':tr.time.time()-1})
        with patch.object(self.listener,'send',return_value=True) as send:
            self.listener.accept(event())
            self.assertEqual(send.call_count,1)

    def test_switch_can_count_diagnostic_donations(self):
        self.listener.config['count_during_test']=True
        tr.save_json(self.listener.control_file, {'testUntil':tr.time.time()+60})
        with patch.object(self.listener,'send',return_value=True) as send:
            self.listener.accept(event())
            self.assertEqual(send.call_count,1)
        self.assertTrue(tr.load_json(self.listener.status_file,{})['lastTest']['counted'])

    def test_real_anonymous_999_is_counted_with_test_switch_off(self):
        self.listener.config['count_during_test']=False
        with patch.object(self.listener,'send',return_value=True) as send:
            self.listener.accept(event())
            self.assertEqual(send.call_count,1)

    def test_stopping_clears_running_status(self):
        self.listener.update(status='stopped', running=False, connected=False)
        self.assertFalse(tr.load_json(self.listener.status_file,{})['running'])

    def test_secret_is_removed_from_error(self):
        text=self.listener.safe_error(RuntimeError('failed '+URL+' private-test-token'))
        self.assertNotIn('private-test-token',text)

    def test_manager_starts_and_cancels_explicit_test_window(self):
        manager=object.__new__(IntegrationManager)
        manager.runtime_dir=self.root/'runtime/integrations'
        manager._manifest=Mock(return_value={})
        manager._adapters={}
        manager._load_config=Mock(return_value={'widget_url':URL})
        manager._configured=Mock(return_value=True)
        manager.start=Mock(return_value={'ok':True})
        result=manager.test('tribute')
        self.assertGreater(result['testUntil'],tr.time.time())
        control=manager.runtime_dir/'tribute_control.json'
        self.assertGreater(tr.load_json(control,{})['testUntil'],tr.time.time())
        manager.test('tribute',cancel=True)
        self.assertEqual(tr.load_json(control,{}),{})

    def test_dead_worker_cannot_remain_connected(self):
        manager=object.__new__(IntegrationManager)
        manager.runtime_dir=self.root/'runtime/integrations'
        manager._manifest=Mock(return_value={'kind':'subprocess'})
        manager._adapters={}
        manager._read_status_file=Mock(return_value={'running':True,'connected':True,'status':'connected'})
        manager._process=Mock(return_value=None)
        status=manager.integration_status('tribute')
        self.assertFalse(status['connected'])
        self.assertFalse(status['running'])

    def test_obs_mode_does_not_accept_the_old_webhook_too(self):
        from tools.test_file_safety import server
        handler=object.__new__(server.Handler)
        handler.path='/api/integrations/tribute/webhook/old-secret'
        handler.read_body_json=Mock(return_value={'name':'new_donation'})
        handler.headers={}
        handler.send_json=Mock()
        manager=Mock()
        manager._load_config.return_value={'widget_url':URL}
        with patch.object(server,'PROJECT_ROOT',self.root), patch.object(server,'get_integration_manager',return_value=manager), patch.object(server,'add_donation') as add:
            handler.do_POST()
        self.assertEqual(handler.send_json.call_args.args[1],410)
        add.assert_not_called()

if __name__=='__main__': unittest.main(verbosity=2)
