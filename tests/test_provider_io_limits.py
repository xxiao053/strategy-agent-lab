"""Bound actual streamed transports, including bodies without line delimiters."""
import json
import asyncio
import time
import tracemalloc
import httpx
import pytest
from lab.contracts import RunConfig
from lab.providers import Adapter,ProviderError


class Chunks(httpx.SyncByteStream):
    def __init__(self,chunk,count,delay=0):self.chunk,self.count,self.delay=chunk,count,delay;self.reads=0;self.closed=False
    def __iter__(self):
        for _ in range(self.count):
            if self.delay:time.sleep(self.delay)
            self.reads+=1
            yield self.chunk
    def close(self):self.closed=True


@pytest.mark.parametrize('target',['catalog','market'])
def test_metadata_transports_reject_compression_before_any_decode(target,monkeypatch):
    import gzip
    from lab.connections import Connections
    from scripts.freeze_market import _transport
    stream=Chunks(gzip.compress(b' '*8_000_000),1)
    original=httpx.Client
    def handle(request):return httpx.Response(200,stream=stream,headers={'Content-Encoding':'gzip'})
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(**kw,transport=httpx.MockTransport(handle)))
    with pytest.raises(ValueError):
        if target=='catalog':Connections._catalog('openai','offline-only-key')
        else:_transport('https://query1.finance.yahoo.com/v8/finance/chart/SPY')
    assert stream.reads==0 and stream.closed


@pytest.mark.parametrize('target',['catalog','market'])
def test_metadata_transports_bound_trickled_response_elapsed_time(target,monkeypatch):
    from lab.connections import Connections
    from scripts.freeze_market import _transport
    clock=[0.0]
    class Trickled(httpx.SyncByteStream):
        closed=False
        def __iter__(self):
            clock[0]=31.0
            yield b'{"data":[]}'
        def close(self):self.closed=True
    stream=Trickled();original=httpx.Client
    monkeypatch.setattr(time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(**kw,transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=stream))))
    with pytest.raises(ValueError):
        if target=='catalog':Connections._catalog('openai','offline-only-key')
        else:_transport('https://query1.finance.yahoo.com/v8/finance/chart/SPY')
    assert stream.closed


def test_catalog_tiny_chunks_do_not_amplify_memory(monkeypatch):
    from lab.connections import Connections
    stream=Chunks(b' ',262144);original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(**kw,transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=stream))))
    tracemalloc.start()
    try:
        with pytest.raises(ValueError):Connections._catalog('openai','offline-only-key')
        _,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    assert peak<8*1024*1024


def test_tiny_http_chunks_do_not_amplify_memory_beyond_the_body_budget():
    stream=Chunks(b' ',262144)
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=stream))) as client:
        tracemalloc.start()
        try:
            with pytest.raises(ProviderError):
                Adapter('openai',client).send(RunConfig(),{'system':'','text':'','image':''},[],'private-test-key')
            _,peak=tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
    assert peak<8*1024*1024


@pytest.mark.parametrize('parts',[[b'data: first\r\rdata: second\r\r'],[b'data: first\n\ndata: second\n\n'],
    [b'data: first\r',b'\n\r',b'\ndata: second\r',b'\n\r',b'\n']])
def test_bounded_sse_preserves_legal_event_delimiters_across_chunks(parts):
    from lab.provider_io import lines
    class Sequence(httpx.SyncByteStream):
        def __iter__(self):yield from parts
    response=httpx.Response(200,stream=Sequence())
    assert list(lines(response,limit=1000,line_limit=100,deadline=time.monotonic()+5))==['data: first','','data: second','']


