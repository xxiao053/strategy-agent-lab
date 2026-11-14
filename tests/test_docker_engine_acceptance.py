"""Explicit opt-in engine checks, never inference; skipped by ordinary offline suites."""
import os
import hashlib
import uuid
import pytest

pytestmark=pytest.mark.skipif(os.environ.get('LAB_DOCKER_ACCEPTANCE')!='1',reason='Real Docker acceptance requires explicit opt-in and a running Linux engine.')


def test_actual_image_material_decoder_transport_and_cleanup(tmp_path,monkeypatch):
    from lab.materials import Materials
    from lab.workspace_store import WorkspaceStore
    from tests.test_visual_inputs import picture
    from PIL import PngImagePlugin
    monkeypatch.setenv('LAB_EXECUTION_BACKEND','docker');monkeypatch.setenv('LAB_DATA_ROOT',str(tmp_path))
    store=WorkspaceStore(tmp_path/'runs'/'test.db');pid=store.create('Image parser acceptance','en')['id'];materials=Materials(tmp_path,store)
    metadata=PngImagePlugin.PngInfo();metadata.add_text('discard','a'*1600000)
    raw=picture(size=(160,80),pnginfo=metadata)
    meta=materials.upload(pid,'offline.png','image/png',raw)
    png=materials.image(pid,meta['id'],meta['image']['sha256'])
    assert hashlib.sha256(png).hexdigest()==meta['image']['sha256'] and len(png)<1000
    assert meta['bytes']>1500000 and meta['image']['width']==160
    assert not list((tmp_path/'material-tasks').iterdir())
    from lab.docker_runtime import installation_id
    assert_no_owned_resources(installation_id(tmp_path/'runs'))


def test_actual_max_pixel_image_normalizes_with_existing_memory_quota(tmp_path,monkeypatch):
    from lab.materials import Materials
    from lab.workspace_store import WorkspaceStore
    from tests.test_visual_inputs import picture
    from lab.docker_runtime import installation_id
    monkeypatch.setenv('LAB_EXECUTION_BACKEND','docker');monkeypatch.setenv('LAB_DATA_ROOT',str(tmp_path))
    store=WorkspaceStore(tmp_path/'runs'/'test.db');pid=store.create('Pixel limit acceptance','en')['id'];materials=Materials(tmp_path,store)
    meta=materials.upload(pid,'pixels.png','image/png',picture(size=(4000,4000),mode='RGB'))
    assert (meta['image']['width'],meta['image']['height'])==(1024,1024)
    assert_no_owned_resources(installation_id(tmp_path/'runs'))


def assert_no_owned_resources(owner):
    from lab.docker_runtime import connect
    client=connect()
    try:
        assert not client.containers.list(all=True,filters={'label':'lab.installation='+owner})
        assert not client.volumes.list(filters={'label':'lab.installation='+owner})
        print('No task containers or volumes remain for test installation '+owner)
    finally:client.close()


def test_actual_networkless_nonroot_quota_and_cleanup():
    from lab.docker_runtime import DockerTask,connect
    owner=uuid.uuid4().hex
    with DockerTask(owner) as task:
        task.probe();ident=task.container.id
        task.seed({'input.txt':'cutoff-only'})
        result=task.run(['python','-I','-c',"from pathlib import Path; assert Path('input.txt').read_text()=='cutoff-only'; p=Path('large'); blocked=False\ntry:p.write_bytes(b'x'*20000000)\nexcept OSError:blocked=True\nassert blocked; print('QUOTA_OK')"])
        assert result.returncode==0 and 'QUOTA_OK' in result.stdout
    client=connect()
    try:assert not client.containers.list(all=True,filters={'id':ident})
    finally:client.close()
    assert_no_owned_resources(owner)


def test_actual_infinite_output_is_killed_and_collected_files_survive(tmp_path):
    from lab.docker_runtime import DockerTask,connect
    from lab.materials import reference_inputs
    owner=uuid.uuid4().hex
    material='完整来源 Unicode β / selected evidence\n'*400+'FINAL-SOURCE-MARKER'
    version={'method':{'scope':'daily','rules':[],'questions':[],'material_sources':[
        {'id':'a'*32,'sha256':hashlib.sha256(material.encode()).hexdigest(),'name':'notes.md','units':[{'location':'L1','text':material}]}]}}
    files={'strategy.py':'pass',**reference_inputs(version)}
    with DockerTask(owner) as task:
        task.seed(files)
        digests={name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}
        script="import hashlib,json;from pathlib import Path;expected="+repr(digests)+";assert all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest for name,digest in expected.items());assert json.loads(Path('MATERIAL-REFERENCES.json').read_text())['sources'][0]['units'][0]['text'].endswith('FINAL-SOURCE-MARKER');print('FULL_UNICODE_SOURCE_OK')"
        result=task.run(['python','-I','-c',script])
        assert result.returncode==0 and result.stdout.strip()=='FULL_UNICODE_SOURCE_OK'
        saved=task.collect()
    assert {a['name']:a['text'] for a in saved}==files
    with pytest.raises(ValueError,match='limit'):
        with DockerTask(owner) as task:
            task.run(['python','-u','-c',"while True: print('x'*8192)"],timeout=3,output_limit=32768)
    client=connect()
    try:assert not client.containers.list(all=True,filters={'label':'lab.installation='+owner})
    finally:client.close()
    assert_no_owned_resources(owner)


def test_actual_readonly_cutoff_workspace(tmp_path,monkeypatch):
    from lab.docker_runtime import DockerBoundary
    work=tmp_path/'work';home=tmp_path/'runtime';work.mkdir();home.mkdir()
    (work/'context.json').write_text('{"cutoff":"2024-01-02"}')
    monkeypatch.setenv('LAB_DATA_ROOT',str(tmp_path/'appdata'))
    script="from pathlib import Path; assert Path('context.json').read_text()=='{\"cutoff\":\"2024-01-02\"}'; denied=0\nfor name in ['context.json','created.txt']:\n try:Path(name).write_text('bad')\n except OSError:denied+=1\nassert denied==2;print('READONLY_OK')"
    result=DockerBoundary(work,home).run(['python','-I','-c',script])
    assert result.returncode==0 and result.stdout.strip()=='READONLY_OK'
    from lab.docker_runtime import installation_id
    assert_no_owned_resources(installation_id(tmp_path/'appdata'/'runs'))


def test_actual_multisymbol_sized_input_remains_readonly_and_cleans_up(tmp_path,monkeypatch):
    from lab.project_evaluator import IsolatedEvaluator
    from lab.docker_runtime import installation_id
    monkeypatch.setenv('LAB_EXECUTION_BACKEND','docker');monkeypatch.setenv('LAB_DATA_ROOT',str(tmp_path))
    source='def decide(context):\n assert len(context["fixture"]) == 2000000\n return {"proposals":[],"state":{"observed":context["cutoff"]}}\n'
    result=IsolatedEvaluator(tmp_path/'scopes',[{'name':'strategy.py','text':source}]).decide(
        {'cutoff':'2024-01-03','bars':{},'fixture':'x'*2000000})
    assert result=={'proposals':[],'state':{'observed':'2024-01-03'}}
    assert list((tmp_path/'scopes').iterdir())==[]
    assert_no_owned_resources(installation_id(tmp_path/'runs'))
