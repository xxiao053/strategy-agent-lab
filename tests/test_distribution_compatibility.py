"""Offline contracts for the distribution's TLS/env/chart dependency surfaces."""
import io
import ssl
import certifi
import pytest
from PIL import Image
from dotenv import dotenv_values
from lab.references import reference_chart_png


def test_chart_renders_valid_bounded_png():
    raw=reference_chart_png()
    assert raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw)<1000000
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size==(1080,270)
        image.verify()


def test_environment_parse_is_inert_and_explicit(monkeypatch):
    monkeypatch.delenv('LAB_TEST_KEY',raising=False)
    parsed=dotenv_values(stream=io.StringIO('LAB_TEST_KEY="fixture-key"\nLAB_EXECUTION_BACKEND=docker\n'))
    import os
    assert parsed['LAB_TEST_KEY']=='fixture-key' and 'LAB_TEST_KEY' not in os.environ


def test_tls_trust_loads_without_disabling_hostname_checks():
    context=ssl.create_default_context(cafile=certifi.where())
    assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
    assert context.cert_store_stats()['x509_ca']>20


@pytest.mark.parametrize('proxy_env,no_proxy,host',[
    ('HTTPS_PROXY','','127.0.0.2'),('https_proxy','','127.0.0.2'),
    ('ALL_PROXY','','127.0.0.2'),('HTTPS_PROXY','localhost','localhost'),
    ('HTTPS_PROXY','*','localhost'),
])
def test_sdk_https_environment_route_tls_cleanup_and_zero_retries(tmp_path,monkeypatch,proxy_env,no_proxy,host):
    import asyncio
    import httpx
    import httpcore
    from httpcore._backends.auto import AutoBackend
    import lab.sdk_budget as sdk
    from tests.test_distribution_credentials import connection
    for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_DIR'):
        monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv(proxy_env,'http://127.0.0.2:45678')
    monkeypatch.setenv('NO_PROXY',no_proxy)
    monkeypatch.setenv('SSL_CERT_FILE',certifi.where())
    # The offline guard still permits loopback only; no socket is opened.
    monkeypatch.setattr(sdk,'endpoint',lambda provider:'https://localhost:45679')
    attempts=[];contexts=[];closed=[]
    async def connect(backend,host,port,timeout=None,local_address=None,socket_options=None):
        attempts.append((host,port,timeout))
        raise httpcore.ConnectError('private-proxy-authority')
    create_context=ssl.create_default_context
    def context(*args,**kwargs):
        result=create_context(*args,**kwargs);contexts.append((kwargs,result));return result
    close_transport=httpx.AsyncHTTPTransport.aclose
    async def close(transport):closed.append(transport);await close_transport(transport)
    monkeypatch.setattr(AutoBackend,'connect_tcp',connect)
    monkeypatch.setattr(ssl,'create_default_context',context)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'aclose',close)
    store,c,cfg=connection(tmp_path);p=store.create('P','en')
    async def run():
        async with httpx.AsyncClient(transport=sdk.BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build'),timeout=120) as client:
            with pytest.raises(ValueError):await client.post('https://localhost:45679/responses',json={'input':'hello'})
    asyncio.run(run())
    assert attempts==[(host,45679 if host=='localhost' else 45678,120)]
    assert contexts and all(options.get('cafile')==certifi.where() and value.check_hostname and value.verify_mode==ssl.CERT_REQUIRED for options,value in contexts)
    assert len(closed)==len(contexts) and len({id(transport) for transport in closed})==len(closed)
    record=store.get(p['id'])['records'][0]
    assert record['status']=='unknown' and record['committed_cost']==record['reserved_cost']>0
    assert 'private-proxy-authority' not in record['error']
