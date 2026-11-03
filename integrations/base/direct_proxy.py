"""Ephemeral loopback CONNECT relay: Chromium uses Python's direct network path.
TLS stays end-to-end between Chromium and the service; no certificates are changed.
"""
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress
import select
import socket
import threading
import time

def resolve_public(host):
    addresses=socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)
    public=[item[4][0] for item in addresses if ipaddress.ip_address(item[4][0]).is_global]
    if not public:raise ValueError('Only public destinations are allowed')
    return next((ip for ip in public if ':' not in ip),public[0])

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_CONNECT(self):
        remote=None
        try:
            host,port=self.path.rsplit(':',1);port=int(port)
            if port!=443:raise ValueError('Only HTTPS is allowed')
            address=resolve_public(host.strip('[]'))
        except (ValueError,OSError):
            self.send_error(403);return
        try:
            remote=socket.create_connection((address,port),timeout=15)
            self.send_response(200,'Connection Established');self.end_headers()
            remote.settimeout(20);self.connection.settimeout(20)
            last=time.monotonic()
            while not self.server.stopping.is_set():
                ready,_,_=select.select([self.connection,remote],[],[],1)
                if not ready:
                    if time.monotonic()-last>180:return
                    continue
                for source in ready:
                    data=source.recv(65536)
                    if not data:return
                    (remote if source is self.connection else self.connection).sendall(data)
                    last=time.monotonic()
        except (OSError,ValueError):
            pass
        finally:
            if remote:remote.close()
            self.close_connection=True

class Server(ThreadingHTTPServer):
    daemon_threads=True
    block_on_close=False

class DirectBrowserProxy(AbstractContextManager):
    def __init__(self,enabled=True):self.enabled=enabled;self.server=None
    def __enter__(self):
        if not self.enabled:return None
        self.server=Server(('127.0.0.1',0),Handler);self.server.stopping=threading.Event()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        return {'server':'http://127.0.0.1:'+str(self.server.server_port)}
    def __exit__(self,*args):
        if self.server:
            self.server.stopping.set();self.server.shutdown();self.server.server_close();self.thread.join(2)
