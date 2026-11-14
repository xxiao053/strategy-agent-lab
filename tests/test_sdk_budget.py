import asyncio
import json
import httpx
import pytest
from tests.test_distribution_credentials import connection


def test_transport_reserves_and_persists_before_return(tmp_path):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en')
    store.mutate(p['id'],lambda p:p.update(busy=True))
    def provider(request):
        records=store.get(p['id'])['records'];assert len(records)==1 and records[0]['status']=='running'
        body=json.loads(request.content);assert body['store'] is False and body['max_output_tokens']==6000
        return httpx.Response(200,json={'id':'response','usage':{'input_tokens':10,'output_tokens':20},'output':[]})
    async def run():
        transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=httpx.MockTransport(provider))
        async with httpx.AsyncClient(transport=transport) as client:
            response=await client.post('https://api.openai.com/v1/responses',json={'model':'wrong','input':'hello'})
            assert response.status_code==200
        record=store.get(p['id'])['records'][0]
        assert record['status']=='completed' and (tmp_path/'workspace-receipts'/f"{record['id']}.json").exists()
        assert record['usage_cost']==pytest.approx(.00005)
        assert record['committed_cost']==pytest.approx(.00005)
        assert record['billed_cost'] is None and record['reservation_multiplier']==1.5
    asyncio.run(run())


def test_unknown_outcome_remains_reserved_and_blocks_followup(tmp_path):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en');calls=[]
    def provider(request):calls.append(request);raise httpx.ReadTimeout('fixture')
    async def run():
        transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=httpx.MockTransport(provider))
        async with httpx.AsyncClient(transport=transport) as client:
            for _ in range(2):
                with pytest.raises(ValueError):await client.post('https://api.openai.com/v1/responses',json={'input':'hello'})
    asyncio.run(run());assert len(calls)==1
    r=store.get(p['id'])['records'][0];assert r['status']=='unknown' and r['committed_cost']==r['reserved_cost']>0


@pytest.fixture
def local_http_routes(monkeypatch):
    """Origin and non-forwarding proxy use loopback only, with no inherited proxy."""
    import threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy'):
        monkeypatch.delenv(name,raising=False)
    servers=[];threads=[];calls=[]
    for route in ('origin','proxy'):
        def handler_for(label):
            class Handler(BaseHTTPRequestHandler):
                def do_POST(self):
                    body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                    calls.append((label,self.path,json.loads(body)))
                    raw=json.dumps({'id':label,'usage':{'input_tokens':1,'output_tokens':1},'output':[]}).encode()
                    self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                def log_message(self,*args):pass
            return Handler
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(route))
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
        server.daemon_threads=True;thread.start();servers.append(server);threads.append(thread)
    urls=[f'http://127.0.0.1:{server.server_port}' for server in servers]
    monkeypatch.setenv('HTTP_PROXY',urls[1])
    try:yield urls[0],urls[1],calls
    finally:
        for server in servers:server.shutdown();server.server_close()
        for thread in threads:thread.join(2);assert not thread.is_alive()


def test_explicit_httpx_transport_bypasses_configured_proxy(local_http_routes):
    origin,proxy,calls=local_http_routes
    async def run():
        async with httpx.AsyncClient(timeout=2) as client:
            assert (await client.post(origin+'/responses',json={})).json()['id']=='proxy'
        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0),timeout=2) as client:
            assert (await client.post(origin+'/responses',json={})).json()['id']=='origin'
    asyncio.run(run())
    assert [route for route,_,_ in calls]==['proxy','origin']


@pytest.mark.parametrize('no_proxy,expected',[('', 'proxy'),('127.0.0.1','origin'),('*','origin')])
def test_default_budget_route_honors_proxy_and_no_proxy(tmp_path,monkeypatch,local_http_routes,no_proxy,expected):
    import lab.sdk_budget as sdk
    origin,proxy,calls=local_http_routes
    monkeypatch.setenv('NO_PROXY',no_proxy)
    # The local approved endpoint is a fixture; production endpoint validation is tested separately.
    monkeypatch.setattr(sdk,'endpoint',lambda provider:origin)
    store,c,cfg=connection(tmp_path);p=store.create('P','en')
    async def run():
        transport=sdk.BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build')
        async with httpx.AsyncClient(transport=transport) as client:
            response=await client.post(origin+'/responses',json={'input':'hello'})
            assert response.json()['id']==expected
    asyncio.run(run())
    assert len(calls)==1 and calls[0][0]==expected
    record=store.get(p['id'])['records'][0]
    assert record['status']=='completed'
    assert json.loads((tmp_path/'workspace-receipts'/f"{record['id']}.json").read_bytes())['id']==expected


