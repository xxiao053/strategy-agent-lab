"""Regression coverage for avoidable calls and incomplete structured responses."""
import copy
import json
import httpx
import pytest

pytestmark = pytest.mark.market_data

from lab.account import Account
from lab.contracts import RunConfig, Strategy
from lab.runner import Runner
from lab.store import Store
from tests.helpers import bound_reply, exit_facts
from tests.test_workflow import ROOT
from tests.test_candidate_workflow import response, sample_context


def test_cash_gate_skips_inference_and_records_reason(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-test')
    def handler(request):
        pytest.fail('Unfundable candidate must not reach provider')
    store = Store(tmp_path/'db')
    runner = Runner(ROOT, store, httpx.Client(transport=httpx.MockTransport(handler)))
    cfg = RunConfig(symbols=['QQQ'], start='2024-11-05', end='2024-11-08', capital=100,
                    mode='live', approved=True, paid_authorized=True, use_images=False)
    run = runner.create(cfg)
    runner.execute(run['id'])
    done = store.get(run['id'])
    assert done['status'] == 'completed', done['reason']
    assert done['summary']['requests'] == 0
    event = next(d for d in done['state']['decisions'] if d['candidates'])
    assert event['validation']['reason'] == 'not_executable'
    assert event['execution_precheck']['eligible'] is False
    assert not event['primary_evaluations']


def test_entry_check_respects_reserved_cash_and_pending_slots():
    s = Strategy(risk_fraction=1, max_weight=1, max_positions=1, entry_gap_limit=0,
                 commission=0, slippage=0)
    a = Account(100)
    assert a.enter('AAPL', '2024-01-02', 60, 50, s, exit_facts(50))
    assert a.cash == 100 and a.available == 40
    check = a.entry_check('MSFT', 60, s, exit_facts(50))
    assert not check['eligible'] and check['reason'] == 'position_slots'
    s.max_positions = 2
    check = a.entry_check('MSFT', 60, s, exit_facts(50))
    assert not check['eligible'] and check['quantity'] == 0


def test_request_schema_requires_each_exact_candidate():
    from jsonschema import Draft202012Validator
    from lab.prompts import candidate_schema
    from lab.contracts import CandidateBatch
    _, _, ctx = sample_context()
    choices = [dict(ctx['candidates'][0], candidate_id=k) for k in ['fixed-A', 'fixed-B']]
    schema = candidate_schema(choices)
    assessments = schema['properties']['assessments']
    assert assessments['type'] == 'object'
    assert set(assessments['required']) == {'fixed-A', 'fixed-B'}
    assert assessments['additionalProperties'] is False
    for key, definition in assessments['properties'].items():
        assert definition['properties']['candidate_id']['enum'] == [key]
    reply = bound_reply({'candidates':choices}, 'pass')
    keyed = {'assessments':{a['candidate_id']:a for a in reply['assessments']}}
    validator = Draft202012Validator(schema)
    assert validator.is_valid(keyed)
    missing = copy.deepcopy(keyed)
    del missing['assessments']['fixed-B']
    assert not validator.is_valid(missing)
    duplicate = copy.deepcopy(keyed)
    duplicate['assessments']['fixed-B'] = duplicate['assessments']['fixed-A']
    assert not validator.is_valid(duplicate)
    assert CandidateBatch.parse_reply(json.dumps(keyed)).model_dump() == reply
    keyed['assessments']['fixed-A']['candidate_id'] = 'fixed-B'
    with pytest.raises(ValueError):
        CandidateBatch.parse_reply(json.dumps(keyed))


def test_missing_candidate_correction_names_the_missing_id(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-test')
    seen = []
    def handler(request):
        body=json.loads(request.content);ctx=json.loads(body['input'][0]['content'][0]['text'])
        obj=bound_reply(ctx,'pass');seen.append(body)
        if len(seen)==1:
            assert len(obj['assessments']) == 3
            return response({'assessments':obj['assessments'][:1]})
        correction=body['input'][-1]['content']
        assert ctx['candidates'][1]['candidate_id'] in correction
        assert ctx['candidates'][2]['candidate_id'] in correction
        return response(obj)
    store=Store(tmp_path/'db');runner=Runner(ROOT,store,httpx.Client(transport=httpx.MockTransport(handler)))
    r=runner.create(RunConfig(symbols=['AAPL'],start='2024-12-19',end='2024-12-23',mode='live',
                             approved=True,paid_authorized=True,use_images=False,review_enabled=False))
    runner.execute(r['id'])
    assert store.get(r['id'])['status']=='completed'
    assert len(seen)==2


def legacy_context(*args, **kwargs):
    from lab.prompts import make_context
    from lab.contracts import CandidateBatch
    ctx = make_context(*args, **kwargs)
    ctx['schema'] = CandidateBatch.model_json_schema()
    return ctx


@pytest.mark.parametrize('recover_passes', [True, False])
def test_explicit_recovery_preserves_checkpoint_and_receipts_and_is_bounded(tmp_path, monkeypatch, recover_passes):
    from lab.store import fingerprint
    import lab.runner as runner_module
    real_context = runner_module.make_context
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-test')
    monkeypatch.setattr(runner_module, 'make_context', legacy_context)
    calls = []
    def handler(request):
        body=json.loads(request.content);ctx=json.loads(body['input'][0]['content'][0]['text'])
        calls.append(body)
        obj=bound_reply(ctx,'pass')
        keyed = body['text']['format']['schema']['properties']['assessments']['type']=='object'
        if keyed and recover_passes:
            return response({'assessments':{a['candidate_id']:a for a in obj['assessments']}})
        return response({'assessments':obj['assessments'][:1]})
    store=Store(tmp_path/'db');runner=Runner(ROOT,store,httpx.Client(transport=httpx.MockTransport(handler)))
    cfg=RunConfig(symbols=['AAPL'],start='2024-12-19',end='2024-12-23',mode='live',
                  approved=True,paid_authorized=True,use_images=False,review_enabled=False)
    run=runner.create(cfg);runner.execute(run['id']);rid=run['id']
    paused=store.get(rid);assert paused['status']=='paused'
    original=store.requests(rid);assert len(original)==2
    original_hash=fingerprint(original);checkpoint=copy.deepcopy(paused['state'])
    assert checkpoint['day']==1
    node=original[-1]['node']
    monkeypatch.setattr(runner_module,'make_context',real_context)
    runner.execute(rid)  # Without recovery authorization, no new charge.
    assert len(calls)==2
    assert store.get(rid)['state']==checkpoint
    auth=store.authorize_output_recovery(rid,node)
    assert store.authorize_output_recovery(rid,node)==auth
    assert store.get(rid)['config']==paused['config']
    runner.execute(rid)
    assert fingerprint([r for r in store.requests(rid) if r['node']==node])==original_hash
    result=store.get(rid)
    assert result['state']['account']['curve'][:1]==checkpoint['account']['curve']
    if recover_passes:
        assert result['status']=='completed',result['reason']
        assert len(calls)==3
        replay=runner.replay(rid);runner.execute(replay['id'])
        assert store.get(replay['id'])['state']==result['state']
        assert len(calls)==3
    else:
        assert result['status']=='paused'
        assert len(calls)==4  # One normal answer + one repair; no tool call.
        store.authorize_output_recovery(rid,node)
        runner.execute(rid)
        assert len(calls)==4


def test_recovery_cannot_authorize_unknown_billing(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','offline-test')
    def handler(request):
        raise httpx.ReadTimeout('offline-timeout')
    store=Store(tmp_path/'db');runner=Runner(ROOT,store,httpx.Client(transport=httpx.MockTransport(handler)))
    run=runner.create(RunConfig(symbols=['QQQ'],start='2024-11-05',end='2024-11-08',mode='live',approved=True,paid_authorized=True,use_images=False))
    runner.execute(run['id'])
    with pytest.raises(ValueError,match='incomplete-output'):
        store.authorize_output_recovery(run['id'],store.requests(run['id'])[0]['node'])


def test_affordable_alternative_is_not_pruned_by_first_candidate_sizing(tmp_path, monkeypatch):
    import lab.runner as module
    original_shortlist=module.shortlist
    def choices(bars,i,strategy,symbol):
        candidates=original_shortlist(bars,i,strategy,symbol)
        if candidates:
            base=candidates[0]
            return [dict(base,candidate_id='unaffordable',stop=1),
                    dict(base,candidate_id='affordable',stop=bars[i].close-1)]
        return candidates
    monkeypatch.setattr(module,'shortlist',choices)
    monkeypatch.setenv('OPENAI_API_KEY','offline-test')
    def handler(request):
        ctx=json.loads(json.loads(request.content)['input'][0]['content'][0]['text'])
        assert [c['candidate_id'] for c in ctx['candidates']]==['unaffordable','affordable']
        obj=bound_reply(ctx,'fail')
        obj['assessments'][1]=bound_reply({'candidates':[ctx['candidates'][1]]},'pass')['assessments'][0]
        return response(obj)
    store=Store(tmp_path/'db');runner=Runner(ROOT,store,httpx.Client(transport=httpx.MockTransport(handler)))
    cfg=RunConfig(symbols=['QQQ'],start='2024-11-05',end='2024-11-08',capital=1000,
                  strategy=Strategy(risk_fraction=.01,max_weight=1,entry_gap_limit=0,commission=0),
                  mode='live',approved=True,paid_authorized=True,use_images=False,review_enabled=False)
    run=runner.create(cfg);runner.execute(run['id']);done=store.get(run['id'])
    assert done['status']=='completed'
    assert done['summary']['requests']==1
    assert done['state']['account']['orders'][0]['candidate_id']=='affordable'


def test_recovery_does_not_reset_request_budget(tmp_path, monkeypatch):
    import lab.runner as module
    monkeypatch.setattr(module,'make_context',legacy_context)
    monkeypatch.setenv('OPENAI_API_KEY','offline-test')
    calls=[]
    def handler(request):
        calls.append(1)
        ctx=json.loads(json.loads(request.content)['input'][0]['content'][0]['text'])
        return response({'assessments':bound_reply(ctx,'pass')['assessments'][:1]})
    store=Store(tmp_path/'db');runner=Runner(ROOT,store,httpx.Client(transport=httpx.MockTransport(handler)))
    cfg=RunConfig(symbols=['AAPL'],start='2024-12-19',end='2024-12-23',mode='live',approved=True,
                  paid_authorized=True,use_images=False,review_enabled=False,max_requests=2)
    run=runner.create(cfg);runner.execute(run['id']);rid=run['id']
    store.authorize_output_recovery(rid,store.requests(rid)[-1]['node'])
    runner.execute(rid)
    assert len(calls)==2
    assert 'budget exhausted' in store.get(rid)['reason']


@pytest.mark.parametrize('provider',['openai','anthropic','gemini','deepseek','qwen','kimi','glm','doubao'])
def test_legacy_receipt_replays_for_every_provider_without_relaxing_hash_checks(tmp_path, provider):
    from lab.contracts import CandidateBatch
    from lab.providers import Adapter
    from lab.runner import ENGINE_VERSION, Paused
    from lab.store import fingerprint
    cfg, bars, ctx=sample_context()
    cfg=cfg.model_copy(update=dict(mode='live',approved=True,paid_authorized=True,
                                  provider=provider,model='offline-model',use_images=False))
    legacy=dict(ctx,schema=CandidateBatch.model_json_schema())
    url,body=Adapter(provider).build(cfg,legacy,[])
    text=json.dumps(bound_reply({'candidates':ctx['candidates']},'pass'))
    if provider=='openai':
        raw={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}
    elif provider=='anthropic':
        raw={'stop_reason':'end_turn','content':[{'type':'text','text':text}]}
    elif provider=='gemini':
        raw={'candidates':[{'finishReason':'STOP','content':{'role':'model','parts':[{'text':text}]}}]}
    else:
        raw={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':text}}]}
    store=Store(tmp_path/'db');run=store.create(cfg.model_dump(),{},'offline-fixture')
    node='2024-11-06:QQQ:primary';key=run['id']+':'+node+':0'
    store.begin_request(run['id'],node,key,fingerprint(dict(url=url,payload=body,engine=ENGINE_VERSION)),0,
                        dict(url=url,body=body))
    store.save_response(key,raw,{'input':100,'output':50},0)
    original=store.requests(run['id'])
    def forbidden(request):pytest.fail('Archived judgment must not be requested again')
    runner=Runner(ROOT,store,httpx.Client(transport=httpx.MockTransport(forbidden)))
    result=runner.judge(run['id'],node,cfg,ctx,bars,'QQQ')
    assert result.assessments[0].verdict=='pass'
    assert store.requests(run['id'])==original
    with pytest.raises(Paused,match='differs'):
        runner.judge(run['id'],node,cfg,dict(ctx,text=ctx['text']+' '),bars,'QQQ')