@pytest.mark.parametrize('kind',['size','deadline','encoding'])
def test_adapter_stops_unbounded_responses_without_retry_or_raw_success(kind,monkeypatch):
    from lab import providers
    monkeypatch.setattr(providers,'MAX_RESPONSE_BYTES',512,raising=False)
    monkeypatch.setattr(providers,'MAX_RESPONSE_SECONDS',.04 if kind=='deadline' else 5,raising=False)
    stream=Chunks(b' '*200,8,.02 if kind=='deadline' else 0);hits=[];saved=[]
    def handle(request):
        hits.append(1)
        return httpx.Response(200,stream=stream,headers={'Content-Encoding':'gzip'} if kind=='encoding' else {})
    adapter=Adapter('openai',httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ProviderError) as error:
        adapter.send(RunConfig(),{'system':'','text':'','image':''},[],'private-test-key',save_raw=lambda *x:saved.append(x))
    assert error.value.ambiguous and len(hits)==1 and not saved
    assert stream.reads<8 and stream.closed


@pytest.mark.parametrize('kind',['size','line','deadline'])
def test_native_relay_limits_stream_and_retains_unknown_reservation(kind,tmp_path,monkeypatch):
    from lab import build_runtime
    from tests.test_builder_runtime import setup_project
    store,connections,pid,cfg=setup_project(tmp_path)
    monkeypatch.setattr(build_runtime,'MAX_STREAM_BYTES',512 if kind=='size' else 4096,raising=False)
    monkeypatch.setattr(build_runtime,'MAX_STREAM_LINE_BYTES',512 if kind=='line' else 4096,raising=False)
    monkeypatch.setattr(build_runtime,'MAX_STREAM_SECONDS',.04 if kind=='deadline' else 5,raising=False)
    stream=Chunks(b'x'*200+(b'\n' if kind!='line' else b''),8,.02 if kind=='deadline' else 0);hits=[]
    def handle(request):hits.append(1);return httpx.Response(200,stream=stream)
    with build_runtime.BudgetRelay(store,pid,cfg,'private-test-key',10,'fixture',transport=httpx.MockTransport(handle)) as relay:
        with httpx.Client(trust_env=False,timeout=3) as client:
            headers={'Authorization':'Bearer '+relay.token}
            client.post(relay.url+'/responses',headers=headers,json={'input':[]})
            blocked=client.post(relay.url+'/responses',headers=headers,json={'input':[]})
            assert blocked.status_code==409
    assert stream.reads<8 and stream.closed and len(hits)==1
    record=store.get(pid)['records'][0]
    assert record['status']=='unknown' and record['committed_cost']==record['reserved_cost']>0
    assert sum(p.stat().st_size for p in (tmp_path/'workspace-receipts').glob('*'))<=4096


@pytest.mark.parametrize('kind',['deadline','encoding'])
def test_sdk_receive_boundary_stops_trickles_and_compression(kind,tmp_path,monkeypatch):
    import gzip
    from lab import sdk_budget
    from tests.test_distribution_credentials import connection
    store,connections,cfg=connection(tmp_path);project=store.create('Fixture','en');hits=[]
    monkeypatch.setattr(sdk_budget,'MAX_RESPONSE_SECONDS',.04,raising=False)
    class AsyncChunks(httpx.AsyncByteStream):
        reads=0;closed=False
        async def __aiter__(self):
            if kind=='encoding':
                self.reads+=1
                yield gzip.compress(json.dumps({'id':'fixture','output':[],'usage':{'input_tokens':1,'output_tokens':1}}).encode())
            else:
                for _ in range(8):
                    await asyncio.sleep(.02);self.reads+=1;yield b' '
        async def aclose(self):self.closed=True
    stream=AsyncChunks()
    def handle(request):hits.append(1);return httpx.Response(200,stream=stream,headers={'Content-Encoding':'gzip'} if kind=='encoding' else {})
    async def run():
        transport=sdk_budget.BudgetTransport(store,connections,project['id'],cfg,'private-test-key',10,'fixture',transport=httpx.MockTransport(handle))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ValueError):await client.post('https://api.openai.com/v1/responses',json={'input':'fixture'})
            with pytest.raises(ValueError):await client.post('https://api.openai.com/v1/responses',json={'input':'fixture'})
    asyncio.run(run())
    assert stream.closed and stream.reads<(1 if kind=='encoding' else 8) and len(hits)==1
    record=store.get(project['id'])['records'][0]
    assert record['status']=='unknown' and record['committed_cost']==record['reserved_cost']>0