@pytest.mark.parametrize('failure,category',[
    (httpx.ConnectTimeout,'connection_timeout'),(httpx.ReadTimeout,'read_timeout'),
    (httpx.WriteTimeout,'write_timeout'),(httpx.PoolTimeout,'pool_timeout'),
    (httpx.ConnectError,'connection_error'),(httpx.ProxyError,'proxy_error'),
    (httpx.RemoteProtocolError,'transport_error'),(RuntimeError,'interrupted'),
])
def test_transport_failures_report_only_safe_category_and_never_retry(tmp_path,failure,category):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en');calls=[];closed=[];errors=[]
    secret='Bearer old-key-123 https://proxy-user:proxy-secret@private.invalid exception-secret'
    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self,request):
            calls.append(request)
            assert request.headers['Authorization']=='Bearer old-key-123'
            assert request.extensions['timeout']=={'connect':120,'read':120,'write':120,'pool':120}
            raise failure(secret)
        async def aclose(self):closed.append(True)
    async def run():
        transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=Transport())
        async with httpx.AsyncClient(transport=transport,timeout=120) as client:
            for _ in range(2):
                with pytest.raises(ValueError) as error:await client.post('https://api.openai.com/v1/responses',json={'input':'hello'})
                errors.append(str(error.value))
    asyncio.run(run())
    assert len(calls)==1 and closed==[True]
    record=store.get(p['id'])['records'][0]
    assert record['status']=='unknown' and record['committed_cost']==record['reserved_cost']>0
    assert record['diagnostic']==category and category in errors[0]
    assert 'No automatic retry' in record['error'] and 'No automatic retry' in errors[0]
    public=json.dumps({'record':record,'errors':errors})
    assert all(value not in public for value in ('old-key-123','proxy-user','proxy-secret','private.invalid','exception-secret'))
    assert not (tmp_path/'workspace-receipts').exists()


@pytest.mark.parametrize('status',[302,401,429,500])
def test_http_failure_retains_receipt_and_reservation_without_redirect_or_retry(tmp_path,status):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en');calls=[]
    raw=b'{"error":"private-response-secret"}'
    def provider(request):
        calls.append(request)
        return httpx.Response(status,headers={'Location':'https://not-approved.invalid/'},content=raw)
    async def run():
        transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=httpx.MockTransport(provider))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ValueError) as error:await client.post('https://api.openai.com/v1/responses',json={'input':'hello'})
            assert 'private-response-secret' not in str(error.value)
    asyncio.run(run())
    record=store.get(p['id'])['records'][0]
    assert len(calls)==1 and record['status']=='unknown' and record['diagnostic']=='provider_http_error'
    assert record['committed_cost']==record['reserved_cost']>0 and 'private-response-secret' not in json.dumps(record)
    assert (tmp_path/'workspace-receipts'/f"{record['id']}.json").read_bytes()==raw


@pytest.mark.parametrize('url,method',[
    ('https://not-approved.invalid/v1/responses','POST'),('https://api.openai.com/v1/models','POST'),
    ('https://api.openai.com/v1/responses','GET'),('http://api.openai.com/v1/responses','POST'),
])
def test_invalid_sdk_destination_never_dispatches_or_reserves(tmp_path,url,method):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en');closed=[]
    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self,request):pytest.fail('Invalid destination dispatched')
        async def aclose(self):closed.append(True)
    async def run():
        async with httpx.AsyncClient(transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=Transport())) as client:
            with pytest.raises(ValueError,match='destination'):await client.request(method,url,json={'input':'hello'})
    asyncio.run(run())
    assert store.get(p['id'])['records']==[] and closed==[True]


