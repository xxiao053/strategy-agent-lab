import json
import base64
import httpx
import pytest

pytestmark = pytest.mark.market_data
from lab.contracts import RunConfig
from lab.market import load_snapshot
from lab.prompts import make_context, tool_result
from lab.providers import Adapter, PROVIDERS
from lab.runner import Runner, ENGINE_VERSION
from lab.store import Store
from tests.test_workflow import ROOT
from tests.helpers import bound_reply


def sample_context():
    c=RunConfig(symbols=['QQQ'],start='2024-11-05',end='2024-11-08')
    bars=load_snapshot(ROOT,c.symbols,c.start,c.end)['QQQ']
    i=next(i for i,b in enumerate(bars) if b.date=='2024-11-06')
    return c,bars[:i+1],make_context('QQQ',bars,i,c)


def test_context_freezes_candidates_includes_attributed_examples_and_no_future():
    cfg,bars,ctx=sample_context();obj=json.loads(ctx['text'])
    assert len(obj['candidates']) in [1,2,3]
    assert obj['stage']=='primary'
    assert obj['reference_pack']['cases']
    assert any(x['source_url'].startswith('https://chartschool.stockcharts.com') for x in obj['reference_pack']['cases'])
    assert all(x['provenance'] for x in obj['reference_pack']['cases'])
    assert ctx['schema']['properties']['assessments']
    assert ctx['images'] and base64.b64decode(ctx['images'][0]).startswith(b'\x89PNG')
    assert '2024-11-07' not in ctx['text']


def test_inspection_returns_only_offered_geometry_metrics_and_local_chart():
    cfg,bars,ctx=sample_context();choices=ctx['candidates']
    call=dict(name='inspect_candidate',arguments={'candidate_id':choices[0]['candidate_id'],'section':'handle'})
    result=tool_result(call,'QQQ',bars,candidates=choices)
    assert result['candidate_id']==choices[0]['candidate_id']
    assert result['_image'] and result['metrics']['target']==choices[0]['target']
    assert all(b['date']<=bars[-1].date for b in result['bars'])
    call['arguments']['candidate_id']='../../not-offered'
    assert 'error' in tool_result(call,'QQQ',bars,candidates=choices)


