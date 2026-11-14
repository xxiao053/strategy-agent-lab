import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lab.api import create_app
from lab.material_citations import validate_material_citations
from lab.materials import construction_inputs
from lab.workspace_store import WorkspaceStore

ROOT = Path(__file__).resolve().parents[1]
HEAD = {'X-Lab-Request': '1'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('LAB_DATA_ROOT', str(tmp_path))
    return TestClient(create_app(ROOT, tmp_path/'lab.sqlite3'), base_url='http://127.0.0.1')


@pytest.mark.parametrize('example', ['cup-complete', 'nvda-revision'])
def test_shipped_example_becomes_unapproved_independent_project(client, example):
    source = ROOT/'examples/builder'/example/'project.json'
    before = source.read_bytes()
    response = client.post(f'/api/workspace/examples/{example}/copy', headers=HEAD, json={'locale':'en'})
    assert response.status_code == 200, response.text
    p = response.json()
    assert len(p['id']) == 32 and p['id'] != example
    assert p['draft']['rules'] and p['revision'] == 1
    assert p['versions'] == [] and p['records'] == [] and p.get('builds', []) == []
    assert p['model_roles'] == {'builder':None, 'execution':None} and p['busy'] is False
    assert p['example_origin']['id'] == example
    assert 'strategy.py' in {a['name'] for a in p['starter_files']}
    assert not any(a['name'] in {'method.json','result.json'} for a in p['starter_files'])
    assert all(m['kind'] == 'welcome' for m in p['messages'])
    materials = client.get(f"/api/workspace/projects/{p['id']}/materials").json()
    assert materials
    for material in materials:
        assert len(material['id']) == 32 and material['source_kind'] == 'example_excerpt'
        detail = client.get(f"/api/workspace/projects/{p['id']}/materials/{material['id']}").json()
        assert detail['units']
        assert not detail.get('image')
    validate_material_citations(p['draft']['rules'], p['draft']['material_sources'])
    assert client.get(f"/api/workspace/projects/{p['id']}/runs").json() == []
    assert client.get('/api/workspace/connections').json() == []
    approved = client.post(f"/api/workspace/projects/{p['id']}/approve", headers=HEAD, json={'revision':1}).json()
    assert len(approved['versions']) == 1
    inputs = construction_inputs(approved['versions'][0], 'contract')
    assert 'MATERIAL-REFERENCES.json' in inputs
    second = client.post(f'/api/workspace/examples/{example}/copy', headers=HEAD, json={'locale':'zh-CN'}).json()
    assert second['id'] != p['id'] and second['versions'] == []
    assert source.read_bytes() == before


@pytest.mark.parametrize('body', [{'path':'C:/private'}, {'authorized':True}, {'locale':'xx'}, {'locale':[]}, {'locale':{}}, {'title':''}, {'version':True}, {'version':999}])
def test_invalid_copy_does_not_create_partial_project(client, body):
    assert client.post('/api/workspace/examples/cup-complete/copy', headers=HEAD, json=body).status_code == 400
    assert client.get('/api/workspace/projects').json() == []


def test_copy_keeps_local_request_boundary_and_rejects_unknown_example(client):
    assert client.post('/api/workspace/examples/cup-complete/copy', json={}).status_code == 403
    assert client.post('/api/workspace/examples/cup-complete/copy', headers={**HEAD,'Origin':'https://evil.invalid'}, json={}).status_code == 403
    assert client.post('/api/workspace/examples/not-shipped/copy', headers=HEAD, json={}).status_code == 404


def test_choose_older_example_version(client):
    p = client.post('/api/workspace/examples/nvda-revision/copy', headers=HEAD, json={'version':2,'locale':'en'}).json()
    assert p['example_origin']['version'] == 2
    assert any('100' in r['rule'] for r in p['draft']['rules'])


@pytest.mark.parametrize('damage', ['path', 'hash', 'citation', 'size'])
def test_corrupt_package_rejected_before_any_project_write(tmp_path, damage):
    from lab.example_copy import ExampleCopies
    folder = tmp_path/'examples/builder/cup-complete'
    folder.mkdir(parents=True)
    data = json.loads((ROOT/'examples/builder/cup-complete/project.json').read_text(encoding='utf-8'))
    if damage == 'path': data['builds'][0]['files'][0]['name'] = '../strategy.py'
    elif damage == 'hash': data['builds'][0]['files'][0]['text'] += '\n# modified'
    elif damage == 'citation': data['versions'][0]['rules'][0]['material_refs'][0]['id'] = 'missing'
    elif damage == 'size': data['materials'][0]['units'][0]['text'] = 'x'*150000
    (folder/'project.json').write_text(json.dumps(data), encoding='utf-8')
    store = WorkspaceStore(tmp_path/'runs/workspace.sqlite3')
    with pytest.raises(ValueError): ExampleCopies(tmp_path,store).create('cup-complete',{})
    assert store.list() == []


def test_starter_code_is_only_untrusted_source_not_a_completed_build(client):
    from lab.example_copy import starter_artifacts
    p = client.post('/api/workspace/examples/cup-complete/copy', headers=HEAD, json={}).json()
    files = starter_artifacts(p)
    assert any(a['name']=='strategy.py' for a in files)
    assert not any(a['name'].startswith('MATERIAL-') or a['name']=='method.json' for a in files)
    assert p.get('execution_hash') is None and not p.get('builds')
    p['starter_files'][0]['name'] = '../outside.py'
    with pytest.raises(ValueError): starter_artifacts(p)


@pytest.mark.parametrize('names', [
    ['CON.py'], ['a/'*8+'probe.py'], ['Probe.py','probe.py'],
    ['probe.py','probe.py/child.py'], ['PROBE.py/child.py','probe.py'],
])
def test_invalid_seed_names_rejected_before_creating_project(tmp_path, names):
    from lab.example_copy import ExampleCopies
    folder = tmp_path/'examples/builder/cup-complete'
    folder.mkdir(parents=True)
    data = json.loads((ROOT/'examples/builder/cup-complete/project.json').read_text(encoding='utf-8'))
    for name in names:
        data['builds'][0]['files'].append(dict(name=name,text='',sha256=hashlib.sha256(b'').hexdigest()))
    (folder/'project.json').write_text(json.dumps(data),encoding='utf-8')
    store = WorkspaceStore(tmp_path/'runs/workspace.sqlite3')
    with pytest.raises(ValueError): ExampleCopies(tmp_path,store).create('cup-complete',{})
    assert store.list() == []
