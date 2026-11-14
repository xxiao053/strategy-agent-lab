import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from lab.api import create_app

ROOT = Path(__file__).resolve().parents[1]
HEAD = {'X-Lab-Request': '1'}

@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(ROOT, tmp_path/'execution.sqlite3'), base_url='http://127.0.0.1')

def test_new_projects_are_persistent_and_do_not_reset_each_other(client):
    a = client.post('/api/workspace/projects', headers=HEAD, json={'title':'Alpha','locale':'en'}).json()
    b = client.post('/api/workspace/projects', headers=HEAD, json={'title':'Beta','locale':'zh-CN'}).json()
    assert a['id'] != b['id']
    assert a['messages'][0]['role'] == 'assistant'
    assert 'example' in a['messages'][0]['text'].lower()
    assert len(client.get('/api/workspace/projects').json()) == 2
    assert client.get('/api/workspace/projects/'+a['id']).json()['title'] == 'Alpha'

def test_saved_demo_is_available_without_private_database_or_keys(client):
    demo = client.get('/api/workspace/demo').json()
    assert demo['result']['summary']['buy_fills'] == 32
    assert len(demo['result']['curve']) > 700
    assert 'config' in demo

def test_credentials_are_explicit_and_never_returned(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-private-key-123456')
    assert client.get('/api/workspace/connections').json() == []
    r = client.post('/api/workspace/connections', headers=HEAD, json={
        'name':'My model','provider':'openai','model':'gpt-6-luna',
        'use_environment':True,'input_price':.1,'output_price':.5})
    assert r.status_code == 200, r.text
    assert r.json()['configured'] is True
    assert 'test-private-key' not in json.dumps(client.get('/api/workspace/connections').json())
    assert client.get('/api/workspace/connections').json()[0]['model'] == 'gpt-6-luna'

def test_bad_connection_and_unknown_project_fail_closed(client):
    r = client.post('/api/workspace/connections', headers=HEAD,json={
        'name':'bad','provider':'missing','model':'x','key':'secret-do-not-echo'})
    assert r.status_code == 400
    assert 'secret-do-not-echo' not in r.text
    assert client.get('/api/workspace/projects/../../secrets').status_code != 200

def test_chat_requires_own_connection_and_authorization(client):
    p=client.post('/api/workspace/projects',headers=HEAD,json={'title':'x'}).json()
    r=client.post(f"/api/workspace/projects/{p['id']}/messages",headers=HEAD,json={
        'text':'Please help','connection_id':'missing','authorized':False,'budget':1})
    assert r.status_code == 400
    assert len(client.get(f"/api/workspace/projects/{p['id']}").json()['messages']) == 1

def test_real_adapter_draft_approval_and_bounded_budget(client, monkeypatch):
    import httpx
    from lab.providers import Adapter
    request_bodies=[]
    def transport(request):
        data=json.loads(request.content)
        request_bodies.append(data)
        assert data['model']=='chosen-model'
        assert data['text']['format']['name']=='method_draft'
        assert 'reasoning' not in data
        context=json.loads(data['input'][0]['content'][0]['text'])
        assert context['new_message']['id'] and context['new_message']['text']=='I trade US equities'
        reply={'message':'What should trigger an exit?', 'scope':'US equities',
               'rules':[{'topic':'Market','rule':'US equities','source':'user message'}],
               'questions':[{'question':'Exit rule?','blocking':True}]}
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[
            {'type':'output_text','text':json.dumps(reply)}]}], 'usage':{'input_tokens':500,'output_tokens':100}})
    original=Adapter.__init__
    monkeypatch.setattr(Adapter,'__init__',lambda self,provider:original(self,provider,httpx.Client(transport=httpx.MockTransport(transport))))
    c=client.post('/api/workspace/connections',headers=HEAD,json={'name':'custom','provider':'openai',
        'model':'chosen-model','key':'test-private-key','input_price':1,'output_price':3}).json()
    p=client.post('/api/workspace/projects',headers=HEAD,json={'title':'Fresh'}).json()
    payload={'text':'I trade US equities','connection_id':c['id'],'authorized':True,'budget':1}
    p=client.post(f"/api/workspace/projects/{p['id']}/messages",headers=HEAD,json=payload).json()
    assert p['revision']==1 and p['records'][0]['status']=='completed'
    assert p['records'][0]['committed_cost']==pytest.approx(.0008)
    assert p['records'][0]['usage_cost']==pytest.approx(.0008) and p['records'][0]['billed_cost'] is None
    assert p['messages'][-1]['text']=='What should trigger an exit?'
    assert client.post(f"/api/workspace/projects/{p['id']}/approve",headers=HEAD,json={'revision':1}).status_code==400
    payload['budget']=.0001
    assert client.post(f"/api/workspace/projects/{p['id']}/messages",headers=HEAD,json=payload).status_code==400
    assert len(request_bodies)==1

