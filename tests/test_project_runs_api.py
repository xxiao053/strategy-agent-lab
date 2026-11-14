import copy
import json
import pytest
from fastapi.testclient import TestClient
from lab.api import create_app
from lab.connections import Connections
from lab.workspace_store import WorkspaceStore
from tests.test_project_execution import manifest,bars,proposal


def prepared(tmp_path):
    from lab.execution_contract import seal_build
    from lab.project_runs import ProjectRuns
    store=WorkspaceStore(tmp_path/'workspace.sqlite3');pid=store.create('One','en')['id'];connections=Connections(store)
    method={'rules':[{'topic':'entry','rule':'buy three shares','source':'m1'}],'questions':[]}
    artifacts=[{'name':'strategy.py','text':'def decide(context): return {"proposals":[],"state":{}}'},
               {'name':'execution.json','text':json.dumps(manifest())},{'name':'method.json','text':json.dumps(method)}]
    build={'id':'build1','version':1,'status':'completed','artifacts':artifacts,'execution_hash':seal_build(artifacts,method)}
    store.mutate(pid,lambda p:p.update(versions=[{'version':1,'method':method}],builds=[build]))
    runs=ProjectRuns(tmp_path,store,connections)
    return store,pid,runs


def body():return {'build_id':'build1','symbols':['SPY'],'start':'2024-01-03','end':'2024-01-05','initial_cash':100,'fee_rate':0}


def test_code_run_needs_no_model_and_durable_results_are_separate_from_project_polling(tmp_path,monkeypatch):
    store,pid,runs=prepared(tmp_path)
    monkeypatch.setattr(runs,'load_market',lambda *args:(bars(),{'SPY':{'receipt':'frozen-fixture'}}))
    class Program:
        def __init__(self,*args):pass
        def decide(self,context):return {'proposals':[proposal()] if context['cutoff']=='2024-01-03' else [],'state':{}}
    monkeypatch.setattr(runs,'evaluator_factory',Program)
    monkeypatch.setattr('lab.project_runs.threading.Thread.start',lambda self:None)
    summary=runs.start(pid,body())
    assert summary['status']=='running' and store.get(pid)['busy']
    runs.execute(pid,summary['id'])
    result=runs.get(pid,summary['id'])
    assert result['status']=='completed' and result['curve'][-1]['equity']==88
    assert result['frozen']['build_hash'] and result['frozen']['market_hash'] and result['frozen']['run_hash']
    assert not store.get(pid)['busy'] and store.get(pid)['records']==[]
    assert 'decisions' not in runs.list(pid)[0] and 'runs' not in store.get(pid)
    with pytest.raises(KeyError):runs.get('another-project',summary['id'])


def test_cancel_and_restart_never_restart_or_erase_run_evidence(tmp_path,monkeypatch):
    from lab.project_runs import ProjectRuns
    store,pid,runs=prepared(tmp_path)
    monkeypatch.setattr(runs,'load_market',lambda *args:(bars(),{}))
    monkeypatch.setattr('lab.project_runs.threading.Thread.start',lambda self:None)
    run=runs.start(pid,body());runs.cancel(pid,run['id']);runs.execute(pid,run['id'])
    assert runs.get(pid,run['id'])['status']=='cancelled'
    run2=runs.start(pid,body())
    restarted=ProjectRuns(tmp_path,store,runs.connections)
    assert restarted.get(pid,run2['id'])['status']=='interrupted'
    assert not store.get(pid)['busy']


def test_bad_build_missing_market_and_model_authority_fail_before_start(tmp_path,monkeypatch):
    store,pid,runs=prepared(tmp_path)
    with pytest.raises(ValueError,match='project'):runs.start(pid,{**body(),'build_id':'foreign-build'})
    with pytest.raises(ValueError):runs.start(pid,body())
    assert not store.get(pid)['busy'] and runs.list(pid)==[]
    for changes in [{'start':'invalid'},{'symbols':['SPY','SPY']},{'initial_cash':float('nan')},{'fee_rate':-1},{'symbols':['BAD']},{'extra':1}]:
        with pytest.raises(ValueError):runs.start(pid,{**body(),**changes})


