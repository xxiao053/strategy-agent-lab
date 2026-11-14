"""Provider counting refines an excessive estimate without authorizing more spend."""
import json
import httpx
import pytest
from lab.providers import Adapter,ProviderError
from tests.test_visual_inputs import visual_judge
from tests.test_project_execution import proposal
from tests.test_project_judgment import response


def count_response(value):
    return httpx.Response(200,stream=httpx.ByteStream(json.dumps({'object':'response.input_tokens','input_tokens':value}).encode()))


def test_count_uses_only_non_generating_endpoint_and_complete_input():
    seen=[]
    wire=dict(model='selected-model',input=[{'role':'user','content':[{'type':'input_image','image_url':'data:image/png;base64,abc','detail':'high'}]}],
              instructions='rules',tools=[],text={'format':{'type':'json_object'}},reasoning={'effort':'low'},store=False,max_output_tokens=1500)
    def transport(request):
        seen.append(request)
        assert str(request.url)=='https://api.openai.com/v1/responses/input_tokens'
        assert json.loads(request.content)=={k:v for k,v in wire.items() if k not in ('store','max_output_tokens')}
        return count_response(1234)
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        assert Adapter('openai',client).count_input_tokens(wire,'private-key')==1234
    assert len(seen)==1


def test_count_reaches_provider_through_operator_configured_proxy(monkeypatch):
    # Keep the real Client's environment routing; replace only the network boundary.
    for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy'):
        monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:18080')
    def direct(request):
        raise httpx.ConnectTimeout('Direct route unavailable')
    def proxy_transport(self,proxy,**kwargs):
        assert str(proxy.url)=='http://127.0.0.1:18080'
        return httpx.MockTransport(lambda request:count_response(1234))
    monkeypatch.setattr(httpx.Client,'_init_transport',lambda self,**kwargs:httpx.MockTransport(direct))
    monkeypatch.setattr(httpx.Client,'_init_proxy_transport',proxy_transport)
    assert Adapter('openai').count_input_tokens({'model':'chosen','input':'text'},'private-key')==1234


@pytest.mark.parametrize('value',[True,0,-1,3.5,'100',10000001])
def test_invalid_counts_never_become_a_cheap_reservation(value):
    with httpx.Client(transport=httpx.MockTransport(lambda req:count_response(value))) as client:
        with pytest.raises(ProviderError):Adapter('openai',client).count_input_tokens({'model':'chosen','input':'text'},'private-key')


def test_budget_refinement_retains_images_and_reserves_before_inference(tmp_path,monkeypatch):
    seen=[];bodies=[]
    def transport(request):
        seen.append(request.url.path);bodies.append(json.loads(request.content))
        if request.url.path.endswith('/input_tokens'):
            return count_response(1000)
        record=store.get(pid)['records'][-1]
        assert record['status']=='running' and 0<record['reserved_cost']<=.05
        assert record['image_input']['counted_input_tokens']==1000
        assert record['image_input']['reservation_input_tokens']>=2250
        return httpx.Response(200,json=response())
    store,pid,judge,context=visual_judge(tmp_path,monkeypatch,transport);judge.budget=.05
    decision={'id':'d1'}
    result=judge(decision,context,proposal(judgment='Inspect approved criteria'))
    assert result['verdict']=='pass'
    assert seen==['/v1/responses/input_tokens','/v1/responses']
    assert bodies[0]['input']==bodies[1]['input'] and bodies[0]['text']==bodies[1]['text']
    assert len(store.get(pid)['records'])==1 and len(decision['images'])==1


@pytest.mark.parametrize('failure',['http','invalid','timeout','expensive'])
def test_count_failure_or_still_excessive_cost_never_dispatches_inference(tmp_path,monkeypatch,failure):
    calls=[]
    def transport(request):
        calls.append(request.url.path)
        assert request.url.path.endswith('/input_tokens')
        if failure=='timeout':raise httpx.ReadTimeout('private-key confidential diagnostic')
        if failure=='http':return httpx.Response(401,text='private-key confidential diagnostic')
        return count_response(False if failure=='invalid' else 1000000)
    store,pid,judge,context=visual_judge(tmp_path,monkeypatch,transport);judge.budget=.05
    with pytest.raises(ValueError) as error:judge({'id':'d1'},context,proposal(judgment='Inspect'))
    assert 'private-key' not in str(error.value) and 'confidential' not in str(error.value)
    assert calls==['/v1/responses/input_tokens'] and not store.get(pid)['records']


def test_stale_connection_cannot_send_context_to_count_endpoint(tmp_path,monkeypatch):
    store,pid,judge,context=visual_judge(tmp_path,monkeypatch,lambda req:pytest.fail('No network for stale connection'))
    judge.budget=.05;judge.cfg['generation']-=1
    with pytest.raises(ValueError):judge({'id':'d1'},context,proposal(judgment='Inspect'))
    assert not store.get(pid)['records']


def test_count_rejects_compression_before_reading_or_expanding_body():
    import gzip
    reads=[]
    class Compressed(httpx.SyncByteStream):
        def __iter__(self):
            reads.append(1)
            yield gzip.compress(b'x'*1000000)
    def transport(request):
        return httpx.Response(200,headers={'Content-Encoding':'gzip'},stream=Compressed())
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(ProviderError):Adapter('openai',client).count_input_tokens({'model':'chosen','input':'text'},'private-key')
    assert reads==[]


def test_count_deadline_checks_each_unaggregated_transport_chunk(monkeypatch):
    clock=[0.];reads=[]
    monkeypatch.setattr('lab.providers.time.monotonic',lambda:clock[0])
    class Trickle(httpx.SyncByteStream):
        def __iter__(self):
            for i in range(10):
                clock[0]+=7.;reads.append(i)
                yield b' '
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,stream=Trickle()))) as client:
        with pytest.raises(ProviderError,match='deadline'):
            Adapter('openai',client).count_input_tokens({'model':'chosen','input':'text'},'private-key')
    assert len(reads)==3
