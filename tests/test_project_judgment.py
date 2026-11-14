import json
import httpx
import pytest
from lab.connections import Connections
from lab.workspace_store import WorkspaceStore
from lab.providers import Adapter
from tests.test_project_execution import manifest, proposal, bars


def setup(tmp_path,monkeypatch,transport):
    from lab.project_judgment import BoundedJudgment
    from lab.execution_contract import Manifest
    store=WorkspaceStore(tmp_path/'workspace.sqlite3');pid=store.create('Method','en')['id'];connections=Connections(store)
    cfg=connections.create({'name':'execution','provider':'openai','model':'explicit-execution',
                            'key':'private-offline-key','input_price':1,'output_price':2})
    connections.assign_roles(pid,{'builder':None,'execution':cfg['id']})
    store.mutate(pid,lambda p:p.update(busy=True))
    original=Adapter.__init__
    monkeypatch.setattr(Adapter,'__init__',lambda self,provider:original(self,provider,httpx.Client(transport=httpx.MockTransport(transport))))
    judge=BoundedJudgment(store,connections,pid,'run1',Manifest.model_validate(manifest(True)),cfg,'private-offline-key',2)
    context={'cutoff':'2024-01-03','bars':{'SPY':[b.model_dump() for b in bars()['SPY'][:2]]},'account':{'cash':100,'positions':{}},'state':{}}
    return store,pid,judge,context


def response(verdict='pass',evidence=None):
    value={'verdict':verdict,'reason':'The supplied bars support this judgment.',
           'evidence':evidence if evidence is not None else [{'symbol':'SPY','date':'2024-01-03'}]}
    return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}],
            'usage':{'input_tokens':100,'output_tokens':50}}


@pytest.mark.parametrize('verdict',['pass','fail','insufficient_evidence'])
def test_judgments_are_distinct_saved_and_charged_to_execution_role(tmp_path,monkeypatch,verdict):
    def transport(request):
        body=json.loads(request.content)
        assert body['model']=='explicit-execution' and body['max_output_tokens']==1500
        assert [t['name'] for t in body['tools']]==['read_bars','price_facts']
        return httpx.Response(200,json=response(verdict))
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport)
    result=judge({'id':'d1'},context,proposal(judgment='Apply approved criteria'))
    assert result['verdict']==verdict and len(result['request_ids'])==1
    record=store.get(pid)['records'][0]
    assert record['role']=='execution' and record['run_id']=='run1' and record['decision_id']=='d1'
    assert record['status']=='completed' and record['committed_cost']==pytest.approx(.0002)
    assert record['usage_cost']==pytest.approx(.0002) and record['billed_cost'] is None
    assert (tmp_path/'workspace-receipts'/f"{record['id']}.json").exists()
    assert 'private-offline-key' not in json.dumps(store.get(pid))


@pytest.mark.parametrize('bad',[{'verdict':'maybe'},None,'future'])
def test_invalid_verdict_or_missing_evidence_is_not_rejection(tmp_path,monkeypatch,bad):
    raw=response(evidence=[] if bad is None else [{'symbol':'SPY','date':'2025-01-03'}])
    if isinstance(bad,dict):raw['output'][0]['content'][0]['text']=json.dumps(bad)
    store,pid,judge,context=setup(tmp_path,monkeypatch,lambda req:httpx.Response(200,json=raw))
    with pytest.raises(ValueError,match='invalid_response|missing_evidence'):
        judge({'id':'d1'},context,proposal(judgment='assess'))
    record=store.get(pid)['records'][0]
    assert record['status']=='invalid_response' and record['committed_cost']>0
    assert (tmp_path/'workspace-receipts'/f"{record['id']}.json").exists()


def test_unknown_transport_retains_reservation_without_retry(tmp_path,monkeypatch):
    calls=[]
    def transport(req):calls.append(req);raise httpx.ReadTimeout('contains private transport details')
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport)
    with pytest.raises(ValueError,match='infrastructure_failure'):judge({'id':'d'},context,proposal(judgment='assess'))
    record=store.get(pid)['records'][0]
    assert len(calls)==1 and record['status']=='unknown' and record['committed_cost']==record['reserved_cost']
    assert 'private transport' not in record['error']


