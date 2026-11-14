import json
import os
from pathlib import Path
import httpx
import pytest
from lab.workspace_store import WorkspaceStore
from lab.connections import Connections


def setup_project(tmp_path):
    store=WorkspaceStore(tmp_path/'state.sqlite3')
    p=store.create('Trend','en')
    store.mutate(p['id'],lambda p:p.update(revision=1,draft={'scope':'daily','rules':[{'topic':'entry','rule':'cross SMA20','source':'m1'}],'questions':[]}))
    store.approve(p['id'],1)
    connections=Connections(store)
    c=connections.create({'name':'x','provider':'openai','model':'gpt-6-luna','key':'private-real-test-key','input_price':.1,'output_price':.5})
    return store,connections,p['id'],c


def post_declared_oversize(url,token):
    """Exercise the early Content-Length guard without racing an unread socket body."""
    from http.client import HTTPConnection
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    connection=HTTPConnection(parsed.hostname,parsed.port,timeout=5)
    try:
        connection.putrequest('POST','/responses')
        connection.putheader('Authorization','Bearer '+token)
        connection.putheader('Content-Length',str(2*1024*1024+1))
        connection.endheaders()
        response=connection.getresponse()
        return response.status,json.loads(response.read())
    finally:connection.close()


def test_builder_requires_approval_and_spend_authorization(tmp_path):
    from lab.build_runtime import Builder
    s,c,p,cfg=setup_project(tmp_path)
    b=Builder(s,c)
    with pytest.raises(ValueError,match='Authorize'):
        b.prepare(p,{'connection_id':cfg['id'],'authorized':False,'budget':2,'version':1})
    with pytest.raises(ValueError,match='version'):
        b.prepare(p,{'connection_id':cfg['id'],'authorized':True,'budget':2,'version':2})
    assert s.get(p)['busy'] is False


def test_build_resolves_project_builder_and_rejects_override(tmp_path):
    from lab.build_runtime import Builder
    s,c,p,cfg=setup_project(tmp_path)
    c.assign_roles(p,{'builder':cfg['id'],'execution':None})
    body={'authorized':True,'budget':2,'version':1}
    assert Builder(s,c).prepare(p,body)[2]['id']==cfg['id']
    with pytest.raises(ValueError,match='builder'):
        Builder(s,c).prepare(p,{**body,'connection_id':'another'})
    c.delete(cfg['id'])
    with pytest.raises(ValueError):Builder(s,c).prepare(p,body)


@pytest.mark.parametrize('notes',[123,'x'*8001,'API_KEY=private-credential'],ids=['wrong-type','overlong','credential'])
def test_repair_feedback_is_bounded_and_rejects_credentials_before_build(tmp_path,notes):
    from lab.build_runtime import Builder
    s,c,p,cfg=setup_project(tmp_path)
    with pytest.raises(ValueError,match='repair|Repair|credentials'):
        Builder(s,c).prepare(p,{'authorized':True,'budget':2,'version':1,'connection_id':cfg['id'],'repair_notes':notes})
    assert not s.get(p)['busy'] and not s.get(p).get('builds')


def test_repair_feedback_reaches_coder_without_rewriting_approved_method(tmp_path,monkeypatch):
    from lab.build_runtime import Builder
    s,c,p,cfg=setup_project(tmp_path)
    note='Candidate deduplication loses the stored indices; reproduce two candidates and repair.'
    s.mutate(p,lambda value:value.update(builds=[{'id':'repair','version':1,'repair_notes':note}],busy=True))
    version=s.get(p)['versions'][0];before=json.dumps(version)
    seen=[]
    monkeypatch.setattr('lab.sdk_builder.run_build',lambda builder,pid,bid,v,connection,key,budget,prompt:seen.append((v,prompt)))
    Builder(s,c).run(p,'repair',version,cfg,'unused',1,'docker')
    assert len(seen)==1 and note in seen[0][1]
    assert json.dumps(seen[0][0])==before and json.dumps(s.get(p)['versions'][0])==before


