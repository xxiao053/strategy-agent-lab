import pytest


def test_data_preparation_only_on_explicit_request(tmp_path,monkeypatch):
    from lab.data_preparation import DataPreparation
    from lab.workspace_store import WorkspaceStore
    store=WorkspaceStore(tmp_path/'workspace.sqlite3');p=store.create('P','en')
    calls=[]
    manager=DataPreparation(tmp_path,store,fetch=lambda *a,**kw:calls.append((a,kw)))
    assert calls==[]
    with pytest.raises(ValueError):manager.start(p['id'],dict(build_id='missing',symbols=['SPY'],start='2024-01-02',end='2024-01-03'))
    assert calls==[] and not store.get(p['id'])['busy']


def test_market_transport_bounds_bytes_before_parse(monkeypatch):
    from scripts.freeze_market import _transport
    class Response:
        status_code=200;headers={}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_bytes(self):yield b'x'*4000001
        def stream(self,*a,**kw):return self
    monkeypatch.setattr('httpx.Client',lambda *a,**kw:Response())
    with pytest.raises(ValueError,match='size'):_transport('https://query1.finance.yahoo.com/v8/finance/chart/SPY')


def test_preparation_reports_progress_without_model_or_overwrite(tmp_path,monkeypatch):
    from tests.test_project_runs_api import prepared,body
    from lab.data_preparation import DataPreparation
    store,pid,_=prepared(tmp_path);calls=[]
    def fetch(root,symbol,**kw):calls.append((root,symbol,kw));return {'sha256':'known','validation':{'sessions':3}}
    prep=DataPreparation(tmp_path,store,fetch=fetch)
    monkeypatch.setattr('lab.data_preparation.threading.Thread.start',lambda self:None)
    config={k:v for k,v in body().items() if k in {'build_id','symbols','start','end'}}
    state=prep.start(pid,config);assert state['status']=='running' and store.get(pid)['busy']
    monkeypatch.undo()
    prep.execute(pid,state['id'],config,0)
    result=store.get(pid)['data_preparation']
    assert result['status']=='completed' and result['completed']==1 and not store.get(pid)['busy']
    assert calls[0][1]=='SPY' and calls[0][2]['retries']==1 and store.get(pid)['records']==[]


def test_preparation_rejects_huge_date_scope_before_calendar(tmp_path,monkeypatch):
    from tests.test_project_runs_api import prepared
    from lab.data_preparation import DataPreparation
    store,pid,_=prepared(tmp_path)
    def forbidden(*args):raise AssertionError('unbounded calendar creation')
    monkeypatch.setattr('lab.data_preparation.market_calendar',forbidden)
    with pytest.raises(ValueError,match='date scope'):
        DataPreparation(tmp_path,store).start(pid,dict(build_id='build1',symbols=['SPY'],start='1900-01-01',end='9999-12-30'))


def test_preparation_worker_start_failure_releases_busy(tmp_path,monkeypatch):
    from tests.test_project_runs_api import prepared,body
    from lab.data_preparation import DataPreparation
    store,pid,_=prepared(tmp_path)
    def failed(self):raise RuntimeError('fixture')
    monkeypatch.setattr('lab.data_preparation.threading.Thread.start',failed)
    config={k:v for k,v in body().items() if k in {'build_id','symbols','start','end'}}
    with pytest.raises(ValueError):DataPreparation(tmp_path,store).start(pid,config)
    assert not store.get(pid)['busy'] and store.get(pid)['data_preparation']['status']=='failed'