def test_run_endpoints_reject_foreign_build_and_unknown_run_without_mutation(tmp_path):
    from pathlib import Path
    client=TestClient(create_app(Path(__file__).resolve().parents[1],tmp_path/'execution.sqlite3'),base_url='http://127.0.0.1')
    h={'X-Lab-Request':'1'}
    pid=client.post('/api/workspace/projects',json={'title':'API'},headers=h).json()['id']
    response=client.post(f'/api/workspace/projects/{pid}/runs',json=body(),headers=h)
    assert response.status_code==400
    assert client.get(f'/api/workspace/projects/{pid}/runs').json()==[]
    assert client.get(f'/api/workspace/projects/{pid}/runs/foreign').status_code==404
    assert client.get(f'/api/workspace/projects/{pid}/runs/foreign/status').status_code==404
    assert client.post(f'/api/workspace/projects/{pid}/runs/foreign/cancel',json={},headers=h).status_code==404


def test_model_run_never_falls_back_to_builder_and_requires_saved_role_expectation(tmp_path,monkeypatch):
    from lab.execution_contract import seal_build
    store,pid,runs=prepared(tmp_path)
    def model_build(p):
        b=p['builds'][0];b['artifacts'][1]['text']=json.dumps(manifest(True))
        b['execution_hash']=seal_build(b['artifacts'],p['versions'][0]['method'])
    store.mutate(pid,model_build)
    cfg=runs.connections.create({'name':'builder','provider':'openai','model':'offline',
                                 'key':'private-offline-test','input_price':1,'output_price':1})
    runs.connections.assign_roles(pid,{'builder':cfg['id'],'execution':None})
    monkeypatch.setattr(runs,'load_market',lambda *args:(bars(),{}))
    with pytest.raises(ValueError,match='Authorize'):runs.start(pid,body())
    with pytest.raises(ValueError,match='execution connection'):
        runs.start(pid,{**body(),'authorized':True,'budget':1,'connection_id':cfg['id']})
    runs.connections.assign_roles(pid,{'builder':None,'execution':cfg['id']})
    with pytest.raises(ValueError,match='execution connection'):
        runs.start(pid,{**body(),'authorized':True,'budget':1,'connection_id':'stale'})
    runs.connections.delete(cfg['id'])
    with pytest.raises(ValueError,match='configured'):
        runs.start(pid,{**body(),'authorized':True,'budget':1,'connection_id':cfg['id']})
    assert not store.get(pid)['records'] and not store.get(pid)['busy']


def saved_decision(tmp_path,monkeypatch):
    store,pid,runs=prepared(tmp_path)
    monkeypatch.setattr(runs,'load_market',lambda *args:(bars(),{}))
    monkeypatch.setattr('lab.project_runs.threading.Thread.start',lambda self:None)
    class Program:
        def __init__(self,*args):pass
        def decide(self,c):return {'proposals':[proposal()] if c['cutoff']=='2024-01-03' else [],'state':{'entry_anchor':13}}
    monkeypatch.setattr(runs,'evaluator_factory',Program)
    rid=runs.start(pid,body())['id'];runs.execute(pid,rid)
    return store,pid,runs,rid


def test_builder_receives_trusted_selected_run_context_without_mutating_run(tmp_path,monkeypatch):
    import httpx
    from lab.providers import Adapter
    from lab.workspace_agent import WorkspaceAgent
    store,pid,runs,rid=saved_decision(tmp_path,monkeypatch)
    before=runs.get(pid,rid)
    from lab.execution_contract import digest
    before['inputs']['2024-01-03']['bars']['QQQ']=[{'date':'2024-01-03','open':400,'high':410,'low':390,'close':407,'volume':999}]
    before['decisions'][0]['input_hash']=digest(before['inputs']['2024-01-03'])
    before['decisions'][0]['model']={'verdict':'pass','reason':'QQQ confirms','evidence':[{'symbol':'QQQ','date':'2024-01-03'}],
        'request_ids':['stored-request'],'tools':[{'name':'price_facts','arguments':{'symbol':'QQQ','start_date':'2024-01-03','end_date':'2024-01-03'},'result':{'last_close':407}}]}
    runs.update(pid,rid,inputs=before['inputs'],decisions=before['decisions'])
    before=runs.get(pid,rid)
    cfg=runs.connections.create({'name':'builder','provider':'openai','model':'offline',
                                 'key':'private-offline-key','input_price':1,'output_price':1})
    runs.connections.assign_roles(pid,{'builder':cfg['id'],'execution':None})
    seen=[]
    def transport(request):
        payload=json.loads(request.content);seen.append(json.loads(payload['input'][0]['content'][0]['text']))
        response={'message':'The saved next-open fill was 20, not signal close 13. Shall we change the method?',
                  'scope':'Daily','rules':[],'questions':[]}
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(response)}]}],
                                        'usage':{'input_tokens':100,'output_tokens':50}})
    original=Adapter.__init__
    monkeypatch.setattr(Adapter,'__init__',lambda self,provider:original(self,provider,httpx.Client(transport=httpx.MockTransport(transport))))
    request={'text':'Correct this selected decision','authorized':True,'budget':1,'connection_id':cfg['id'],
             'evidence_ref':{'run_id':rid,'decision_id':'2024-01-03-1'}}
    result=WorkspaceAgent(store,runs.connections).message(pid,request)
    evidence=seen[0]['selected_evidence']
    assert evidence['reference']==request['evidence_ref']
    assert evidence['decision']['proposal']['sizing']=={'shares':3}
    assert evidence['bars']['SPY'][-1]['close']==13 and evidence['orders'][0]['price']==20
    assert evidence['state']=={} and 'def decide' in evidence['code'][0]['text']
    assert evidence['method']['rules'][0]['rule']=='buy three shares'
    assert evidence['manifest']['schema']=='strategy-v1'
    assert evidence['bars']['QQQ'][0]['close']==407
    assert evidence['model']['reason']=='QQQ confirms' and evidence['model_tools'][0]['result']['last_close']==407
    assert result['messages'][-2]['evidence_ref']==request['evidence_ref']
    assert runs.get(pid,rid)==before