@pytest.mark.parametrize('mode',['success','oversize','read_error','cancel'])
def test_response_and_transport_close_even_on_interruption(tmp_path,mode):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en');closed=[];calls=[]
    async def run():
        entered=asyncio.Event()
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                if mode=='cancel':entered.set();await asyncio.Event().wait()
                if mode=='read_error':raise httpx.ReadError('private-stream-secret')
                yield b'x'*2000001 if mode=='oversize' else b'{"usage":{"input_tokens":1},"output":[]}'
            async def aclose(self):closed.append('response')
        class Transport(httpx.AsyncBaseTransport):
            async def handle_async_request(self,request):calls.append(request);return httpx.Response(200,stream=Stream())
            async def aclose(self):closed.append('transport')
        async with httpx.AsyncClient(transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=Transport())) as client:
            request=asyncio.create_task(client.post('https://api.openai.com/v1/responses',json={'input':'hello'}))
            if mode=='cancel':
                await asyncio.wait_for(entered.wait(),2);request.cancel()
                with pytest.raises(asyncio.CancelledError):await request
            elif mode=='success':assert (await request).status_code==200
            else:
                with pytest.raises(ValueError):await request
    asyncio.run(run())
    assert closed==['response','transport'] and len(calls)==1
    record=store.get(p['id'])['records'][0]
    assert record['status']==('completed' if mode=='success' else 'unknown')
    if mode!='success':assert record['committed_cost']==record['reserved_cost']>0
    if mode=='cancel':assert record['diagnostic']=='cancelled'
    assert 'private-stream-secret' not in json.dumps(record)


def test_unparseable_full_response_is_saved_before_unknown_failure(tmp_path):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en')
    raw=b'not-json-private-reply'
    async def run():
        transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=httpx.MockTransport(lambda request:httpx.Response(200,content=raw)))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ValueError) as error:await client.post('https://api.openai.com/v1/responses',json={'input':'hello'})
            assert 'not-json-private-reply' not in str(error.value)
    asyncio.run(run())
    record=store.get(p['id'])['records'][0]
    assert record['status']=='unknown' and record['committed_cost']==record['reserved_cost']>0
    assert (tmp_path/'workspace-receipts'/f"{record['id']}.json").read_bytes()==raw


