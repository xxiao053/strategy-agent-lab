import socket
import pytest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading
import importlib


def test_external_network_guard_blocks_before_dns_or_connect(request):
    # Missing fixture must fail before any attempt to use the network.
    request.getfixturevalue('block_external_network')
    with pytest.raises(RuntimeError,match='Offline test guard'):
        socket.getaddrinfo('api.openai.com',443)
    with socket.socket() as connection:
        with pytest.raises(RuntimeError,match='Offline test guard'):
            connection.connect(('203.0.113.1',443))
        with pytest.raises(RuntimeError,match='Offline test guard'):
            connection.connect_ex(('203.0.113.1',443))


@pytest.mark.parametrize('client_module',['httpx','httpx2','urllib'])
def test_destination_guard_blocks_external_url_even_through_local_proxy(client_module,monkeypatch):
    received=[]
    class ProxyFixture(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            received.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(b'local fixture only')
    server=ThreadingHTTPServer(('127.0.0.1',0),ProxyFixture)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    proxy=f'http://127.0.0.1:{server.server_port}'
    monkeypatch.setenv('HTTP_PROXY',proxy);monkeypatch.setenv('HTTPS_PROXY',proxy);monkeypatch.setenv('NO_PROXY','')
    try:
        with pytest.raises(RuntimeError,match='Offline test guard'):
            if client_module=='urllib':
                from urllib.request import build_opener,ProxyHandler
                build_opener(ProxyHandler({'http':proxy})).open('http://external.invalid/probe',timeout=2)
            else:
                module=importlib.import_module(client_module)
                with module.Client(proxy=proxy,timeout=2) as client:client.get('http://external.invalid/probe')
        assert received==[], 'External destination never reaches even the local fake proxy.'
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