def test_approval_versions_and_stale_request(tmp_path):
    from lab.workspace_store import WorkspaceStore
    s=WorkspaceStore(tmp_path/'p.sqlite3');p=s.create('a','en')
    def draft(p):
        p['draft']={'scope':'daily','rules':[{'topic':'entry','rule':'user rule','source':'m1'}],'questions':[]}
        p['revision']=1
    s.mutate(p['id'],draft)
    with pytest.raises(ValueError): s.approve(p['id'],0)
    first=s.approve(p['id'],1)
    s.mutate(p['id'],lambda p:p.update(revision=2,draft={**p['draft'],'scope':'revised'}))
    second=s.approve(p['id'],2)
    assert len(second['versions'])==2
    assert second['versions'][0]['method']==first['versions'][0]['method']
    assert WorkspaceStore(s.path).get(p['id'])['versions']==second['versions']

def test_unknown_billing_preserves_reservation_without_retry(client,monkeypatch):
    from lab.providers import Adapter,ProviderError
    calls=[]
    def fail(*a,**kw): calls.append(1);raise ProviderError('Transport failed',ambiguous=True)
    monkeypatch.setattr(Adapter,'send',fail)
    c=client.post('/api/workspace/connections',headers=HEAD,json={'name':'custom','provider':'openai',
        'model':'chosen-model','key':'test-private-key','input_price':1,'output_price':3}).json()
    p=client.post('/api/workspace/projects',headers=HEAD,json={'title':'Failure'}).json()
    p=client.post(f"/api/workspace/projects/{p['id']}/messages",headers=HEAD,json={
        'text':'hello','connection_id':c['id'],'authorized':True,'budget':1}).json()
    assert len(calls)==1 and p['records'][0]['status']=='unknown'
    assert p['records'][0]['committed_cost']>0 and p['busy'] is False

def test_protected_secret_survives_restart_but_is_not_plaintext(tmp_path):
    import os
    if os.name!='nt':pytest.skip('Windows credential protection')
    from lab.workspace_store import WorkspaceStore
    from lab.connections import Connections
    s=WorkspaceStore(tmp_path/'s.sqlite3');c=Connections(s)
    cfg=c.create({'name':'x','provider':'openai','model':'m','key':'private-secret-value',
        'input_price':1,'output_price':3,'remember':True})
    assert Connections(s).get(cfg['id'])[1]=='private-secret-value'
    assert b'private-secret-value' not in s.path.read_bytes()


def test_catalog_check_is_metadata_only_and_does_not_claim_inference(client,monkeypatch):
    import httpx
    def transport(request):
        assert request.method=='GET' and str(request.url)=='https://api.openai.com/v1/models'
        assert request.headers['authorization']=='Bearer private-test-key'
        return httpx.Response(200,json={'data':[{'id':'chosen-model'},{'id':'another-model'}]})
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(transport),**kw))
    c=client.post('/api/workspace/connections',headers=HEAD,json={'name':'x','provider':'openai',
        'model':'chosen-model','key':'private-test-key','input_price':1,'output_price':3}).json()
    r=client.post(f"/api/workspace/connections/{c['id']}/check",headers=HEAD,json={})
    assert r.status_code==200
    assert r.json()=={'models':['another-model','chosen-model'],'selected_listed':True,'status':'catalog_available'}
    assert client.get('/api/workspace/connections').json()[0]['verification']=='not_tested'
    saved=client.get('/api/workspace/connections').json()[0]
    assert saved['catalog_status']=='catalog_available' and saved['selected_listed'] is True
    assert saved.get('construction')!='code_construction_observed'