@pytest.mark.skipif(os.name!='nt',reason='Windows MXC start contract')
def test_build_start_snapshots_role_and_rejects_racing_role_change(tmp_path,monkeypatch):
    from lab.build_runtime import Builder
    s,c,p,cfg=setup_project(tmp_path)
    c.assign_roles(p,{'builder':cfg['id'],'execution':None})
    monkeypatch.setattr('lab.build_runtime.shutil.which',lambda _: 'codex')
    monkeypatch.setattr('lab.build_runtime.threading.Thread.start',lambda _:None)
    builder=Builder(s,c);body={'authorized':True,'budget':2,'version':1}
    prepared=builder.prepare
    def race(*args):
        result=prepared(*args);c.assign_roles(p,{'builder':None,'execution':None});return result
    monkeypatch.setattr(builder,'prepare',race)
    with pytest.raises(ValueError,match='changed'):builder.start(p,body)
    c.assign_roles(p,{'builder':cfg['id'],'execution':None})
    monkeypatch.setattr(builder,'prepare',prepared)
    result=builder.start(p,body)
    build=result['builds'][0]
    assert build['role']=='builder' and build['connection_id']==cfg['id'] and build['model']=='gpt-6-luna'
    with pytest.raises(ValueError,match='active'):c.assign_roles(p,{'builder':None,'execution':None})
    with pytest.raises(ValueError,match='active'):c.delete(cfg['id'])
    assert c.list()[0].get('construction')!='code_construction_observed'


@pytest.mark.skipif(os.name!='nt',reason='Windows MXC start contract')
def test_legacy_build_connection_cannot_be_deleted_while_in_use(tmp_path,monkeypatch):
    from lab.build_runtime import Builder
    s,c,p,cfg=setup_project(tmp_path)
    monkeypatch.setattr('lab.build_runtime.shutil.which',lambda _: 'codex')
    monkeypatch.setattr('lab.build_runtime.threading.Thread.start',lambda _:None)
    Builder(s,c).start(p,{'authorized':True,'budget':2,'version':1,'connection_id':cfg['id']})
    with pytest.raises(ValueError,match='active'):c.delete(cfg['id'])


def test_relay_caps_tokens_persists_usage_and_refuses_budget_exhaustion(tmp_path):
    from lab.build_runtime import BudgetRelay
    s,c,p,cfg=setup_project(tmp_path)
    def transport(request):
        body=json.loads(request.content)
        assert request.headers['authorization']=='Bearer private-real-test-key'
        assert body['max_output_tokens']==6000 and body['model']=='gpt-6-luna'
        assert body['store'] is False and body['service_tier']=='default'
        raw={'type':'response.completed','response':{'id':'test','usage':{'input_tokens':1000,'output_tokens':500}}}
        return httpx.Response(200,headers={'Content-Type':'text/event-stream'},text='data: '+json.dumps(raw)+'\n\n')
    with BudgetRelay(s,p,cfg,'private-real-test-key',.02,'build-test',transport=httpx.MockTransport(transport)) as relay:
        with httpx.Client(trust_env=False) as local:
            r=local.post(relay.url+'/responses',headers={'Authorization':'Bearer '+relay.token},json={'model':'gpt-6-luna','input':[],'max_output_tokens':99999})
            assert r.status_code==200 and 'response.completed' in r.text
            assert local.post(relay.url+'/responses',json={'input':[]}).status_code==403
            oversized={'input':['x'*120000]}
            assert local.post(relay.url+'/responses',headers={'Authorization':'Bearer '+relay.token},json=oversized).status_code==402
    records=s.get(p)['records']
    assert len(records)==1 and records[0]['status']=='completed'
    assert records[0]['committed_cost']==pytest.approx(.00035)
    assert records[0]['usage_cost']==pytest.approx(.00035) and records[0]['billed_cost'] is None
    assert 'private-real-test-key' not in json.dumps(s.get(p))


