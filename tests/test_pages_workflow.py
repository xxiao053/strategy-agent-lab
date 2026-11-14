"""Publication policy is tested without running or publishing a GitHub workflow."""
import json
from pathlib import Path
import re


def test_pages_workflow_is_manual_opt_in_and_limits_deploy_authority():
    path=Path(__file__).resolve().parents[1]/'.github/workflows/pages.yml'
    assert path.is_file(), 'The reviewed static artifact needs a manual publication entry.'
    workflow=json.loads(path.read_text())  # JSON is a strict YAML subset.
    assert set(workflow['on'])=={'workflow_dispatch'}
    approval=workflow['on']['workflow_dispatch']['inputs']['publish']
    assert approval['type']=='boolean' and approval['default'] is False
    assert workflow['permissions']=={'contents':'read'}
    build=workflow['jobs']['build'];deploy=workflow['jobs']['deploy']
    assert deploy['needs']=='build' and deploy['if']=='${{ inputs.publish }}'
    assert deploy['environment']['name']=='github-pages'
    assert deploy['permissions']=={'pages':'write','id-token':'write'}
    assert 'permissions' not in build
    assert build['env']['VITE_SHOWCASE_REPOSITORY']=='https://github.com/${{ github.repository }}'
    steps=build['steps']
    assert next(s for s in steps if s.get('uses','').startswith('actions/checkout@'))['with']['persist-credentials'] is False
    artifact=next(s for s in steps if s.get('uses','').startswith('actions/upload-pages-artifact@'))
    assert artifact['with']['path']=='web/dist-showcase'
    for job in (build,deploy):
        assert job['runs-on']=='ubuntu-latest'
        for step in job['steps']:
            if 'uses' in step:assert re.fullmatch(r'actions/[a-z-]+@[a-f0-9]{40}',step['uses'])
    assert all('secrets.' not in json.dumps(job) for job in (build,deploy))