@pytest.mark.parametrize('path,body',[
    ('projects',{'title':42}),
    ('connections',{'name':42,'provider':'openai','model':'x'}),
    ('connections',{'name':'x','provider':[],'model':'x'}),
    ('connections',{'name':'x','provider':'openai','model':False}),
])
def test_malformed_settings_return_validation_not_server_errors(client,path,body):
    assert client.post('/api/workspace/'+path,headers=HEAD,json=body).status_code==400


def test_build_without_approved_method_is_rejected_before_runtime(client):
    p=client.post('/api/workspace/projects',headers=HEAD,json={'title':'Not approved'}).json()
    response=client.post(f"/api/workspace/projects/{p['id']}/build",headers=HEAD,json={'authorized':True,'budget':2,'version':1})
    assert response.status_code==400 and 'version' in response.json()['detail']


def test_restart_marks_build_interrupted_and_keeps_budget(tmp_path):
    from lab.workspace_store import WorkspaceStore
    s=WorkspaceStore(tmp_path/'x.sqlite3');p=s.create('x','en')
    s.mutate(p['id'],lambda p:p.update(busy=True,builds=[{'id':'b','status':'running'}],
        records=[{'status':'running','committed_cost':.1}]))
    p=WorkspaceStore(s.path).get(p['id'])
    assert p['builds'][0]['status']=='interrupted'
    assert p['records'][0]['committed_cost']==.1 and not p['busy']


def test_validation_error_never_echoes_submitted_credentials(client):
    r=client.post('/api/workspace/connections',headers=HEAD,json=[{'key':'secret-validation-canary'}])
    assert r.status_code==422
    assert 'secret-validation-canary' not in r.text


def connection(client, model='chosen-model'):
    return client.post('/api/workspace/connections',headers=HEAD,json={'name':model,'provider':'openai',
        'model':model,'key':'private-test-key','input_price':1,'output_price':3}).json()


def test_catalog_before_save_needs_only_provider_credentials(client,monkeypatch):
    import httpx
    def transport(request):
        assert request.method=='GET' and request.url.path=='/v1/models'
        return httpx.Response(200,json={'data':[{'id':'chosen-model'},{'id':'private-test-key'}, {'id':'bad id'}, {'id':'x'*101}]})
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(transport),**kw))
    r=client.post('/api/workspace/connections/catalog',headers=HEAD,json={'provider':'openai','key':'private-test-key'})
    assert r.status_code==200
    assert r.json()=={'models':['chosen-model'],'status':'catalog_available'}
    assert client.get('/api/workspace/connections').json()==[]
    assert client.get('/api/workspace/projects').json()==[]


@pytest.mark.parametrize('response', ['not-json', {'data':'private-test-key'}, {'data':[{'id':'x'*1000000}]}])
def test_catalog_malformed_provider_data_is_bounded_and_secret_free(client,monkeypatch,response):
    import httpx
    original=httpx.Client
    def transport(request):
        return httpx.Response(200,text=response) if isinstance(response,str) else httpx.Response(200,json=response)
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(transport),**kw))
    r=client.post('/api/workspace/connections/catalog',headers=HEAD,json={'provider':'openai','key':'private-test-key'})
    assert r.status_code==400
    assert len(r.text)<300 and 'private-test-key' not in r.text
    assert connection(client)['configured'] is True  # Manual save remains available.


