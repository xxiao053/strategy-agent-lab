"""A selected demonstration is a model workflow, not a performance comparison."""
import pytest
from fastapi.testclient import TestClient
from lab.api import create_app
from lab.contracts import RunConfig
from lab.store import Store, fingerprint


def completed_model(store, scope='demo-budget'):
    cfg = RunConfig(mode='live', approved=True, paid_authorized=True, budget_scope=scope)
    store.authorize_budget(scope, 2)
    run = store.create(cfg.model_dump(), {}, 'fixture-data')
    store.begin_request(run['id'], 'day:SYM:primary', run['id']+':1', 'hash', .01, {'body': {}})
    store.save_response(run['id']+':1', {'id': 'fixture', 'model': cfg.model},
                        {'input': 100, 'output': 20, 'reported': True}, 1)
    store.checkpoint(run['id'], {'day': 1, 'account': {'curve': [], 'orders': [], 'trades': []}})
    store.status(run['id'], 'completed')
    return store.get(run['id'])


def test_model_showcase_needs_no_baseline_or_replay_and_resets_new_run_permissions(tmp_path):
    app = create_app(db_path=tmp_path/'runs.sqlite3')
    store = app.state.store
    run = completed_model(store)
    store.set_showcase({'run_id': run['id']})
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        boot = client.get('/api/bootstrap').json()
    assert boot['showcase']['run_id'] == run['id']
    assert boot['showcase']['summary']['requests'] == 1
    assert 'baseline_id' not in boot['showcase']
    assert 'numeric_showcase' not in boot
    assert not boot['defaults']['paid_authorized'] and not boot['defaults']['approved']
    assert boot['defaults']['budget_scope'] is None
    assert boot['defaults']['strategy'] == run['config']['strategy']


def test_removing_old_runs_preserves_spend_and_selected_run_exactly(tmp_path):
    store = Store(tmp_path/'runs.sqlite3')
    keep, old = completed_model(store), completed_model(store)
    store.set_showcase({'run_id': keep['id']})
    before = fingerprint(store.get(keep['id'], True))
    budget = store.budget_status('demo-budget')
    assert store.delete_runs([old['id']]) == 1
    assert [r['id'] for r in store.list()] == [keep['id']]
    assert not store.requests(old['id'])
    assert fingerprint(store.get(keep['id'], True)) == before
    after = store.budget_status('demo-budget')
    assert after == pytest.approx(budget)
    assert store.delete_runs([old['id']]) == 0
    assert store.budget_status('demo-budget') == pytest.approx(budget)
    with pytest.raises(ValueError, match='exhausted'):
        store.begin_request(keep['id'], 'next', 'next', 'hash', 2, {})


@pytest.mark.parametrize('problem', ['showcase', 'running', 'unsettled', 'replay', 'reuse_source'])
def test_deletion_refuses_protected_or_referenced_records(tmp_path, problem):
    store = Store(tmp_path/'runs.sqlite3')
    run = completed_model(store)
    if problem == 'showcase':
        store.set_showcase({'run_id': run['id']})
    elif problem == 'running':
        store.status(run['id'], 'running')
    elif problem == 'unsettled':
        store.begin_request(run['id'], 'next', 'next', 'hash', .01, {})
    elif problem == 'replay':
        cfg = RunConfig(mode='replay', replay_of=run['id'])
        store.create(cfg.model_dump(), {}, 'fixture-data')
    else:
        cfg = RunConfig(mode='live', approved=True, paid_authorized=True,
                        reuse_responses_from=run['id'])
        store.create(cfg.model_dump(), {}, 'fixture-data')
    before = store.list()
    with pytest.raises(ValueError):
        store.delete_runs([run['id']])
    assert store.list() == before
