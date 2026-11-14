"""Real SDK and worker engine, scripted HTTP only: never a provider/AI acceptance."""
import asyncio
import io
import json
import os
import shlex
import uuid
from pathlib import Path
import httpx
import pytest
from tests.test_distribution_credentials import connection
from tests.test_docker_engine_acceptance import assert_no_owned_resources

pytestmark=pytest.mark.skipif(os.environ.get('LAB_DOCKER_ACCEPTANCE')!='1',reason='Explicit real Docker acceptance only; no provider calls.')


def test_actual_sdk_turn_limit_keeps_partial_code_and_cleans_up(tmp_path,monkeypatch):
    import lab.sdk_builder as sdk
    from lab.sdk_budget import BudgetTransport
    from lab.build_runtime import Builder
    from lab.docker_runtime import installation_id
    from tests.test_project_runs_api import prepared
    store,pid,runs=prepared(tmp_path);version=store.get(pid)['versions'][0]
    cfg=runs.connections.create(dict(provider='openai',model='model',name='test',key='offline-key',input_price=1,output_price=2))
    runs.connections.assign_roles(pid,{'builder':cfg['id'],'execution':None})
    store.mutate(pid,lambda p:(p.update(busy=True),p['builds'][0].update(status='running')))
    calls=[]
    def response(request):
        body=json.loads(request.content);calls.append(body);ordinal=len(calls)
        if ordinal>1:
            outputs=[str(x.get('output','')) for x in body.get('input',[]) if x.get('type')=='function_call_output']
            assert outputs and 'Exit code: 0' in outputs[-1] and 'saved' in outputs[-1]
        tool=next(t for t in body['tools'] if t.get('name','').endswith('exec_command'))
        script="from pathlib import Path;Path('strategy.py').write_text('# partial only');print('saved')"
        return httpx.Response(200,json={'id':f'resp{ordinal}','object':'response','created_at':1,
            'status':'completed','model':'model','output':[{'type':'function_call','id':f'fc{ordinal}',
            'call_id':f'call{ordinal}','name':tool['name'],'arguments':json.dumps({'cmd':'python -c '+shlex.quote(script)})}],
            'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}})
    def transport(*args,**kwargs):return BudgetTransport(*args,**kwargs,transport=httpx.MockTransport(response))
    monkeypatch.setattr(sdk,'BudgetTransport',transport)
    owner=installation_id(tmp_path)
    try:
        sdk.run_build(Builder(store,runs.connections),pid,'build1',version,cfg,'offline-key',10,'Scripted partial-file fixture.')
        project=store.get(pid);build=project['builds'][0]
        assert len(calls)==50 and build['status']=='failed' and 'turn limit' in build['error']
        assert not project['busy']
        assert next(a['text'] for a in build['artifacts'] if a['name']=='strategy.py')=='# partial only'
        assert len(project['records'])==50 and all(r['status']=='completed' for r in project['records'])
    finally:assert_no_owned_resources(owner)


def test_actual_sdk_scripted_budget_exec_patch_exec_roundtrip(tmp_path):
    from lab.docker_runtime import DockerTask
    from lab.sdk_builder import construct
    from lab.sdk_budget import BudgetTransport
    store,connections,cfg=connection(tmp_path);project=store.create('Scripted SDK fixture','en');pid=project['id']
    connections.assign_roles(pid,{'builder':cfg['id'],'execution':None})
    store.mutate(pid,lambda p:p.update(busy=True));calls=[]
    patch='*** Begin Patch\n*** Add File: fixture.txt\n+Isolated official SDK patch.\n*** End Patch'
    def response(request):
        body=json.loads(request.content);calls.append(body);ordinal=len(calls)
        assert body['store'] is False and body['max_output_tokens']==6000 and body['model']=='model'
        records=store.get(pid)['records'];assert len(records)==ordinal and records[-1]['status']=='running'
        outputs=[str(x.get('output','')) for x in body.get('input',[]) if isinstance(x,dict)]
        if ordinal==2:assert any('seed-ok' in x and 'Exit code: 0' in x for x in outputs)
        if ordinal==3:assert any('fixture.txt' in x for x in outputs)
        if ordinal==4:assert any('patch-ok' in x and 'Exit code: 0' in x for x in outputs)
        if ordinal in (1,3):
            tool=next(t for t in body['tools'] if t.get('name','').endswith('exec_command'))
            script=("import os;from pathlib import Path;assert os.getuid()==10001;assert Path('method.txt').read_text()=='trusted input';assert 'noexec' in next(x for x in Path('/proc/mounts').read_text().splitlines() if x.split()[1]=='/tmp').split()[3].split(',');print('seed-ok')" if ordinal==1 else "from pathlib import Path;assert Path('fixture.txt').read_text().strip()=='Isolated official SDK patch.';print('patch-ok')")
            output=[{'type':'function_call','id':f'fc{ordinal}','call_id':f'call{ordinal}','name':tool['name'],'arguments':json.dumps({'cmd':'python -c '+shlex.quote(script),'workdir':'/workspace','tty':False})}]
        elif ordinal==2:
            tool=next(t for t in body['tools'] if t.get('name','').endswith('apply_patch'));assert tool['type']=='custom'
            output=[{'type':'custom_tool_call','id':'ct2','call_id':'call2','name':tool['name'],'input':patch}]
        else:
            assert ordinal==4
            output=[{'type':'message','id':'final','role':'assistant','status':'completed','content':[{'type':'output_text','text':'Scripted SDK flow complete.','annotations':[]}]}]
        return httpx.Response(200,json={'id':f'resp{ordinal}','object':'response','created_at':1,'status':'completed','model':'model','output':output,'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}})
    owner='sdk-test-'+uuid.uuid4().hex
    try:
        with DockerTask(owner,wall_seconds=60) as task:
            task.seed({'method.txt':'trusted input'});task.probe()
            transport=BudgetTransport(store,connections,pid,cfg,'old-key-123',1,'fixture-build',check_task=task.inspect,transport=httpx.MockTransport(response))
            assert asyncio.run(construct(task,'Run only the scripted fixture.',transport,cfg))=='Scripted SDK flow complete.'
            artifacts={a['name']:a['text'] for a in task.collect()}
            assert artifacts['method.txt']=='trusted input' and artifacts['fixture.txt'].strip()=='Isolated official SDK patch.'
        records=store.get(pid)['records'];assert len(calls)==len(records)==4
        assert all(r['status']=='completed' for r in records)
        assert all((tmp_path/'workspace-receipts'/f"{r['id']}.json").is_file() for r in records)
    finally:assert_no_owned_resources(owner)


def test_actual_sdk_can_correct_a_nonmatching_patch_without_losing_workspace(tmp_path):
    from lab.docker_runtime import DockerTask
    from lab.sdk_builder import construct
    from lab.sdk_budget import BudgetTransport
    store,connections,cfg=connection(tmp_path);p=store.create('Patch repair','en');pid=p['id']
    calls=[]
    def response(request):
        body=json.loads(request.content);calls.append(body);ordinal=len(calls)
        if ordinal<=2:
            tool=next(t for t in body['tools'] if t.get('name','').endswith('apply_patch'))
            patch='*** Begin Patch\n*** Update File: fixture.txt\n@@\n-'+('missing line' if ordinal==1 else 'original')+'\n+corrected\n*** End Patch'
            output=[{'type':'custom_tool_call','id':f'ct{ordinal}','call_id':f'call{ordinal}','name':tool['name'],'input':patch}]
        else:
            assert ordinal==3
            output=[{'type':'message','id':'final','role':'assistant','status':'completed','content':[{'type':'output_text','text':'Repair complete.','annotations':[]}]}]
        return httpx.Response(200,json={'id':f'resp{ordinal}','object':'response','created_at':1,'status':'completed','model':'model','output':output,'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}})
    owner='sdk-patch-repair-'+uuid.uuid4().hex
    try:
        with DockerTask(owner,wall_seconds=60) as task:
            task.seed({'fixture.txt':'original\n'});task.probe()
            transport=BudgetTransport(store,connections,pid,cfg,'old-key-123',1,'fixture-build',check_task=task.inspect,transport=httpx.MockTransport(response))
            assert asyncio.run(construct(task,'Scripted recoverable patch.',transport,cfg))=='Repair complete.'
            assert {a['name']:a['text'] for a in task.collect()}['fixture.txt']=='corrected\n'
        assert len(calls)==3 and all(r['status']=='completed' for r in store.get(pid)['records'])
    finally:assert_no_owned_resources(owner)


def test_completed_partial_code_is_freshly_verified_without_another_model_request(tmp_path,monkeypatch):
    import lab.sdk_builder as sdk
    from lab.build_runtime import Builder
    from lab.docker_runtime import installation_id
    from tests.test_project_runs_api import prepared
    store,pid,runs=prepared(tmp_path);version=store.get(pid)['versions'][0]
    source=store.get(pid)['builds'][0]
    source.update(status='failed',model='original-model',provider='openai',connection_id='original-connection')
    source['artifacts'].extend([
        {'name':'test_strategy.py','text':'import unittest\nfrom strategy import decide\nclass Tests(unittest.TestCase):\n def test_interface(self): self.assertEqual(decide({}), {"proposals":[],"state":{}})\n'},
        {'name':'demo.py','text':'import json\nfrom pathlib import Path\nx={"synthetic":True,"decisions":[]}\nPath("result.json").write_text(json.dumps(x))\nprint(json.dumps(x))\n'},
        {'name':'README.md','text':'Offline verification fixture.'},
    ])
    store.mutate(pid,lambda p:p.update(busy=True,builds=[source,{'id':'recovered','version':1,'status':'running','artifacts':[]}]))
    async def no_model(*args):pytest.fail('Valid saved source needs no additional model call')
    monkeypatch.setattr(sdk,'construct',no_model)
    owner=installation_id(tmp_path)
    try:
        sdk.run_build(Builder(store,runs.connections),pid,'recovered',version,{'id':'unused'},'unused',1,'prompt')
        project=store.get(pid);build=project['builds'][1]
        assert build['status']=='completed' and build['validation']['tests_passed']
        assert build['verification_only'] and build['recovered_from']=='build1' and build['execution_hash']
        assert build['model']=='original-model' and build['connection_id']=='original-connection'
        assert project['builds'][0]==source and project['records']==[] and not project['busy']
    finally:assert_no_owned_resources(owner)


def test_actual_sdk_cancellation_releases_running_task():
    from agents.sandbox import Manifest
    from agents.sandbox.snapshot import NoopSnapshotSpec
    from agents.sandbox.sandboxes.docker import DockerSandboxClientOptions
    from lab.docker_runtime import DockerTask,WORKER_IMAGE
    from lab.sdk_builder import hardened_client
    owner='sdk-cancel-'+uuid.uuid4().hex
    try:
        with DockerTask(owner,wall_seconds=60) as task:
            async def check():
                session=await hardened_client(task).create(manifest=Manifest(),snapshot=NoopSnapshotSpec(),options=DockerSandboxClientOptions(image=WORKER_IMAGE,network_mode='none'))
                await session.start()
                running=asyncio.create_task(session.exec('sleep','10',shell=False))
                try:
                    async with asyncio.timeout(2):
                        while task.execution is None:await asyncio.sleep(.01)
                    running.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(running,2)
                    assert task.closed
                finally:
                    if not running.done():running.cancel()
            asyncio.run(check())
    finally:assert_no_owned_resources(owner)


def test_actual_sdk_path_validation_survives_mutated_helper_and_enforces_user_timeout():
    from agents.sandbox import Manifest
    from agents.sandbox.errors import InvalidManifestPathError
    from agents.sandbox.snapshot import NoopSnapshotSpec
    from agents.sandbox.sandboxes.docker import DockerSandboxClientOptions
    from agents.sandbox.session.runtime_helpers import RESOLVE_WORKSPACE_PATH_HELPER as helper
    from lab.docker_runtime import DockerTask,WORKER_IMAGE
    from lab.sdk_builder import hardened_client
    owner='sdk-path-'+uuid.uuid4().hex
    try:
        with DockerTask(owner,wall_seconds=60) as task:
            task.seed({'method.txt':'trusted input'})
            async def check():
                session=await hardened_client(task).create(manifest=Manifest(),snapshot=NoopSnapshotSpec(),options=DockerSandboxClientOptions(image=WORKER_IMAGE,network_mode='none'))
                await session.start()
                stream=await session.read(Path('method.txt'))
                try:assert stream.read()==b'trusted input'
                finally:stream.close()
                poison="from pathlib import Path;p=Path("+repr(str(helper.install_path))+");p.chmod(0o755);p.write_text('#!/bin/sh\\necho /workspace/escape-link\\n');Path('/tmp/outside-data').write_text('outside');Path('escape-link').symlink_to('/tmp/outside-data')"
                assert task.run(['python','-c',poison]).returncode==0
                with pytest.raises(InvalidManifestPathError):await session.read(Path('escape-link'))
                with pytest.raises(InvalidManifestPathError):await session.write(Path('../outside'),io.BytesIO(b'forbidden'))
                with pytest.raises(ValueError,match='user'):await session.exec('id',shell=False,user='root')
                assert task.run(['python','-c',"from pathlib import Path;Path('escape-link').unlink()"]).returncode==0
                with pytest.raises(ValueError,match='time limit'):await session.exec('sleep','2',shell=False,timeout=.05)
            asyncio.run(check())
    finally:assert_no_owned_resources(owner)