def test_project_model_roles_are_independent_validated_and_survive_restart(client,tmp_path):
    a=client.post('/api/workspace/projects',headers=HEAD,json={'title':'Alpha'}).json()
    b=client.post('/api/workspace/projects',headers=HEAD,json={'title':'Beta'}).json()
    c=connection(client); d=connection(client,'another-model')
    assert a['model_roles']=={'builder':None,'execution':None}
    url=f"/api/workspace/projects/{a['id']}/models"
    r=client.post(url,headers=HEAD,json={'builder':c['id'],'execution':d['id']})
    assert r.status_code==200 and r.json()['model_roles']=={'builder':c['id'],'execution':d['id']}
    assert client.get(f"/api/workspace/projects/{b['id']}").json()['model_roles']=={'builder':None,'execution':None}
    for body in [{'builder':'missing','execution':None},{'builder':[], 'execution':None},{'builder':None},
                 {'builder':c['id'],'execution':None,'key':'not-allowed'}]:
        assert client.post(url,headers=HEAD,json=body).status_code==400
    assert client.post(url,headers=HEAD,json={'builder':c['id'],'execution':c['id']}).status_code==200
    assert client.post(url,headers=HEAD,json={'builder':c['id'],'execution':None}).json()['model_roles']['execution'] is None
    client.delete(f"/api/workspace/connections/{c['id']}",headers=HEAD)
    assert client.get(f"/api/workspace/projects/{a['id']}").json()['model_roles']['builder']==c['id']
    assert client.post(url,headers=HEAD,json={'builder':c['id'],'execution':None}).status_code==400


def test_old_projects_migrate_unset_and_busy_or_unconfigured_roles_reject(tmp_path):
    from lab.workspace_store import WorkspaceStore
    from lab.connections import Connections
    s=WorkspaceStore(tmp_path/'roles.sqlite3');p=s.create('old','en')
    with s.connect() as db:
        old=dict(p);old.pop('model_roles',None)
        db.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(old),p['id']))
    assert s.get(p['id'])['model_roles']=={'builder':None,'execution':None}
    c=Connections(s);cfg=c.create({'name':'x','provider':'openai','model':'m','key':'private-test-key','input_price':1,'output_price':3})
    s.mutate(p['id'],lambda p:p.update(busy=True))
    with pytest.raises(ValueError,match='active'):
        c.assign_roles(p['id'],{'builder':cfg['id'],'execution':None})
    s.mutate(p['id'],lambda p:p.update(busy=False))
    c.session.clear()
    with pytest.raises(ValueError,match='key'):
        c.assign_roles(p['id'],{'builder':cfg['id'],'execution':None})


def test_roles_persist_without_modifying_historical_records(tmp_path):
    from lab.workspace_store import WorkspaceStore
    from lab.connections import Connections
    s=WorkspaceStore(tmp_path/'persist.sqlite3');p=s.create('Preserved','en');c=Connections(s)
    cfg=c.create({'name':'x','provider':'openai','model':'m','key':'private-test-key','input_price':1,'output_price':3})
    original={'id':'historic','model':'old','committed_cost':.32,'status':'completed'}
    s.mutate(p['id'],lambda p:p.update(records=[original]))
    c.assign_roles(p['id'],{'builder':cfg['id'],'execution':cfg['id']})
    loaded=WorkspaceStore(s.path).get(p['id'])
    assert loaded['model_roles']=={'builder':cfg['id'],'execution':cfg['id']}
    assert loaded['records']==[original] and len(loaded['messages'])==1