def test_generated_files_cannot_escape_or_forge_method_version(tmp_path):
    from lab.build_runtime import collect_artifacts
    work=tmp_path/'work';work.mkdir()
    (work/'strategy.py').write_text('def signal(): return True')
    (work/'test_strategy.py').write_text('import unittest')
    (work/'result.json').write_text('{"trades":[]}')
    assert {f['name'] for f in collect_artifacts(work)}=={'strategy.py','test_strategy.py','result.json'}
    (work/'huge.py').write_text('x'*300000)
    with pytest.raises(ValueError):collect_artifacts(work)


def test_previous_reference_is_not_recursively_exported(tmp_path):
    from lab.build_runtime import collect_artifacts
    (tmp_path/'strategy.py').write_text('pass')
    (tmp_path/'previous-version.txt').write_text('x'*300000)
    assert [f['name'] for f in collect_artifacts(tmp_path)]==['strategy.py']


def test_skipped_only_suite_is_not_verified(tmp_path):
    import subprocess,sys
    from lab.build_runtime import verify_project
    (tmp_path/'method.json').write_text('{}')
    (tmp_path/'test_strategy.py').write_text('import unittest\nclass Test(unittest.TestCase):\n @unittest.skip("todo")\n def test_rule(self): pass\n')
    (tmp_path/'demo.py').write_text('print("{}")')
    result=verify_project(tmp_path,{},lambda args:subprocess.run(args,cwd=tmp_path,capture_output=True,text=True))
    assert not result['tests_passed']


def test_self_reported_success_never_becomes_independent_test_evidence(tmp_path):
    import subprocess
    from lab.build_runtime import verify_project
    (tmp_path/'method.json').write_text('{}')
    def isolated(args):
        return subprocess.CompletedProcess(args,0,'LAB_TEST_RESULT:{"executed":7,"passed":true}\n','')
    result=verify_project(tmp_path,{},isolated)
    assert result['test_evidence']=='generated_self_report'
    assert result['tests_passed'] is True


@pytest.mark.parametrize('changed',['strategy.py','method.json'])
def test_demo_cannot_mutate_the_verified_deliverable(tmp_path,changed):
    import subprocess
    from lab.build_runtime import verify_project
    (tmp_path/'method.json').write_text('{}')
    (tmp_path/'strategy.py').write_text('x=1')
    (tmp_path/'test_strategy.py').write_text('import unittest\nclass Test(unittest.TestCase):\n def test_rule(self): self.assertEqual(1,1)\n')
    (tmp_path/'demo.py').write_text('from pathlib import Path\nPath('+repr(changed)+').write_text(\'{"changed":true}\');print("{}")')
    with pytest.raises(ValueError,match='changed'):
        verify_project(tmp_path,{},lambda args:subprocess.run(args,cwd=tmp_path,capture_output=True,text=True))


def test_runtime_environment_does_not_inherit_credentials_or_home_configuration(tmp_path,monkeypatch):
    from lab.build_runtime import runtime_environment, runtime_config
    monkeypatch.setenv('OPENAI_API_KEY','do-not-inherit')
    monkeypatch.setenv('SECRET_CUSTOM','do-not-inherit')
    monkeypatch.setattr('lab.build_runtime.shutil.which',lambda _:str(tmp_path/'shell'/'pwsh.exe'))
    env=runtime_environment(tmp_path,'ephemeral-token')
    assert 'OPENAI_API_KEY' not in env and 'SECRET_CUSTOM' not in env
    assert env['CODEX_HOME']==str(tmp_path)
    config=runtime_config('http://127.0.0.1:1234','gpt-6-luna','low')
    import tomllib
    data=tomllib.loads(config)
    assert data['permissions']['builder']['filesystem'][':root']=='deny'
    assert data['permissions']['builder']['network']['enabled'] is False
    assert data['approval_policy']=='never'
    assert data['model_providers']['builder']['request_max_retries']==0
    assert data['project_doc_max_bytes']==0
    assert data['allow_login_shell'] is False
    assert data['permissions']['builder']['filesystem'][str(tmp_path/'shell')]=='read'


