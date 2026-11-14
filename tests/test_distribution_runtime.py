import subprocess
import sys
import pytest


def test_data_root_keeps_source_immutable(tmp_path,monkeypatch):
    from lab.api import create_app
    from fastapi.testclient import TestClient
    data=tmp_path/'data';source=tmp_path/'source';source.mkdir()
    monkeypatch.setenv('LAB_DATA_ROOT',str(data))
    app=create_app(root=source)
    with TestClient(app,base_url='http://localhost') as client:
        assert client.get('/api/workspace/projects').status_code==200
    assert (data/'runs/workspace.sqlite3').exists()
    assert not (source/'runs').exists()


def test_native_collection_stops_bounded_traversal(tmp_path):
    from lab.build_runtime import collect_artifacts
    for i in range(513):(tmp_path/f'{i}.ignored').touch()
    with pytest.raises(ValueError,match='limit'):collect_artifacts(tmp_path)


def test_owned_process_stops_on_workspace_overflow(tmp_path):
    from lab.process_guard import bounded_run
    script="import pathlib,time;pathlib.Path('huge').write_bytes(b'x'*3000000);time.sleep(30)"
    with pytest.raises(ValueError,match='Filesystem'):
        bounded_run([sys.executable,'-c',script],cwd=tmp_path,timeout=5,workspace=tmp_path)
