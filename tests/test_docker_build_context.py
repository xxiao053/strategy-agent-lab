"""Distribution context contract: only reviewed inputs, never host runtime files."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
# New runtime assets require an explicit distribution decision and a build check.
REQUIRED_FILES = frozenset("""
Dockerfile
Dockerfile.worker
LICENSE
THIRD_PARTY_NOTICES.txt
DATA_NOTICE.md
DATA_NOTICE.zh-CN.md
requirements-runtime.lock
lab/__init__.py
lab/account.py
lab/api.py
lab/billing.py
lab/build_runtime.py
lab/connections.py
lab/construction_limits.py
lab/container_app.py
lab/contracts.py
lab/data_preparation.py
lab/docker_policy.py
lab/docker_runtime.py
lab/example_copy.py
lab/execution_contract.py
lab/image_policy.py
lab/market.py
lab/material_citations.py
lab/material_parser.py
lab/materials.py
lab/process_guard.py
lab/project_account.py
lab/project_assessments.py
lab/project_charts.py
lab/project_evaluator.py
lab/project_evidence.py
lab/project_history.py
lab/project_limits.py
lab/project_managed.py
lab/project_judgment.py
lab/project_runner.py
lab/project_runs.py
lab/prompts.py
lab/providers.py
lab/provider_io.py
lab/references.py
lab/runner.py
lab/sdk_budget.py
lab/sdk_builder.py
lab/store.py
lab/strategy.py
lab/universe.py
lab/workspace_agent.py
lab/workspace_api.py
lab/workspace_store.py
scripts/freeze_market.py
docs/en/execution-contract.md
docs/media/builder-conversation.png
docs/media/walkthrough.mp4
docs/media/walkthrough.bilingual.srt
docs/media/revision.gif
examples/cup-handle/config.json
examples/cup-handle/result.json
web/package.json
web/pnpm-lock.yaml
web/pnpm-workspace.yaml
web/index.html
web/tsconfig.json
web/vite.config.ts
web/distribution-notices.ts
web/showcase-config.ts
web/src/App.tsx
web/src/CostDetails.tsx
web/src/CredentialRenewal.tsx
web/src/i18n.ts
web/src/Inspection.tsx
web/src/main.tsx
web/src/ModelSettings.tsx
web/src/ProjectDecisionEvidence.tsx
web/src/ProjectLibrary.ts
web/src/ProjectPresentation.ts
web/src/ProjectMaterials.tsx
web/src/ProjectRuns.tsx
web/src/RuntimeStatus.tsx
web/src/SavedProject.tsx
web/src/CupReference.tsx
web/src/saved-project.css
web/src/Showcase.tsx
web/src/showcase.css
web/src/showcase-main.tsx
web/src/saved-examples.ts
web/src/vite-env.d.ts
web/src/style.css
web/src/workspace.css
web/src/Workspace.tsx
web/src/WorkbenchGuide.tsx
web/src/WorkbenchMedia.tsx
""".split())
for example_path in ('examples/builder/cup-complete','examples/builder/nvda-revision'):
    _example = json.loads((ROOT / example_path / 'project.json').read_text(encoding='utf-8'))
    REQUIRED_FILES |= {example_path + '/project.json', example_path + '/presentation.json'} | {
        example_path + '/images/' + image['sha256'] + '.png'
        for run in _example['runs'] for decision in run['decisions'] for image in decision['images']
    }


@pytest.fixture
def context_fixture(tmp_path):
    context = tmp_path / 'context'
    context.mkdir()
    # Copy only named public inputs, never recurse through the real checkout.
    for name in sorted(REQUIRED_FILES | {'.dockerignore'}):
        target = context / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)

    parents = {Path('.')}
    for name in REQUIRED_FILES:
        parents.update(Path(name).parents)
    marker = 'packaging-canary-' + uuid.uuid4().hex
    canaries = set()
    for parent in parents:
        for name in (
            '.env', 'auth.json', '.ssh/id_rsa', 'private.pem',
            'workspace.sqlite3', 'data/raw-input.csv', 'logs/private.log',
            '__pycache__/local.pyc', '.cache/session.json',
            '.venv/pyvenv.cfg', 'node_modules/fixture/index.js',
            'node_modules/.modules.yaml', 'dist/fixture.js',
            'local-not-reviewed.py', 'local-not-reviewed.tsx',
            'tsconfig.private.json', 'vite.config.private.ts',
            'unreviewed/nested.txt', 'provider-response.json',
            '.git/config', 'fixture.test.tsx',
            '0' * 64 + '.png',
        ):
            relative = (parent / name).as_posix()
            assert relative not in REQUIRED_FILES
            target = context / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(marker + ':' + relative, encoding='utf-8')
            canaries.add(relative)
    return context, canaries, marker


def assert_public_context(files, context, canaries, marker):
    assert not (files.keys() & canaries), sorted(files.keys() & canaries)
    assert set(files) == REQUIRED_FILES, {
        'unexpected': sorted(files.keys() - REQUIRED_FILES),
        'missing': sorted(REQUIRED_FILES - files.keys()),
    }
    for name, content in files.items():
        assert marker.encode() not in content, name
        assert hashlib.sha256(content).digest() == hashlib.sha256(
            (context / name).read_bytes()
        ).digest(), name


def test_sdk_archive_excludes_unreviewed_files_under_every_public_parent(context_fixture):
    """A directory or extension-wide exception must not admit private siblings."""
    from docker.utils.build import tar

    context, canaries, marker = context_fixture
    with tar(str(context), exclude=(context / '.dockerignore').read_text().splitlines()) as archive:
        with tarfile.open(fileobj=archive) as content:
            # Docker's SDK always sends the control file; it is not a COPY input.
            files = {
                item.name: content.extractfile(item).read()
                for item in content.getmembers()
                if item.isfile() and item.name != '.dockerignore'
            }
    assert_public_context(files, context, canaries, marker)


@pytest.mark.skipif(
    os.environ.get('LAB_DOCKER_ACCEPTANCE') != '1',
    reason='Actual build context export requires explicit Docker acceptance opt-in.',
)
def test_actual_docker_context_exports_exact_public_inputs(context_fixture, tmp_path):
    """BuildKit must exclude host modules, secrets and future unreviewed assets."""
    context, canaries, marker = context_fixture
    docker = os.environ.get('LAB_DOCKER_CLI') or shutil.which('docker')
    assert docker, 'Set LAB_DOCKER_CLI to the installed Docker CLI.'
    exported = tmp_path / 'exported'
    command = [
        docker, 'build', '--file', '-', '--network=none', '--progress=plain',
        '--output', 'type=local,dest=' + str(exported), str(context),
    ]
    result = subprocess.run(
        command, input='FROM scratch\nCOPY . /\n', text=True,
        encoding='utf-8', errors='replace', capture_output=True, timeout=90,
        env={**os.environ, 'BUILDX_GIT_INFO': 'false'},
    )
    (tmp_path / 'docker-context-build.log').write_text(
        result.stdout + result.stderr, encoding='utf-8'
    )
    assert result.returncode == 0, result.stdout + result.stderr
    files = {
        path.relative_to(exported).as_posix(): path.read_bytes()
        for path in exported.rglob('*') if path.is_file()
    }
    (tmp_path / 'exported-paths.json').write_text(
        json.dumps(sorted(files), indent=2), encoding='utf-8'
    )
    print(f'Actual Docker export: {len(files)} files; {len(canaries)} fake canaries tested; evidence {tmp_path}')
    assert_public_context(files, context, canaries, marker)