def test_native_history_compacts_with_prefix_headroom_and_local_budgeted_protocol():
    import tomllib
    from lab.build_runtime import runtime_config
    data=tomllib.loads(runtime_config('http://127.0.0.1:1','gpt-6-luna','low'))
    # Known Luna capacity is not a small application byte limit. Compact with
    # ample working room, below its long-context billing threshold.
    assert data['model_context_window']==1050000
    assert data['model_auto_compact_token_limit']==200000
    assert data['model_auto_compact_token_limit_scope']=='total'
    assert data['tool_output_token_limit']==6000
    provider=data['model_providers']['builder']
    assert provider['capabilities']['remote_compaction']=='unsupported'
    assert provider['wire_api']=='responses' and provider['request_max_retries']==provider['stream_max_retries']==0


def test_native_unknown_model_does_not_inherit_luna_capacity():
    import tomllib
    from lab.build_runtime import runtime_config
    data=tomllib.loads(runtime_config('http://127.0.0.1:1','custom-model','low'))
    assert data['model_context_window']==32000 and data['model_auto_compact_token_limit']==20000


@pytest.mark.parametrize('case,status,code,detail',[
    ('raw',413,'raw_request_too_large','2097153 bytes'),
    ('normalized',413,'normalized_request_too_large','limit is 2097152 bytes'),
    ('count',409,'request_limit','16 of 16'),
    ('budget',402,'budget_exhausted','budget'),
])
def test_relay_rejects_with_safe_reason_without_provider_or_receipt(tmp_path,case,status,code,detail):
    from lab.build_runtime import BudgetRelay
    s,c,p,cfg=setup_project(tmp_path)
    def forbidden(request):pytest.fail('Local rejection must not reach provider')
    with BudgetRelay(s,p,cfg,'private-real-test-key',0 if case=='budget' else 10,'fixture',transport=httpx.MockTransport(forbidden)) as relay:
        if case=='count':relay.calls=16
        if case=='raw':raw=b'{}'
        elif case=='normalized':raw=json.dumps({'input':[0]*((2*1024*1024)//3)},separators=(',',':')).encode()
        else:raw=b'{"input":"Summarize prior construction history. UNTRUSTED-SECRET-DO-NOT-ECHO"}'
        if case=='raw':actual,payload=post_declared_oversize(relay.url,relay.token)
        else:
            with httpx.Client(trust_env=False) as client:
                response=client.post(relay.url+'/responses',headers={'Authorization':'Bearer '+relay.token},content=raw)
            actual,payload=response.status_code,response.json()
        assert actual==status
        error=payload['error']
        assert error['code']==code and detail in error['message']
        assert relay.rejection_error==error['message']
        assert all(secret not in error['message'] for secret in ['UNTRUSTED-SECRET','private-real-test-key',relay.token])
    assert s.get(p)['records']==[] and not (tmp_path/'workspace-receipts').exists()


def test_compaction_uses_same_relay_count_budget_and_unknown_outcome_gate(tmp_path):
    from lab.build_runtime import BudgetRelay
    s,c,p,cfg=setup_project(tmp_path);calls=[]
    def timeout(request):calls.append(request);raise httpx.ReadTimeout('UNTRUSTED-SECRET')
    with BudgetRelay(s,p,cfg,'private-real-test-key',10,'fixture',transport=httpx.MockTransport(timeout)) as relay:
        with httpx.Client(trust_env=False) as client:
            headers={'Authorization':'Bearer '+relay.token}
            body={'input':[{'role':'user','content':'Summarize the prior construction history.'}]}
            assert client.post(relay.url+'/responses',headers=headers,json=body).status_code==502
            blocked=client.post(relay.url+'/responses',headers=headers,json=body)
            assert blocked.status_code==409
            assert blocked.json()['error']['code']=='unknown_outcome'
            assert 'reservation retained' in blocked.json()['error']['message']
            assert client.post(relay.url+'/responses/compact',headers=headers,json=body).status_code==403
    assert len(calls)==1
    record=s.get(p)['records'][0]
    assert record['status']=='unknown' and record['committed_cost']==record['reserved_cost']>0


@pytest.mark.parametrize('runtime_exit',[0,1,'interrupted'])
def test_native_build_stores_local_rejection_reason_even_on_zero_exit(tmp_path,monkeypatch,runtime_exit):
    import subprocess
    import lab.build_runtime as runtime
    s,c,p,cfg=setup_project(tmp_path)
    s.mutate(p,lambda project:project.update(busy=True,builds=[{'id':'fixture','status':'running'}]))
    def run(args,**kwargs):
        work=kwargs['cwd']
        if 'exec' not in args:
            (work/'inside-probe.txt').write_text('ok')
            return subprocess.CompletedProcess(args,0,'ISOLATION_OK','')
        import tomllib
        config=tomllib.loads((Path(kwargs['env']['CODEX_HOME'])/'config.toml').read_text(encoding='utf-8'))
        status,_=post_declared_oversize(config['model_providers']['builder']['base_url'],kwargs['env']['BUILDER_RELAY_TOKEN'])
        assert status==413
        if runtime_exit=='interrupted':raise TimeoutError('untrusted-runtime-message')
        return subprocess.CompletedProcess(args,runtime_exit,'','')
    monkeypatch.setattr(runtime,'bounded_run',run)
    runtime.Builder(s,c).run(p,'fixture',s.get(p)['versions'][0],cfg,'never-sent',10,'codex')
    project=s.get(p);build=project['builds'][0]
    assert build['status']=='failed' and 'raw request' in build['error'] and '2097153' in build['error']
    assert project['busy'] is False and project['records']==[]


def test_native_marker_still_fails_closed_and_retains_explanation(tmp_path,monkeypatch):
    import subprocess
    import lab.build_runtime as runtime
    s,c,p,cfg=setup_project(tmp_path)
    s.mutate(p,lambda project:project.update(busy=True,builds=[{'id':'fixture','status':'running'}]))
    def run(args,**kwargs):
        work=kwargs['cwd']
        if 'exec' not in args:
            (work/'inside-probe.txt').write_text('ok')
            return subprocess.CompletedProcess(args,0,'ISOLATION_OK','')
        assert 'BLOCKED.md exclusively' in kwargs['input']
        (work/'BLOCKED.md').write_text('Retained-state limitation, even if not a new method choice.')
        return subprocess.CompletedProcess(args,0,'','')
    monkeypatch.setattr(runtime,'bounded_run',run)
    runtime.Builder(s,c).run(p,'fixture',s.get(p)['versions'][0],cfg,'never-sent',10,'codex')
    build=s.get(p)['builds'][0]
    assert build['status']=='failed' and 'unresolved method' in build['error']
    assert any(a['name']=='BLOCKED.md' for a in build['artifacts'])


def test_shared_construction_prompt_bounds_duplicate_reads_and_reserves_method_marker():
    from lab.build_runtime import construction_prompt
    prompt=construction_prompt('python')
    for contract in ['18000 UTF-8 bytes','METHOD-VIEW.json','MATERIAL-INDEX.json','MATERIAL-001.txt',
                     'previous-version.txt','pagination',
                     'inclusive/exclusive','both minimum and maximum','README.md',
                     'BLOCKED.md exclusively','unresolved user method choices','all selected source text',
                     'Batch independent bounded reads','never concatenate whole files']:
        assert contract in prompt