@pytest.mark.parametrize('body,budget',[
    ({'input':'x'*(2*1024*1024)},10),({'input':[0]*((2*1024*1024)//3)},10),
    ({'input':'hello','stream':True},10),({'tools':[{'type':'web_search'}]},10),
    ({'input':'hello'},0),
])
def test_request_authority_and_budget_limits_remain_pre_dispatch(tmp_path,body,budget):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en')
    def provider(request):pytest.fail('Unsupported or unaffordable request dispatched')
    async def run():
        async with httpx.AsyncClient(transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',budget,'build',transport=httpx.MockTransport(provider))) as client:
            with pytest.raises(ValueError):await client.post('https://api.openai.com/v1/responses',json=body)
    asyncio.run(run());assert store.get(p['id'])['records']==[]


@pytest.mark.parametrize('request_bytes',[256_000,1_900_000])
def test_sdk_accepts_roomy_construction_context_with_budget_and_fixed_authority(tmp_path,request_bytes):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en');sent=[]
    def provider(request):
        sent.append(json.loads(request.content))
        record=store.get(p['id'])['records'][0]
        assert record['status']=='running' and record['reserved_cost']>0
        return httpx.Response(200,json={'usage':{'input_tokens':10,'output_tokens':20},'output':[]})
    async def run():
        async with httpx.AsyncClient(transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=httpx.MockTransport(provider))) as client:
            response=await client.post('https://api.openai.com/v1/responses',json={'input':'x'*request_bytes,'max_output_tokens':99999})
            assert response.status_code==200
    asyncio.run(run())
    assert len(sent)==1 and sent[0]['input']=='x'*request_bytes and sent[0]['max_output_tokens']==6000


def test_sdk_large_context_retains_long_context_output_cost_before_and_after_dispatch(tmp_path):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);cfg={**cfg,'model':'gpt-6-luna'};p=store.create('P','en');reserved=[]
    def provider(request):
        reserved.append(store.get(p['id'])['records'][0]['reserved_cost'])
        expected=((len(request.content)+8000)*cfg['input_price']*2+6000*cfg['output_price']*1.5)*1.5/1e6
        assert reserved[-1]==pytest.approx(expected)
        return httpx.Response(200,json={'usage':{'input_tokens':300000,'output_tokens':5000},'output':[]})
    async def run():
        async with httpx.AsyncClient(transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=httpx.MockTransport(provider))) as client:
            assert (await client.post('https://api.openai.com/v1/responses',json={'input':'x'*400000})).status_code==200
    asyncio.run(run())
    record=store.get(p['id'])['records'][0]
    assert record['committed_cost']==pytest.approx((300000*cfg['input_price']*2+5000*cfg['output_price']*1.5)/1e6)
    assert record['committed_cost']<reserved[0]


def test_completed_calls_stop_at_fifty_and_override_output_authority(tmp_path):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en');calls=[]
    def provider(request):
        body=json.loads(request.content);calls.append(body)
        assert body['model']=='model' and body['max_output_tokens']==6000 and body['store'] is False
        assert body['service_tier']=='default' and body['stream'] is False
        assert all(field not in body for field in ('previous_response_id','conversation','prompt_cache_retention'))
        assert request.headers['Authorization']=='Bearer old-key-123' and 'X-Untrusted' not in request.headers
        return httpx.Response(200,json={'usage':{'input_tokens':1,'output_tokens':1},'output':[]})
    async def run():
        async with httpx.AsyncClient(transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',transport=httpx.MockTransport(provider))) as client:
            for _ in range(50):
                response=await client.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer wrong-key','X-Untrusted':'do-not-forward'},json={'input':'hello','model':'wrong','max_output_tokens':999999,'store':True,'service_tier':'priority','previous_response_id':'old','conversation':'old','prompt_cache_retention':'24h'})
                assert response.status_code==200
            with pytest.raises(ValueError,match='limit'):await client.post('https://api.openai.com/v1/responses',json={'input':'hello'})
    asyncio.run(run())
    assert len(calls)==len(store.get(p['id'])['records'])==50


def test_sdk_contract_uses_pinned_private_hook_and_no_retry():
    from lab.sdk_builder import sdk_contract
    result=sdk_contract()
    assert result=={'version':'0.24.0','runner_retries':0,'client_retries':0,'tracing':False,'max_turns':50}


def test_sdk_preflight_does_not_allocate_an_unowned_http_client(monkeypatch):
    import openai
    from lab.sdk_builder import sdk_contract
    class NoClient:
        def __init__(self,*,api_key,max_retries):
            raise AssertionError('Preflight must not allocate a client')
    monkeypatch.setattr(openai,'AsyncOpenAI',NoClient)
    assert sdk_contract()['client_retries']==0


def test_every_sdk_internal_exec_uses_bounded_nonroot_adapter():
    from lab.sdk_builder import bound_session
    from types import SimpleNamespace
    import subprocess
    calls=[]
    def run(args,**kwargs):calls.append((args,kwargs));return subprocess.CompletedProcess(args,0,'ok','')
    async def stream(**kwargs):pass
    inner=SimpleNamespace(_stream_into_exec=stream)
    bound_session(inner,SimpleNamespace(run=run))
    async def check():
        result=await inner._exec_run(cmd=['sh','-c','echo ok'],workdir=None,user=None,timeout=None,command_for_errors=(),kill_on_timeout=True)
        assert result.stdout==b'ok' and result.exit_code==0
        with pytest.raises(ValueError):await inner._exec_run(cmd=['id'],workdir=None,user='root',timeout=100,command_for_errors=(),kill_on_timeout=False)
    asyncio.run(check())
    assert calls==[(['sh','-c','echo ok'],{'timeout':20,'output_limit':65536})]
    assert inner.supports_pty() is False


def test_sdk_borrows_prestarted_session_so_runner_cannot_delete_outputs(monkeypatch):
    import lab.sdk_builder as builder
    from lab.build_runtime import construction_prompt
    from types import SimpleNamespace
    import agents
    events=[]
    class Session:
        async def start(self):events.append('started')
    session=Session()
    class Client:
        async def create(self,**kwargs):
            assert kwargs['snapshot'].type=='noop';return session
    monkeypatch.setattr(builder,'hardened_client',lambda task:Client())
    async def run(agent,prompt,**kwargs):
        assert agent.run_as is None, 'Docker owns numeric identity; SDK must not provision an account'
        assert agent.instructions==construction_prompt('python')
        assert kwargs['run_config'].sandbox.session is session
        assert kwargs['max_turns']==50
        assert events==['started']
        assert kwargs['run_config'].tracing_disabled and agent.model_settings.retry.max_retries==0
        assert agent.model_settings.reasoning.effort=='low'
        return SimpleNamespace(final_output='done')
    monkeypatch.setattr(agents.Runner,'run',run)
    assert asyncio.run(builder.construct(SimpleNamespace(),construction_prompt('python'),httpx.MockTransport(lambda r:None),{'model':'model','reasoning_effort':'low'}))=='done'


def test_expired_task_blocks_before_reservation(tmp_path):
    from lab.sdk_budget import BudgetTransport
    store,c,cfg=connection(tmp_path);p=store.create('P','en')
    def expired():raise ValueError('task expired')
    async def run():
        transport=BudgetTransport(store,c,p['id'],cfg,'old-key-123',10,'build',check_task=expired)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ValueError,match='expired'):await client.post('https://api.openai.com/v1/responses',json={'input':'hello'})
    asyncio.run(run());assert store.get(p['id'])['records']==[]


def test_blocked_build_keeps_collected_explanation(tmp_path,monkeypatch):
    import lab.sdk_builder as sdk
    from lab.build_runtime import Builder
    from tests.test_project_runs_api import prepared
    store,pid,runs=prepared(tmp_path);project=store.get(pid);version=project['versions'][0]
    store.mutate(pid,lambda p:p['builds'][0].update(status='running'))
    class Task:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def seed(self,files):self.files=files
        def probe(self):pass
        def inspect(self):pass
        def collect(self):return [{'name':name,'text':text} for name,text in dict(self.files,**{'BLOCKED.md':'Need a sizing decision.'}).items()]
    async def construct(*args):return 'Blocked by method question.'
    monkeypatch.setattr(sdk,'DockerTask',Task);monkeypatch.setattr(sdk,'construct',construct)
    sdk.run_build(Builder(store,runs.connections),pid,'build1',version,{'id':'connection'},'unused',1,'prompt')
    build=store.get(pid)['builds'][0]
    assert build['status']=='failed' and any(a['name']=='BLOCKED.md' for a in build['artifacts'])


def test_path_helper_uses_pinned_content_not_mutable_tmp_file():
    import subprocess
    from types import SimpleNamespace
    from agents.sandbox.session.runtime_helpers import RESOLVE_WORKSPACE_PATH_HELPER as helper
    from lab.sdk_builder import bound_session
    calls=[]
    def run(cmd,**kw):calls.append((cmd,kw));return subprocess.CompletedProcess(cmd,0,'/workspace/file','')
    async def stream(**kw):pass
    inner=SimpleNamespace(_stream_into_exec=stream);bound_session(inner,SimpleNamespace(run=run))
    candidate='/workspace/quote ; $(touch nope).txt'
    async def check():
        await inner._exec_run(cmd=[str(helper.install_path),'/workspace',candidate,'0'],workdir=None,user=None,timeout=3,command_for_errors=(),kill_on_timeout=True)
    asyncio.run(check())
    assert calls[0][0]==['/bin/sh','-c',helper.content,str(helper.install_path),'/workspace',candidate,'0']
    assert calls[0][1]=={'timeout':3,'output_limit':65536}

    async def ordinary():
        await inner._exec_run(cmd=['/tmp/openai-agents/bin/resolve-workspace-path-other','arg'],workdir=None,user=None,timeout=None,command_for_errors=(),kill_on_timeout=True)
    asyncio.run(ordinary())
    assert calls[1][0]==['/tmp/openai-agents/bin/resolve-workspace-path-other','arg']


@pytest.mark.parametrize('field,value',[('content','#!/bin/sh\necho unsafe'),('install_path','/tmp/other-helper'),('name','other-helper')])
def test_sdk_contract_rejects_changed_path_helper(monkeypatch,field,value):
    from dataclasses import replace
    import agents.sandbox.session.runtime_helpers as helpers
    from lab.sdk_builder import sdk_contract
    monkeypatch.setattr(helpers,'RESOLVE_WORKSPACE_PATH_HELPER',replace(helpers.RESOLVE_WORKSPACE_PATH_HELPER,**{field:value}))
    with pytest.raises(ValueError,match='helper'):sdk_contract()


@pytest.mark.parametrize('timeout',[0,-1,float('inf'),float('nan')])
def test_internal_exec_rejects_invalid_timeout(timeout):
    from types import SimpleNamespace
    from lab.sdk_builder import bound_session
    async def stream(**kw):pass
    def run(*a,**kw):pytest.fail('Invalid timeout must not dispatch')
    inner=SimpleNamespace(_stream_into_exec=stream);bound_session(inner,SimpleNamespace(run=run))
    with pytest.raises(ValueError,match='timeout'):
        asyncio.run(inner._exec_run(cmd=['id'],workdir=None,user=None,timeout=timeout,command_for_errors=(),kill_on_timeout=True))


@pytest.mark.parametrize('cleanup_fails',[False,True])
def test_internal_exec_cancellation_closes_task_and_preserves_cancel(cleanup_fails):
    import threading
    import subprocess
    from types import SimpleNamespace
    from lab.sdk_builder import bound_session
    entered=threading.Event();release=threading.Event();closed=[]
    def run(*a,**kw):entered.set();release.wait(2);return subprocess.CompletedProcess(a,0,'','')
    def close():
        closed.append(True);release.set()
        if cleanup_fails:raise ValueError('fixture cleanup failure')
    async def stream(**kw):pass
    inner=SimpleNamespace(_stream_into_exec=stream);bound_session(inner,SimpleNamespace(run=run,close=close))
    async def check():
        running=asyncio.create_task(inner._exec_run(cmd=['sleep','2'],workdir=None,user=None,timeout=20,command_for_errors=(),kill_on_timeout=True))
        try:
            assert await asyncio.to_thread(entered.wait,1)
            running.cancel()
            with pytest.raises(asyncio.CancelledError) as error:await running
            assert closed==[True]
            if cleanup_fails:assert 'fixture cleanup failure' in error.value.__notes__
        finally:release.set()
    asyncio.run(check())


def test_stream_forces_nonroot_and_preserves_cancellation_on_cleanup_failure():
    import io
    from pathlib import Path
    from types import SimpleNamespace
    from lab.sdk_builder import bound_session
    calls=[]
    async def stream(**kw):
        calls.append(kw);assert kw['user']=='10001:10001' and kw['stream'].read()==b'fixture'
        raise asyncio.CancelledError()
    def close():raise ValueError('fixture cleanup failure')
    inner=SimpleNamespace(_stream_into_exec=stream);bound_session(inner,SimpleNamespace(close=close))
    async def check():
        with pytest.raises(ValueError,match='user'):await inner._stream_into_exec(cmd=['cat'],stream=io.BytesIO(),error_path=Path('file'),user='root')
        with pytest.raises(asyncio.CancelledError) as error:await inner._stream_into_exec(cmd=['cat'],stream=io.BytesIO(b'fixture'),error_path=Path('file'),user=None)
        assert 'fixture cleanup failure' in error.value.__notes__
    asyncio.run(check());assert len(calls)==1


@pytest.mark.parametrize('cmd,workdir',[
    (['id'],'/workspace/../tmp'),
    (['/tmp/openai-agents/bin/resolve-workspace-path-62a6e78539cf','/','/tmp','0'],None),
    (['/tmp/openai-agents/bin/resolve-workspace-path-62a6e78539cf','/workspace','/tmp','0','/tmp','0'],None),
])
def test_internal_exec_rejects_workdir_or_helper_authority(cmd,workdir):
    from types import SimpleNamespace
    from lab.sdk_builder import bound_session
    async def stream(**kw):pass
    def run(*a,**kw):pytest.fail('Invalid scope must not dispatch')
    inner=SimpleNamespace(_stream_into_exec=stream);bound_session(inner,SimpleNamespace(run=run))
    with pytest.raises(ValueError):asyncio.run(inner._exec_run(cmd=cmd,workdir=workdir,user=None,timeout=None,command_for_errors=(),kill_on_timeout=True))