@pytest.mark.parametrize('provider,payload,expected',[
    ('anthropic',{'data':[{'id':'claude-test'}]},['claude-test']),
    ('gemini',{'models':[{'name':'models/gemini-test'}]},['gemini-test']),
    ('deepseek',{'data':[{'id':'deepseek-test'}]},['deepseek-test']),
])
def test_presave_catalog_provider_headers_and_environment_are_explicit(client,monkeypatch,provider,payload,expected):
    import httpx
    from lab.providers import PROVIDERS
    monkeypatch.setenv(PROVIDERS[provider]['env'],'private-test-key')
    def transport(request):
        header={'anthropic':'x-api-key','gemini':'x-goog-api-key'}.get(provider,'authorization')
        assert request.headers[header]==('Bearer private-test-key' if header=='authorization' else 'private-test-key')
        assert request.method=='GET' and request.url.path.endswith('/models')
        return httpx.Response(200,json=payload)
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(transport),**kw))
    url='/api/workspace/connections/catalog'
    assert client.post(url,headers=HEAD,json={'provider':provider}).status_code==400
    assert client.post(url,headers=HEAD,json={'provider':provider,'use_environment':True}).json()['models']==expected


@pytest.mark.parametrize('failure',['http','transport'])
def test_catalog_failures_never_reflect_provider_body_or_key(client,monkeypatch,failure):
    import httpx
    def transport(request):
        if failure=='transport':raise httpx.ConnectError('private-test-key upstream secret',request=request)
        return httpx.Response(401,text='private-test-key upstream secret')
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(transport),**kw))
    r=client.post('/api/workspace/connections/catalog',headers=HEAD,json={'provider':'openai','key':'private-test-key'})
    assert r.status_code==400 and 'private-test-key' not in r.text and 'upstream secret' not in r.text


def test_catalog_rejects_unsafe_endpoint_without_forwarding_credentials(client,monkeypatch):
    monkeypatch.setenv('OPENAI_BASE_URL','http://untrusted.example/private-test-key')
    r=client.post('/api/workspace/connections/catalog',headers=HEAD,json={'provider':'openai','key':'private-test-key'})
    assert r.status_code==400 and 'private-test-key' not in r.text and 'untrusted.example' not in r.text


def test_role_change_during_chat_preparation_blocks_before_inference(tmp_path,monkeypatch):
    from lab.workspace_store import WorkspaceStore
    from lab.connections import Connections
    from lab.workspace_agent import WorkspaceAgent
    from lab.providers import Adapter
    s=WorkspaceStore(tmp_path/'race.sqlite3');c=Connections(s);p=s.create('Race','en')
    cfg=c.create({'name':'x','provider':'openai','model':'m','key':'private-test-key','input_price':1,'output_price':3})
    c.assign_roles(p['id'],{'builder':cfg['id'],'execution':None})
    original=Adapter.build
    def build(self,*args,**kwargs):
        c.assign_roles(p['id'],{'builder':None,'execution':None})
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Adapter,'build',build)
    with pytest.raises(ValueError,match='changed'):
        WorkspaceAgent(s,c).message(p['id'],{'text':'hello','budget':1,'authorized':True})
    assert s.get(p['id'])['records']==[] and s.get(p['id'])['busy'] is False


def test_bound_builder_cannot_be_overridden_or_fall_back_after_deletion(client,monkeypatch):
    from lab.providers import Adapter,ProviderError
    seen=[]
    def fail(self,config,*args,**kw):
        seen.append(config.model);raise ProviderError('Offline fixture')
    monkeypatch.setattr(Adapter,'send',fail)
    c=connection(client);other=connection(client,'other')
    p=client.post('/api/workspace/projects',headers=HEAD,json={'title':'Bound'}).json()
    url=f"/api/workspace/projects/{p['id']}"
    assert client.post(url+'/models',headers=HEAD,json={'builder':c['id'],'execution':other['id']}).status_code==200
    payload={'text':'hello','authorized':True,'budget':1}
    assert client.post(url+'/messages',headers=HEAD,json={**payload,'connection_id':other['id']}).status_code==400
    r=client.post(url+'/messages',headers=HEAD,json=payload)
    assert r.status_code==200 and seen==['chosen-model']
    assert r.json()['records'][0]['role']=='builder' and r.json()['records'][0]['connection_id']==c['id']
    client.delete('/api/workspace/connections/'+c['id'],headers=HEAD)
    assert client.post(url+'/messages',headers=HEAD,json={**payload,'connection_id':other['id']}).status_code==400
    assert seen==['chosen-model']
