"""Automatic checks must remain offline and separate from website publication."""
import json
from pathlib import Path
import re


def workflow():
    path=Path(__file__).resolve().parents[1]/'.github/workflows/ci.yml'
    assert path.is_file(), 'Automatic CI workflow is missing'
    return json.loads(path.read_text())


def test_ci_checks_pushes_and_pull_requests_without_publication_authority():
    config=workflow()
    assert {'push','pull_request'} <= set(config['on'])
    assert 'pull_request_target' not in config['on']
    assert config['permissions']=={'contents':'read'}
    assert 'secrets.' not in json.dumps(config)
    assert config['jobs']
    for job in config['jobs'].values():
        assert 'environment' not in job
        assert job.get('permissions',config['permissions'])=={'contents':'read'}
        assert 0 < job['timeout-minutes'] <= 30
        for step in job['steps']:
            if action:=step.get('uses'):
                assert re.fullmatch(r'actions/(checkout|setup-python|setup-node)@[a-f0-9]{40}',action)
                if action.startswith('actions/checkout@'):
                    assert step['with']['persist-credentials'] is False


def test_backend_ci_runs_without_private_market_data_and_uses_runtime_lock():
    backend=workflow()['jobs']['backend']
    runs='\n'.join(step.get('run','') for step in backend['steps'])
    assert 'python -m pytest -q --without-market-data' in runs
    assert 'requirements-runtime.lock' in runs
    assert 'python -m pip check' in runs
    assert any(step.get('uses','').startswith('actions/setup-python@') for step in backend['steps'])


def test_frontend_ci_tests_and_builds_both_local_and_static_modes():
    frontend=workflow()['jobs']['frontend']
    runs='\n'.join(step.get('run','') for step in frontend['steps']).splitlines()
    assert 'pnpm --dir web install --frozen-lockfile' in runs
    assert 'pnpm --dir web test' in runs
    assert 'pnpm --dir web build' in runs
    assert 'pnpm --dir web build:showcase' in runs
    assert frontend['env']['VITE_SHOWCASE_REPOSITORY']=='https://github.com/${{ github.repository }}'