@pytest.mark.parametrize('provider',[p for p in PROVIDERS if p!='deepseek'])
def test_tool_image_is_native_attachment_not_base64_in_text(provider):
    a=Adapter(provider)
    if provider=='openai':
        raw={'status':'completed','output':[{'type':'function_call','call_id':'c','name':'inspect_candidate','arguments':'{}'}]}
    elif provider=='anthropic':
        raw={'stop_reason':'tool_use','content':[{'type':'tool_use','id':'c','name':'inspect_candidate','input':{}}]}
    elif provider=='gemini':
        raw={'candidates':[{'finishReason':'STOP','content':{'role':'model','parts':[{'functionCall':{'id':'c','name':'inspect_candidate','args':{}}}]}}]}
    else:
        raw={'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'c','type':'function','function':{'name':'inspect_candidate','arguments':'{}'}}]}}]}
    history=a.followup(a.parse(raw),[{'candidate_id':'fixed','_image':'aGVsbG8='}])
    text=json.dumps(history)
    assert '\\"_image\\"' not in text and '"_image"' not in text
    assert 'aGVsbG8=' in text
    assert any(k in text for k in ['input_image','inlineData','image_url','base64'])


def response(obj):
    return httpx.Response(200,json={'id':'offline-response','model':'gpt-6-luna','status':'completed',
        'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(obj)}]}],
        'usage':{'input_tokens':100,'output_tokens':50}})


@pytest.mark.parametrize('primary_pass,expected_requests',[(True,1),(False,2)])
def test_primary_and_targeted_review_are_preserved_and_replay_without_inference(tmp_path,monkeypatch,primary_pass,expected_requests):
    monkeypatch.setenv('OPENAI_API_KEY','offline-only')
    seen=[]
    def handler(request):
        ctx=json.loads(json.loads(request.content)['input'][0]['content'][0]['text']);seen.append(ctx)
        if ctx['stage']=='review':
            assert ctx['prior_assessments']
            assert all(x['verdict']!='pass' for x in ctx['prior_assessments'])
        return response(bound_reply(ctx,'pass' if primary_pass or ctx['stage']=='review' else 'fail'))
    store=Store(tmp_path/'db');runner=Runner(ROOT,store,httpx.Client(transport=httpx.MockTransport(handler)))
    cfg=RunConfig(symbols=['QQQ'],start='2024-11-05',end='2024-11-08',mode='live',approved=True,paid_authorized=True)
    run=runner.create(cfg);runner.execute(run['id']);done=store.get(run['id'])
    assert done['status']=='completed',done['reason']
    assert len(seen)==expected_requests
    event=next(e for e in done['state']['decisions'] if e['decision'])
    assert event['primary_evaluations']
    assert bool(event['review_evaluations']) is (not primary_pass)
    assert event['validation']['pattern']['candidate_id']==event['decision']['candidate_id']
    assert done['state']['account']['orders'][0]['candidate_id']==event['decision']['candidate_id']
    replay=runner.replay(run['id']);runner.execute(replay['id'])
    assert store.get(replay['id'])['state']==done['state']
    assert len(seen)==expected_requests


def test_unknown_candidate_does_not_silently_become_rejection(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','offline-only');seen=[]
    def handler(request):
        ctx=json.loads(json.loads(request.content)['input'][0]['content'][0]['text']);seen.append(ctx)
        obj=bound_reply(ctx,'pass');obj['assessments'][0]['candidate_id']='invented'
        return response(obj)
    store=Store(tmp_path/'db');runner=Runner(ROOT,store,httpx.Client(transport=httpx.MockTransport(handler)))
    r=runner.create(RunConfig(symbols=['QQQ'],start='2024-11-05',end='2024-11-08',mode='live',approved=True,paid_authorized=True))
    runner.execute(r['id'])
    assert store.get(r['id'])['status']=='paused'
    assert len(seen)==2
    assert not (store.get(r['id'])['state'] or {}).get('account',{}).get('orders')


def test_archived_completed_snapshot_is_not_reinterpreted_by_new_engine(tmp_path):
    store=Store(tmp_path/'db');cfg=RunConfig().model_dump()
    cfg['strategy'].pop('version');cfg['strategy']['max_holding']=40
    old=store.create(cfg,{},'old-data')
    state={'engine':'cup-account-v1','day':1,'account':{'curve':[],'orders':[],'trades':[],'positions':{},'cash':100000},'decisions':[],'benchmark':[]}
    store.checkpoint(old['id'],state);store.status(old['id'],'completed')
    copied=Runner(ROOT,store).replay(old['id'])
    assert copied['status']=='completed'
    assert copied['state']==state
    assert copied['archive_replay'] is True
    assert store.get(old['id'])['config']==cfg
    assert ENGINE_VERSION!='cup-account-v1'


def test_old_one_height_config_is_not_silently_replayed_with_three_height_default(tmp_path):
    s=Store(tmp_path/'db');cfg=RunConfig().model_dump();cfg['strategy'].pop('target_multiple',None)
    old=s.create(cfg,{},'original-data')
    state={'engine':ENGINE_VERSION,'day':1,'account':{'curve':[],'orders':[],'trades':[],'positions':{},'cash':100000},'decisions':[],'benchmark':[]}
    s.checkpoint(old['id'],state);s.status(old['id'],'completed')
    assert s.get(old['id'])['archived'] is True
    copied=Runner(ROOT,s).replay(old['id'])
    assert copied['archive_replay'] is True and copied['state']==state
    assert s.get(old['id'])['config']==cfg


def test_tool_repair_and_review_are_bounded_and_resume_reuses_all_six_receipts(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','offline-only');stages={};seen=[]
    def handler(request):
        body=json.loads(request.content);ctx=json.loads(body['input'][0]['content'][0]['text'])
        stage=ctx['stage'];stages[stage]=stages.get(stage,0)+1;seen.append(stage)
        if stages[stage]==1:
            return httpx.Response(200,json={'status':'completed','output':[{'type':'function_call','call_id':stage,
                'name':'inspect_candidate','arguments':json.dumps({'candidate_id':ctx['candidates'][0]['candidate_id'],'section':'handle'})}],
                'usage':{'input_tokens':100,'output_tokens':50}})
        obj=bound_reply(ctx,'fail')
        if stages[stage]==2:obj['assessments'][0]['candidate_id']='wrong-id'
        if stages[stage]==3:
            assert 'tools' not in body
            assert 'wrong-id' in json.dumps(body)
        return response(obj)
    s=Store(tmp_path/'db');r=Runner(ROOT,s,httpx.Client(transport=httpx.MockTransport(handler)))
    cfg=RunConfig(symbols=['QQQ'],start='2024-11-05',end='2024-11-08',mode='live',approved=True,paid_authorized=True,use_images=False)
    run=r.create(cfg);r.execute(run['id']);done=s.get(run['id'])
    assert done['status']=='completed',done['reason']
    assert seen==['primary']*3+['review']*3
    assert len(s.requests(run['id']))==6
    assert not done['state']['account']['orders']
    with s.db() as db:db.execute("UPDATE runs SET state_json=NULL,status='paused' WHERE id=?",(run['id'],))
    r.execute(run['id'])
    assert s.get(run['id'])['state']==done['state'] and len(seen)==6


def test_review_only_receives_nonpasses_and_cannot_erase_primary_pass(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','offline-only');primary_id=[]
    def handler(request):
        ctx=json.loads(json.loads(request.content)['input'][0]['content'][0]['text'])
        obj=bound_reply(ctx,'fail')
        if ctx['stage']=='primary':
            assert len(ctx['candidates'])==3
            primary_id.append(ctx['candidates'][0]['candidate_id'])
            obj['assessments'][0]=bound_reply({'candidates':[ctx['candidates'][0]]},'pass')['assessments'][0]
        else:
            assert primary_id[0] not in [c['candidate_id'] for c in ctx['candidates']]
            assert len(ctx['candidates'])==2
        return response(obj)
    s=Store(tmp_path/'db');r=Runner(ROOT,s,httpx.Client(transport=httpx.MockTransport(handler)))
    run=r.create(RunConfig(symbols=['AAPL'],start='2024-12-19',end='2024-12-23',mode='live',approved=True,paid_authorized=True,use_images=False))
    r.execute(run['id']);done=s.get(run['id'])
    assert done['status']=='completed',done['reason']
    event=next(e for e in done['state']['decisions'] if e['evaluations'])
    assert event['decision']['candidate_id']==primary_id[0]
    assert len(event['primary_evaluations'])==3 and len(event['review_evaluations'])==2
    assert [x['verdict'] for x in event['evaluations']]==['pass','fail','fail']


def test_disabled_tools_cannot_execute_a_hallucinated_inspection(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','offline-only');seen=[]
    def handler(request):
        body=json.loads(request.content);ctx=json.loads(body['input'][0]['content'][0]['text']);seen.append(body)
        if len(seen)==1:
            return httpx.Response(200,json={'status':'completed','output':[{'type':'function_call','call_id':'x','name':'inspect_candidate',
                'arguments':json.dumps({'candidate_id':ctx['candidates'][0]['candidate_id'],'section':'handle'})}]})
        outputs=[x for x in body['input'] if x.get('type')=='function_call_output']
        assert outputs and 'error' in json.loads(outputs[0]['output'])
        assert 'metrics' not in json.loads(outputs[0]['output'])
        return response(bound_reply(ctx,'fail'))
    s=Store(tmp_path/'db');r=Runner(ROOT,s,httpx.Client(transport=httpx.MockTransport(handler)))
    run=r.create(RunConfig(symbols=['QQQ'],start='2024-11-05',end='2024-11-08',mode='live',approved=True,paid_authorized=True,use_images=False,use_tools=False,review_enabled=False))
    r.execute(run['id']);done=s.get(run['id'])
    assert done['status']=='completed',done['reason']
    assert len(seen)==2
