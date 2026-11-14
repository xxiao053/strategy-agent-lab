import json
import httpx
import pytest

pytestmark = pytest.mark.market_data
from lab.contracts import RunConfig
from lab.providers import Adapter, ProviderError
from lab.runner import Runner
from lab.store import Store
from lab.market import load_snapshot
from tests.test_workflow import ROOT
from tests.helpers import bound_reply


def test_baseline_cannot_be_designated_as_a_real_model_showcase(tmp_path):
    s=Store(tmp_path/'lab.db');r=Runner(ROOT,s)
    baseline=r.create(RunConfig(approved=True,symbols=['AAPL'],start='2024-12-19',end='2024-12-23'))
    r.execute(baseline['id'])
    with pytest.raises(ValueError,match='model'):
        s.set_showcase({'run_id':baseline['id'],'baseline_id':baseline['id'],'replay_id':baseline['id']})
    assert s.showcase() is None


def test_model_status_names_the_observed_model_not_all_provider_models(tmp_path):
    s=Store(tmp_path/'lab.db')
    cfg=RunConfig(approved=True)
    run=Runner(ROOT,s).create(cfg)
    assert s.model_status()=={}
    s.begin_request(run['id'],'n','x','h',.01,{'body':{}})
    s.save_response('x',{'id':'resp_offline_fixture','model':'gpt-6-luna','status':'completed'}, {'input':100,'output':10,'reported':True},1)
    status=s.model_status()
    assert status['openai']['models']==['gpt-6-luna']
    assert 'qwen' not in status
    assert status['openai']['requests']==1


def test_budget_scope_is_immutable_and_shared_across_runs(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','offline-test')
    s=Store(tmp_path/'lab.db')
    s.authorize_budget('acceptance',.5)
    with pytest.raises(ValueError):s.authorize_budget('acceptance',2)
    cfg=RunConfig(mode='live',approved=True,paid_authorized=True,budget_scope='acceptance',symbols=['AAPL'],start='2024-12-19',end='2024-12-23')
    r=Runner(ROOT,s)
    one=r.create(cfg)
    s.begin_request(one['id'],'fixture','fixture','hash',.5,{'body':{}})
    s.request_status('fixture','unknown')
    def handler(req):pytest.fail('Shared budget must stop before transport')
    two=Runner(ROOT,s,client=httpx.Client(transport=httpx.MockTransport(handler)))
    run=two.create(cfg);two.execute(run['id'])
    assert s.get(run['id'])['status']=='paused'
    assert 'shared' in s.get(run['id'])['reason'].lower()
    assert len(s.requests(run['id']))==0
    assert s.budget_status('acceptance')['committed_usd']==.5


def test_missing_usage_keeps_budget_reservation(tmp_path):
    s=Store(tmp_path/'lab.db')
    cfg=RunConfig(approved=True)
    r=Runner(ROOT,s).create(cfg)
    s.begin_request(r['id'],'node','receipt','hash',.1,{'body':{}})
    s.save_response('receipt',{'status':'completed'},{'reported':False},1)
    assert s.get(r['id'])['summary']['unresolved_reserve']==.1


def test_safe_provider_error_includes_parameter_but_no_secret():
    def handler(req):return httpx.Response(400,json={'error':{'type':'invalid_request_error','code':'invalid_json_schema','param':'text.format.schema','message':'secret-value'}})
    a=Adapter('openai',httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderError) as e:a.send(RunConfig(),{'system':'','text':'','image':''},[],'secret-value')
    assert 'text.format.schema' in str(e.value)
    assert 'invalid_json_schema' in str(e.value)
    assert 'secret-value' not in str(e.value)


def test_numeric_rejection_explains_handle_length_without_changing_execution():
    from lab.strategy import diagnose_anchors,hard_checks
    from lab.contracts import Strategy
    cfg=RunConfig(strategy=Strategy(cup_max=100,handle_max=20));bars=load_snapshot(ROOT,['MSFT'],cfg.start,cfg.end)['MSFT']
    dates=[b.date for b in bars];l,r,t=[dates.index(d) for d in ['2023-07-18','2023-11-10','2024-01-19']]
    checks=diagnose_anchors(bars,t,l,r,cfg.strategy)
    length=next(x for x in checks if x['name']=='handle_sessions')
    assert length['value']==45
    assert length['passed'] is False
    assert length['minimum']==3 and length['maximum']==20
    assert hard_checks(bars,t,l,r,cfg.strategy) is None


def test_repair_includes_failed_answer_and_precise_error(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','offline-key')
    calls=[]
    def handler(req):
        body=json.loads(req.content);calls.append(body)
        ctx=json.loads(body['input'][0]['content'][0]['text']);dates=[b['date'] for b in ctx['bars']]
        if len(calls)==2:
            assert any(item.get('type')=='message' for item in body['input'][1:])
            assert 'Overall verdict inconsistent' in json.dumps(body['input'][1:])
            assert ctx['cutoff'] in json.dumps(body['input'][1:])
        decision=bound_reply(ctx)
        if len(calls)==1:
            decision['assessments'][0]['verdict']='pass'
        return httpx.Response(200,json={'id':'resp_fixture','model':'gpt-6-luna','status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(decision)}]}],'usage':{'input_tokens':100,'output_tokens':50}})
    s=Store(tmp_path/'lab.db');r=Runner(ROOT,s,client=httpx.Client(transport=httpx.MockTransport(handler)))
    run=r.create(RunConfig(symbols=['AAPL'],start='2024-12-19',end='2024-12-23',mode='live',approved=True,paid_authorized=True,review_enabled=False));r.execute(run['id'])
    assert s.get(run['id'])['status']=='completed'
    assert len(calls)==2


def test_new_controller_run_reuses_exact_saved_responses_without_rebilling(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','offline-key')
    def handler(req):
        ctx=json.loads(json.loads(req.content)['input'][0]['content'][0]['text']);dates=[b['date'] for b in ctx['bars']]
        decision=bound_reply(ctx)
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(decision)}]}],'usage':{'input_tokens':100,'output_tokens':50}})
    s=Store(tmp_path/'lab.db');r=Runner(ROOT,s,client=httpx.Client(transport=httpx.MockTransport(handler)))
    s.authorize_budget('reuse-test',1)
    cfg=RunConfig(symbols=['AAPL'],start='2024-12-19',end='2024-12-23',mode='live',approved=True,paid_authorized=True,budget_scope='reuse-test',review_enabled=False)
    source=r.create(cfg);r.execute(source['id'])
    cfg=RunConfig(**{**cfg.model_dump(),'reuse_responses_from':source['id']})
    def no_network(req):pytest.fail('Exact saved response must be reused, not recharged')
    resumed=Runner(ROOT,s,client=httpx.Client(transport=httpx.MockTransport(no_network)))
    new=resumed.create(cfg);resumed.execute(new['id'])
    assert s.get(new['id'])['status']=='completed'
    assert s.get(new['id'])['state']==s.get(source['id'])['state']
    assert s.get(new['id'])['summary']['requests']==0
    assert s.get(new['id'])['summary']['reused_responses']==1
    assert s.requests(new['id'])[0]['source_request_id']==s.requests(source['id'])[0]['id']
    assert s.budget_status('reuse-test')['requests']==1

