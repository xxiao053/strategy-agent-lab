"""Core tests are self-contained; historical integrations use optional local data."""
from pathlib import Path
import pytest
import ipaddress
import socket
import importlib
from urllib.parse import urlparse
from urllib.request import OpenerDirector


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """All tests are offline: permit loopback relay fixtures, never remote DNS/connect."""
    def allowed(host):
        if host is None:return True
        if isinstance(host,bytes):host=host.decode('ascii','ignore')
        if str(host).lower() in {'localhost','localhost.'}:return True
        try:return ipaddress.ip_address(host).is_loopback
        except ValueError:return False
    def check(host):
        if not allowed(host):raise RuntimeError('Offline test guard blocked external network. Use a mock transport.')
    lookup=socket.getaddrinfo;connect=socket.socket.connect;connect_ex=socket.socket.connect_ex
    def guarded_lookup(host,*args,**kwargs):
        check(host);return lookup(host,*args,**kwargs)
    def guarded_connect(connection,address):
        if connection.family in {socket.AF_INET,socket.AF_INET6}:check(address[0])
        return connect(connection,address)
    def guarded_connect_ex(connection,address):
        if connection.family in {socket.AF_INET,socket.AF_INET6}:check(address[0])
        return connect_ex(connection,address)
    monkeypatch.setattr(socket,'getaddrinfo',guarded_lookup)
    monkeypatch.setattr(socket.socket,'connect',guarded_connect)
    monkeypatch.setattr(socket.socket,'connect_ex',guarded_connect_ex)
    sendto=socket.socket.sendto
    def guarded_sendto(connection,*args):
        if connection.family in {socket.AF_INET,socket.AF_INET6}:check(args[-1][0])
        return sendto(connection,*args)
    monkeypatch.setattr(socket.socket,'sendto',guarded_sendto)
    for name in ['gethostbyname','gethostbyname_ex']:
        original=getattr(socket,name)
        def guarded_name(host,_lookup=original):check(host);return _lookup(host)
        monkeypatch.setattr(socket,name,guarded_name)

    # Check destination URL before a real transport can forward through a local proxy.
    # MockTransport/ASGITransport remain usable; product transports are not modified.
    for name in ['httpx','httpx2']:
        try:module=importlib.import_module(name)
        except ImportError:continue
        original=module.HTTPTransport.handle_request
        def guarded_request(transport,request,_handler=original):
            check(request.url.host);return _handler(transport,request)
        monkeypatch.setattr(module.HTTPTransport,'handle_request',guarded_request)
        original_async=module.AsyncHTTPTransport.handle_async_request
        async def guarded_async_request(transport,request,_handler=original_async):
            check(request.url.host);return await _handler(transport,request)
        monkeypatch.setattr(module.AsyncHTTPTransport,'handle_async_request',guarded_async_request)
    original_open=OpenerDirector.open
    def guarded_open(opener,url,*args,**kwargs):
        parsed=urlparse(url.full_url if hasattr(url,'full_url') else url)
        if parsed.scheme in {'http','https'}:check(parsed.hostname)
        return original_open(opener,url,*args,**kwargs)
    monkeypatch.setattr(OpenerDirector,'open',guarded_open)


def pytest_addoption(parser):
    parser.addoption('--without-market-data', action='store_true',
                     help='Run the self-contained suite without private historical fixtures')


def pytest_collection_modifyitems(config, items):
    root = Path(__file__).resolve().parents[1]/'artifacts'
    available = all(any(root.rglob(f'{s}.yahoo.json')) for s in ('AAPL','AMZN','MSFT','QQQ','SPY'))
    if available and not config.getoption('--without-market-data'):
        return
    missing = pytest.mark.skip(reason='Optional frozen market data not available; see docs/en/development.md')
    for item in items:
        if item.get_closest_marker('market_data'):
            item.add_marker(missing)