def test_evidence_reference_rejects_foreign_or_forged_selection_before_spending(tmp_path,monkeypatch):
    from lab.workspace_agent import WorkspaceAgent
    from lab.providers import Adapter
    monkeypatch.setattr(Adapter,'send',lambda *args,**kwargs:(_ for _ in ()).throw(ValueError('offline test guard: provider must not be reached')))
    store,pid,runs,rid=saved_decision(tmp_path,monkeypatch)
    second=store.create('Other','en')['id']
    cfg=runs.connections.create({'name':'builder','provider':'openai','model':'offline',
                                 'key':'private-offline-key','input_price':1,'output_price':1})
    for target in [pid,second]:runs.connections.assign_roles(target,{'builder':cfg['id'],'execution':None})
    for target,reference in [(second,{'run_id':rid,'decision_id':'2024-01-03-1'}),
                             (pid,{'run_id':rid,'decision_id':'missing'}),
                             (pid,{'run_id':rid,'decision_id':'2024-01-03-1','inputs':{'cash':999}})]:
        with pytest.raises(ValueError,match='evidence|decision|reference'):
            WorkspaceAgent(store,runs.connections).message(target,{'text':'review','authorized':True,'budget':1,'evidence_ref':reference})
        assert not store.get(target)['records']


def test_evidence_resolution_has_explicit_bounded_omissions_and_actual_model_tools(tmp_path,monkeypatch):
    from lab.project_evidence import resolve_evidence
    from lab.execution_contract import canonical
    store,pid,runs,rid=saved_decision(tmp_path,monkeypatch)
    r=runs.get(pid,rid);d=r['decisions'][0]
    d['model']={'verdict':'pass','reason':'QQQ confirms','evidence':[{'symbol':'QQQ','date':'2024-01-03'}],
                'request_ids':['req1'],'tools':[{'name':'price_facts','arguments':{'symbol':'QQQ','start_date':'2024-01-02','end_date':'2024-01-03'},'result':{'first_close':11,'last_close':14}}]}
    # Large saved method/tool/code sections are disclosed as excerpts, never represented as complete.
    r['frozen']['artifacts'][0]['text']='def decide(context): return {"proposals":[],"state":{}}\n'+'# details\n'*15000
    from lab.execution_contract import seal_build,digest
    r['frozen']['build_hash']=seal_build(r['frozen']['artifacts'],r['frozen']['method'])
    r['frozen']['run_hash']=digest({k:v for k,v in r['frozen'].items() if k!='run_hash'})
    runs.update(pid,rid,decisions=r['decisions'],frozen=r['frozen'])
    value=resolve_evidence(store,pid,{'run_id':rid,'decision_id':d['id']})
    assert len(canonical(value).encode())<=80000 and value['omissions']
    assert value['model']['verdict']=='pass' and value['model_tools'][0]['result']['last_close']==14
    assert value['code'][0]['truncated'] is True and 'def decide' in value['code'][0]['text']
