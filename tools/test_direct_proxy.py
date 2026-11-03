import socket,threading,unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.base.direct_proxy import DirectBrowserProxy
class ProxyTests(unittest.TestCase):
 def test_rejects_private_destination(self):
  with DirectBrowserProxy() as proxy:
   host,port=proxy['server'].split('//')[1].split(':')
   with socket.create_connection((host,int(port)),timeout=2) as client:
    client.sendall(b'CONNECT 127.0.0.1:443 HTTP/1.1\r\nHost: 127.0.0.1:443\r\n\r\n')
    self.assertIn(b'403',client.recv(4096))
 def test_disabled_uses_browser_defaults(self):
  with DirectBrowserProxy(enabled=False) as proxy:self.assertIsNone(proxy)
 def test_tunnel_passes_bytes_both_directions(self):
  echo=socket.socket();echo.bind(('127.0.0.1',0));echo.listen();port=echo.getsockname()[1]
  def serve():
   peer,_=echo.accept()
   with peer:peer.sendall(peer.recv(4096))
  worker=threading.Thread(target=serve,daemon=True);worker.start()
  original=socket.create_connection
  def connect(address,*a,**k):return original(('127.0.0.1',port) if address[0]=='8.8.8.8' else address,*a,**k)
  with DirectBrowserProxy() as proxy,patch('integrations.base.direct_proxy.resolve_public',return_value='8.8.8.8'),patch('integrations.base.direct_proxy.socket.create_connection',side_effect=connect):
   host,p=proxy['server'].split('//')[1].split(':')
   with original((host,int(p)),timeout=3) as client:
    client.sendall(b'CONNECT fixture.example:443 HTTP/1.1\r\nHost: fixture.example:443\r\n\r\n')
    self.assertIn(b'200',client.recv(4096));client.sendall(b'fixture-test');self.assertEqual(client.recv(4096),b'fixture-test')
  echo.close();worker.join(2)
if __name__=='__main__':unittest.main()
