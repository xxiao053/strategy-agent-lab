import json
import sqlite3
from pathlib import Path
import httpx
import pytest

pytestmark = pytest.mark.market_data
from fastapi.testclient import TestClient

from lab.contracts import RunConfig
from lab.store import Store
from lab.runner import Runner
from lab.api import create_app
from tests.helpers import bound_reply

ROOT = Path(__file__).resolve().parents[1]


def test_full_numeric_run_is_real_accounting_not_model_demo(tmp_path):
    store = Store(tmp_path/'lab.db')
    runner = Runner(ROOT, store)
    r = runner.create(RunConfig(approved=True))
    runner.execute(r['id'])
    result = store.get(r['id'])
    assert result['status'] == 'completed'
    assert len(result['state']['account']['curve']) == 718
    assert result['state']['account']['orders']
    assert result['state']['account']['trades']
    assert result['summary']['requests'] == 0
    assert 'baseline' in result['provenance']
    assert result['summary']['equity'] > 0
    assert result['summary']['max_drawdown'] <= 0
    before = result['state']
    runner.execute(r['id'])
    assert store.get(r['id'])['state'] == before


def test_versioned_strategy_and_dataset_are_immutable(tmp_path):
    s = Store(tmp_path/'lab.db')
    r = Runner(ROOT, s)
    c = RunConfig(approved=True, symbols=['AAPL'], end='2024-12-31')
    a = r.create(c)
    c.strategy.volume_multiple = 2
    b = r.create(c)
    assert a['strategy_id'] != b['strategy_id']
    assert a['data_id'] == b['data_id']
    assert s.get(a['id'])['config']['strategy']['volume_multiple'] == 1.2


def test_no_live_call_without_consent_or_key(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    s = Store(tmp_path/'lab.db')
    r = Runner(ROOT, s)
    with pytest.raises(ValueError):
        r.create(RunConfig(approved=False))
    config = RunConfig(mode='live', paid_authorized=True, approved=True)
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        r.create(config)


def test_raw_saved_before_parse_and_resume_never_recharges(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-key-not-real')
    calls = []
    def handler(request):
        calls.append(1)
        payload = json.loads(request.content)
        text = payload['input'][0]['content'][0]['text']
        ctx = json.loads(text)
        dates = [b['date'] for b in ctx['bars']]
        decision = bound_reply(ctx)
        return httpx.Response(200, json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(decision)}]}], 'usage':{'input_tokens':100,'output_tokens':50}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = Store(tmp_path/'lab.db')
    runner = Runner(ROOT, store, client=client)
    result = runner.create(RunConfig(symbols=['AAPL'], start='2024-12-19', end='2024-12-23', mode='live', approved=True, paid_authorized=True))
    runner.execute(result['id'])
    done = store.get(result['id'])
    assert done['status'] == 'completed'
    assert calls and done['summary']['requests'] == len(calls)
    assert store.requests(result['id'])[0]['raw']
    # Crash/restart boundary: discard only day checkpoints; keep durable responses.
    with sqlite3.connect(tmp_path/'lab.db') as db:
        db.execute("UPDATE runs SET state_json=NULL,status='paused' WHERE id=?", (result['id'],))
    Runner(ROOT, store, client=client).execute(result['id'])
    assert len(calls) == done['summary']['requests']
    assert store.get(result['id'])['state'] == done['state']
    replay = runner.replay(result['id'])
    runner.execute(replay['id'])
    assert len(calls) == done['summary']['requests']
    assert store.get(replay['id'])['state'] == done['state']


def test_ambiguous_network_pauses_and_does_not_retry_on_resume(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-test')
    calls = []
    def handler(r):
        calls.append(1)
        raise httpx.ReadTimeout('secret')
    s = Store(tmp_path/'lab.db')
    runner = Runner(ROOT, s, client=httpx.Client(transport=httpx.MockTransport(handler)))
    x = runner.create(RunConfig(symbols=['AAPL'], start='2024-12-19', end='2024-12-23', mode='live', approved=True, paid_authorized=True))
    runner.execute(x['id'])
    assert s.get(x['id'])['status'] == 'paused'
    assert s.requests(x['id'])[0]['status'] == 'unknown'
    runner.execute(x['id'])
    assert len(calls) == 1


def test_request_budget_is_enforced_without_calls(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-test')
    def handler(r):
        pytest.fail('Budget should stop before transport')
    s = Store(tmp_path/'lab.db')
    runner = Runner(ROOT, s, client=httpx.Client(transport=httpx.MockTransport(handler)))
    x = runner.create(RunConfig(symbols=['AAPL'], start='2024-12-19', end='2024-12-23', mode='live', approved=True, paid_authorized=True, budget_usd=.00001))
    runner.execute(x['id'])
    assert s.get(x['id'])['status'] == 'paused'
    assert not s.requests(x['id'])


def test_api_local_only_and_cross_origin_writes_rejected(tmp_path):
    app = create_app(ROOT, tmp_path/'lab.db')
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        assert client.get('/api/bootstrap').status_code == 200
        assert client.get('/api/bootstrap', headers={'Host':'evil.example'}).status_code == 400
        assert client.post('/api/preflight', json=RunConfig(approved=True).model_dump(), headers={'Origin':'https://evil.example','X-Lab-Request':'1'}).status_code == 403
        assert client.post('/api/preflight', json=RunConfig(approved=True).model_dump()).status_code == 403
        from lab.contracts import Strategy
        r = client.post('/api/preflight', json=RunConfig(approved=True,strategy=Strategy(cup_max=100,handle_max=20)).model_dump(), headers={'X-Lab-Request':'1'})
        assert r.status_code == 200
        assert r.json()['numeric_dates'] == 43
        providers = client.get('/api/bootstrap').json()['providers']
        assert len(providers) == 8
        assert all('key' not in p for p in providers)
        assert client.get('/api/runs/not-found').status_code == 404
