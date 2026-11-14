from fastapi.testclient import TestClient
import pytest

pytestmark = pytest.mark.market_data
from lab.api import create_app
from lab.contracts import RunConfig
from lab.market import load_snapshot
from lab.store import Store
from lab.runner import Runner
from tests.test_workflow import ROOT


def test_fixed_candidates_context_and_chart_never_switch_geometry(tmp_path):
    app=create_app(ROOT,tmp_path/'db');s=app.state.store;r=app.state.runner
    run=r.create(RunConfig(approved=True,symbols=['QQQ'],start='2024-11-05',end='2024-11-08'))
    r.execute(run['id']);event=next(e for e in s.get(run['id'])['state']['decisions'] if e['candidates'])
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        url=f"/api/runs/{run['id']}/context/QQQ/{event['date']}"
        ctx=c.get(url).json()
        assert ctx['candidates']==event['candidates']
        assert ctx['evaluations']==[]
        assert ctx['archived'] is False
        assert ctx['references']['version']=='cup-teaching-v1'
        chart=f"/api/runs/{run['id']}/chart/QQQ/{event['date']}"
        image=c.get(chart,params={'candidate_id':event['candidates'][0]['candidate_id']})
        assert image.status_code==200 and image.content.startswith(b'\x89PNG')
        assert c.get(chart,params={'candidate_id':'invented'}).status_code==400
        assert c.get(url.replace(event['date'],'2024-11-11')).status_code==400


def test_archive_chart_and_original_input_remain_readable_without_new_strategy_parse(tmp_path):
    app=create_app(ROOT,tmp_path/'db');s=app.state.store
    cfg=RunConfig(symbols=['QQQ'],start='2024-11-05',end='2024-11-08').model_dump()
    cfg['strategy'].pop('version');cfg['strategy']['max_holding']=40
    data=load_snapshot(ROOT,['QQQ'],cfg['start'],cfg['end'])
    run=s.create(cfg,{k:[b.model_dump() for b in v] for k,v in data.items()},'original-data')
    body={'instructions':'ORIGINAL SYSTEM','input':[{'role':'user','content':[{'type':'input_text','text':'ORIGINAL HISTORICAL INPUT'}]}]}
    s.begin_request(run['id'],'2024-11-06:QQQ',run['id']+':receipt','hash',.01,{'body':body})
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        ctx=c.get(f"/api/runs/{run['id']}/context/QQQ/2024-11-06")
        assert ctx.status_code==200
        assert ctx.json()['archived'] is True
        assert ctx.json()['text']=='ORIGINAL HISTORICAL INPUT'
        assert ctx.json()['system']=='ORIGINAL SYSTEM'
        assert c.get(f"/api/runs/{run['id']}/chart/QQQ/2024-11-06").status_code==200
    assert s.get(run['id'])['config']==cfg
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        assert c.post(f"/api/runs/{run['id']}/resume",json={},headers={'X-Lab-Request':'1'}).status_code==400


def test_nontrading_end_is_rejected_before_run_or_inference(tmp_path):
    s=Store(tmp_path/'db');r=Runner(ROOT,s)
    cfg=RunConfig(approved=True,symbols=['AAPL'],start='2024-12-19',end='2024-12-21')
    with pytest.raises(ValueError,match='trading sessions'):r.create(cfg)
    assert s.list()==[]


def test_exposure_summary_uses_actual_account_not_risk_budget(tmp_path):
    s=Store(tmp_path/'db');run=s.create(RunConfig().model_dump(),{},'data')
    s.checkpoint(run['id'],{'account':{'curve':[
        {'equity':100000,'cash':100000,'positions':0},
        {'equity':100000,'cash':80000,'positions':1},
        {'equity':100000,'cash':60000,'positions':2}],
        'orders':[{'side':'buy','status':'filled'},{'side':'buy','status':'cancelled_gap'},
                  {'side':'sell','status':'filled'}], 'trades':[], 'positions':{}}})
    summary=s.get(run['id'])['summary']
    assert summary['buy_fills']==1 and summary['sell_fills']==1
    assert summary['active_sessions']==2
    assert abs(summary['mean_exposure']-.2)<1e-9
    assert abs(summary['current_exposure']-.4)<1e-9


def test_bootstrap_exposes_universe_without_inventing_a_model_showcase(tmp_path):
    app=create_app(ROOT,tmp_path/'db')
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        b=c.get('/api/bootstrap').json()
        assert len(b['universe'])>=30
        assert any(x['symbol']=='NVDA' for x in b['universe'])
        assert b['showcase'] is None
