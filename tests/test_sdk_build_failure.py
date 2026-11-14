import asyncio
import pytest
from agents.exceptions import MaxTurnsExceeded
from lab.build_runtime import Builder
from tests.test_project_runs_api import prepared


def test_model_summary_survives_independent_verification_failure(tmp_path,monkeypatch):
    import lab.sdk_builder as sdk
    store,pid,runs=prepared(tmp_path);version=store.get(pid)['versions'][0]
    store.mutate(pid,lambda p:(p.update(busy=True),p['builds'][0].update(status='running')))
    class Task:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def seed(self,files):self.files=files
        def probe(self):pass
        def inspect(self):pass
        def collect(self):return [{'name':name,'text':text} for name,text in self.files.items()]
    async def construct(*args):return 'Cannot reconcile calculation history with the supplied contract.'
    monkeypatch.setattr(sdk,'DockerTask',Task);monkeypatch.setattr(sdk,'construct',construct)
    monkeypatch.setattr(sdk,'verify_saved_project',lambda *args:{'tests_passed':False,'demo_exit':1})
    sdk.run_build(Builder(store,runs.connections),pid,'build1',version,{'id':'connection'},'unused',1,'prompt')
    build=store.get(pid)['builds'][0]
    assert build['status']=='failed' and not store.get(pid)['busy']
    assert any('Cannot reconcile calculation history' in e.get('text','') for e in build.get('events',[]))


@pytest.mark.parametrize('error,category',[
    (MaxTurnsExceeded('private exception details'),'turn limit'),
    (asyncio.TimeoutError('private exception details'),'time limit'),
    (RuntimeError('private exception details'),'runtime'),
])
@pytest.mark.parametrize('collection_fails',[False,True])
def test_failed_construction_retains_bounded_partial_artifacts_before_cleanup(
    tmp_path,monkeypatch,error,category,collection_fails,
):
    import lab.sdk_builder as sdk
    store,pid,runs=prepared(tmp_path);version=store.get(pid)['versions'][0]
    store.mutate(pid,lambda p:(p.update(busy=True),p['builds'][0].update(status='running')))
    events=[]
    class Task:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):events.append('closed')
        def seed(self,files):self.files=files
        def probe(self):pass
        def inspect(self):pass
        def collect(self):
            assert 'closed' not in events
            events.append('collected')
            if collection_fails:raise ValueError('invalid archive private details')
            return [{'name':name,'text':text} for name,text in
                    dict(self.files,**{'strategy.py':'# unfinished code, not verified'}).items()]
    async def construct(*args):events.append('construct');raise error
    monkeypatch.setattr(sdk,'DockerTask',Task);monkeypatch.setattr(sdk,'construct',construct)
    monkeypatch.setattr('lab.execution_contract.verify_execution_contract',lambda *a:pytest.fail('Failed construction is never verified'))
    sdk.run_build(Builder(store,runs.connections),pid,'build1',version,{'id':'connection'},'unused',1,'prompt')
    project=store.get(pid);build=project['builds'][0]
    assert events==['construct','collected','closed']
    assert build['status']=='failed' and not project['busy']
    assert category in build['error'] and 'private' not in build['error']
    assert 'No automatic retry' in build['error']
    assert any(a['name']=='strategy.py' for a in build['artifacts']) is not collection_fails
    assert project['records']==[]


@pytest.mark.parametrize('prior_status,prior_version,expected',[
    ('failed',1,True),('failed',2,False),('completed',1,True),('running',1,False),
])
def test_rebuild_seeds_eligible_code_without_replacing_current_approved_inputs(
    tmp_path,monkeypatch,prior_status,prior_version,expected,
):
    import json
    import lab.sdk_builder as sdk
    store,pid,runs=prepared(tmp_path);version=store.get(pid)['versions'][0]
    previous=store.get(pid)['builds'][0]
    previous.update(status=prior_status,version=prior_version)
    previous['artifacts'].extend([
        {'name':'test_strategy.py','text':'# unfinished test'},
        {'name':'MATERIAL-001.txt','text':'old source must not replace an approved source'},
        {'name':'METHOD-VIEW.json','text':'old method must not replace an approved method'},
        {'name':'README.md','text':'prior project notes'},
    ])
    next_build={'id':'build2','version':1,'status':'running','artifacts':[]}
    store.mutate(pid,lambda p:p.update(busy=True,builds=[previous,next_build]))
    seeded=[]
    class Task:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def seed(self,files):seeded.append(files);self.files=files
        def probe(self):pass
        def inspect(self):pass
        def collect(self):return [{'name':k,'text':v} for k,v in dict(self.files,**{'BLOCKED.md':'fixture stop'}).items()]
    async def construct(*args):return 'fixture'
    monkeypatch.setattr(sdk,'DockerTask',Task);monkeypatch.setattr(sdk,'construct',construct)
    sdk.run_build(Builder(store,runs.connections),pid,'build2',version,{'id':'connection'},'unused',1,'prompt')
    files=seeded[0]
    assert ('strategy.py' in files) is expected
    assert json.loads(files['method.json'])==version['method']
    assert 'MATERIAL-001.txt' not in files and 'METHOD-VIEW.json' not in files
    if expected:
        assert files['test_strategy.py']=='# unfinished test'
        assert json.loads(files['BUILD-CONTEXT.json'])['status']==prior_status
    assert store.get(pid)['builds'][0]==previous
    assert store.get(pid)['builds'][1]['status']=='failed'


@pytest.mark.parametrize('deleted_file',['obsolete.py','method.json','EXECUTION-CONTRACT.md'])
def test_failed_precheck_does_not_resurrect_files_deleted_by_repair(tmp_path,monkeypatch,deleted_file):
    import lab.sdk_builder as sdk
    store,pid,runs=prepared(tmp_path);version=store.get(pid)['versions'][0]
    previous=store.get(pid)['builds'][0];previous.update(status='failed')
    previous['artifacts'].extend([{'name':name,'text':'# fixture'} for name in
        ('test_strategy.py','demo.py','README.md','obsolete.py')])
    store.mutate(pid,lambda p:p.update(busy=True,builds=[previous,{'id':'repair','version':1,'status':'running','artifacts':[]}]))
    class Task:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def seed(self,files):self.files=dict(files)
        def probe(self):pass
        def inspect(self):pass
        def collect(self):return [{'name':k,'text':v} for k,v in self.files.items()]
    async def construct(task,*args):
        del task.files[deleted_file]
        return 'Removed obsolete source.'
    checks=[]
    original_verify=sdk.verify_saved_project
    def verify(work,*args):
        checks.append({p.name for p in work.iterdir()})
        if len(checks)==1:
            (work/'result.json').write_text('{"unverified":true}')
            return {'tests_passed':False,'demo_exit':1}
        if deleted_file!='obsolete.py':return original_verify(work,*args)
        return {'tests_passed':True,'demo_exit':0}
    monkeypatch.setattr(sdk,'DockerTask',Task);monkeypatch.setattr(sdk,'construct',construct)
    monkeypatch.setattr(sdk,'verify_saved_project',verify)
    sdk.run_build(Builder(store,runs.connections),pid,'repair',version,{'id':'unused'},'unused',1,'prompt')
    assert len(checks)==2 and 'obsolete.py' in checks[0]
    assert not {deleted_file,'result.json'}&checks[1]
    build=store.get(pid)['builds'][1]
    assert build['status']==('completed' if deleted_file=='obsolete.py' else 'failed')
    assert not {deleted_file,'result.json'}&{a['name'] for a in build['artifacts']}
    assert store.get(pid)['builds'][0]==previous
