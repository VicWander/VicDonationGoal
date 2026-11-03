import importlib.util
import sys
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch,MagicMock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
class Status:
 def __init__(self,*a,**k):self.data=k
 def update(self,**k):self.data.update(k)
def load(name):
 spec=importlib.util.spec_from_file_location('reliability_'+name,ROOT/'integrations'/name/(name+'_listener.py'))
 module=importlib.util.module_from_spec(spec)
 with patch('integrations.base.common.StatusWriter',Status):spec.loader.exec_module(module)
 return module
class ReliabilityTests(TestCase):
 def test_reply_keeps_publication_and_checks_id(self):
  m=load('donatepay');ws=MagicMock();ws.recv.side_effect=['{}','{"result":{"data":{"id":9}}}\n{"id":2,"result":{}}'];pending=[]
  self.assertEqual(m.receive_reply(ws,2,'subscribe',pending),{'id':2,'result':{}})
  self.assertEqual(len(pending),1);ws.send.assert_called_once_with('{}')
 def test_ping_updates_status_without_donation(self):
  m=load('donatepay');ws=MagicMock();ws.recv_data.return_value=(m.websocket.ABNF.OPCODE_PING,b'heartbeat')
  self.assertIsNone(m.socket_message(ws,[]));self.assertIn('lastHeartbeatAt',m.STATUS.data)
  ws.recv_data.assert_called_once_with(control_frame=True)
 def test_close_is_not_treated_as_heartbeat(self):
  m=load('donatepay');ws=MagicMock();ws.recv_data.return_value=(m.websocket.ABNF.OPCODE_CLOSE,b'')
  with self.assertRaises(RuntimeError):m.socket_message(ws,[])
 def test_pending_publication_is_preserved(self):
  m=load('donatepay');ws=MagicMock();pending=['fixture']
  self.assertEqual(m.socket_message(ws,pending),'fixture');ws.recv_data.assert_not_called()
 def test_region_controls_all_endpoints(self):
  m=load('donatepay')
  with patch.object(m,'load_json',return_value={'eu_region':True}):
   cfg=m.config();self.assertEqual(cfg['api_v1_url'],'https://donatepay.eu/api/v1');self.assertIn('centrifugo.donatepay.eu',cfg['websocket_url'])
  with patch.object(m,'load_json',return_value={'eu_region':False}):self.assertEqual(m.config()['api_v1_url'],'https://donatepay.ru/api/v1')
 def test_region_change_revalidates_old_user_id(self):
  m=load('donatepay');cfg={'api_key':'fixture-key','api_v1_url':'https://donatepay.eu/api/v1','user_id':'old-ru-id'}
  with patch.object(m,'_load_runtime_state',return_value={'userId':'old-ru-id','credentialScope':'old-scope'}),patch.object(m,'api_get',return_value={'data':{'id':'eu-id'}}) as api,patch.object(m,'_save_runtime_state') as save,patch.object(m,'save_json'),patch.object(m,'load_json',return_value={}),patch.object(m,'log'):
   self.assertEqual(m.resolve_user_id(cfg),'eu-id');api.assert_called_once();self.assertEqual(save.call_args.kwargs['userId'],'eu-id')
 def test_invalid_api_key_is_explicit(self):
  m=load('donatepay')
  with patch.object(m,'api_post_json',return_value={'status':'error','message':'Incorrect token'}):
   with self.assertRaises(m.DonatePayAuthError):m.get_connection_token({'socket_token_url':'https://fixture.example/token','api_key':'fixture'})
 def test_reply_rejects_failure(self):
  m=load('donatepay');ws=MagicMock();ws.recv.return_value='{"id":2,"error":{"code":103}}'
  with self.assertRaises(RuntimeError):m.receive_reply(ws,2,'subscribe',[])
 def test_socketio_requires_confirmation(self):
  m=load('donatestream')
  for raw in ['','2','3probe','0{"sid":"test"}']:self.assertEqual(m.socketio_state(raw),'waiting')
  for raw in ['40{"sid":"test"}',b'40','42["alert",{}]','2\x1e40{}']:self.assertEqual(m.socketio_state(raw),'connected')
  self.assertEqual(m.socketio_state('44{"message":"denied"}'),'disconnected')
 def test_polling_batch_keeps_donation(self):
  m=load('donatestream');raw='2\x1e42["alert",{"message_uid":"fixture-1","sum":12,"nickname":"Fixture"}]'
  donations=m.donations_from_event(raw,'RUB')
  self.assertEqual(len(donations),1);self.assertEqual(donations[0]['externalId'],'fixture-1')
 def test_donatex_failure_does_not_stay_connected(self):
  m=load('donatex');now=[100]
  def poll(cfg):
   if now[0]==100:now[0]=101;return [],'https://donatex.gg/api/v1/donations'
   now[0]=300;raise TimeoutError('timeout')
  with patch.object(m,'config',return_value={}),patch.object(m,'load_seen',return_value=(True,set())),patch.object(m,'poll',side_effect=poll),patch.object(m.time,'time',side_effect=lambda:now[0]),patch.object(m.time,'sleep',side_effect=[None,KeyboardInterrupt]),patch.object(m,'log'):
   with self.assertRaises(KeyboardInterrupt):m.api_loop({})
  self.assertFalse(m.STATUS.data['connected']);self.assertEqual(m.STATUS.data['status'],'retrying')
if __name__=='__main__':main()