@pytest.mark.parametrize('name,end',[('shell','2024-01-03'),('read_bars','2024-01-04')])
def test_forbidden_tools_and_future_dates_stop_without_followup(tmp_path,monkeypatch,name,end):
    calls=[]
    def transport(req):
        calls.append(req)
        return httpx.Response(200,json={'status':'completed','output':[{'type':'function_call','call_id':'c1','name':name,
               'arguments':json.dumps({'symbol':'SPY','start_date':'2024-01-02','end_date':end})}],
               'usage':{'input_tokens':100,'output_tokens':50}})
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport)
    with pytest.raises(ValueError,match='invalid_response'):judge({'id':'d'},context,proposal(judgment='assess'))
    assert len(calls)==1


def test_tool_round_is_cutoff_limited_and_second_tool_request_cannot_loop(tmp_path,monkeypatch):
    calls=[]
    def transport(req):
        body=json.loads(req.content);calls.append(body)
        if len(calls)==2:
            assert 'tools' not in body
            result=json.loads(body['input'][-1]['output'])
            assert [b['date'] for b in result['bars']]==['2024-01-02','2024-01-03']
        return httpx.Response(200,json={'status':'completed','output':[{'type':'function_call','call_id':'c1','name':'read_bars',
               'arguments':json.dumps({'symbol':'SPY','start_date':'2024-01-02','end_date':'2024-01-03'})}],
               'usage':{'input_tokens':100,'output_tokens':50}})
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport)
    with pytest.raises(ValueError,match='invalid_response'):judge({'id':'d'},context,proposal(judgment='assess'))
    assert len(calls)==2 and len(store.get(pid)['records'])==2


def test_budget_and_changed_role_block_before_provider_request(tmp_path,monkeypatch):
    def transport(req):pytest.fail('must not call provider')
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport)
    judge.budget=.00001
    with pytest.raises(ValueError,match='budget'):judge({'id':'d'},context,proposal(judgment='assess'))
    assert not store.get(pid)['records']
    judge.budget=2
    store.mutate(pid,lambda p:p['model_roles'].update(execution=None))
    with pytest.raises(ValueError,match='connection|role'):judge({'id':'d'},context,proposal(judgment='assess'))


def test_readonly_facts_and_request_cap_are_enforced(tmp_path,monkeypatch):
    from lab.project_judgment import evidence_tool
    store,pid,judge,context=setup(tmp_path,monkeypatch,lambda req:pytest.fail('request cap must block provider'))
    result=evidence_tool({'name':'price_facts','arguments':{'symbol':'SPY','start_date':'2024-01-02','end_date':'2024-01-03'}},context,['price_facts'])
    assert result=={'symbol':'SPY','start_date':'2024-01-02','end_date':'2024-01-03','first_close':10,'last_close':13,'high':14,'low':9,'average_volume':100}
    judge.calls=1000
    with pytest.raises(ValueError,match='limit'):judge({'id':'d'},context,proposal(judgment='assess'))
    assert store.get(pid)['records']==[]

@pytest.mark.parametrize('input_mode',['text','chart_and_text'])
def test_execution_model_gets_criteria_and_responsibilities_not_an_account_recheck(tmp_path,monkeypatch,input_mode):
    captured=[]
    def transport(req):
        captured.append(json.loads(req.content))
        return httpx.Response(200,json=response())
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport)
    if input_mode=='chart_and_text':
        store.mutate(pid,lambda p:p.update(busy=False))
        judge.cfg=judge.connections.configure_images(judge.cfg['id'],{'enabled':True,'billing_profile':'token-v1'})
        store.mutate(pid,lambda p:p.update(busy=True))
        judge.manifest.judgment.input_mode=input_mode
    judge.manifest.judgment.trigger='Only when exactly 50 shares including fees are affordable.'
    result=judge({'id':'d'},context,proposal(judgment='Assess the approved visual criteria.'))
    assert result['verdict']=='pass'
    payload=captured[0]
    assert judge.manifest.judgment.trigger not in payload['instructions']
    assert payload['instructions'].split('\n',1)[1]==judge.manifest.judgment.criteria
    facts=json.loads(payload['input'][0]['content'][0]['text'])
    assert facts['responsibilities']==judge.manifest.responsibilities.model_dump()
    assert facts['bars']==context['bars'] and facts['cutoff']==context['cutoff']
    assert ('chart_sources' in facts)==(input_mode=='chart_and_text')
    assert any(c['type']=='input_image' for c in payload['input'][0]['content'])==(input_mode=='chart_and_text')
    assert context['account']=={'cash':100,'positions':{}}
