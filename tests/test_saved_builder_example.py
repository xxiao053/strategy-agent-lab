"""The portable example must close over genuine records and reviewed image assets."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'examples/builder/cup-complete'


def test_complete_builder_example_has_traceable_full_run_and_asset_closure():
    example = json.loads((ROOT / 'project.json').read_text(encoding='utf-8'))
    assert example['schema'] == 'saved-builder-example-v1'
    assert len(example['messages']) == 5
    assert len(example['builds']) == len(example['runs']) == 1
    build, run = example['builds'][0], example['runs'][0]
    assert run['status'] == 'completed'
    assert run['completed_sessions'] == run['total_sessions'] == len(run['curve']) == 718
    assert len(run['assumptions']['symbols']) == 40
    assert run['assumptions']['start'] == '2024-01-02'
    assert run['assumptions']['end'] == '2026-11-10'
    assert run['curve'][-1]['equity'] == 176188.3
    assert len(run['trades']) == 56
    assert run['build_id'] == build['id']
    checks = example['independent_checks']
    assert checks['build_hash'] == build['original_build_hash']
    assert checks['run_hash'] == run['original_run_hash']
    assert checks['implementation_cases'] == 26
    assert build['validation']['test_evidence'] == 'generated_self_report'
    for file in build['files']:
        assert hashlib.sha256(file['text'].encode()).hexdigest() == file['sha256']
    images = {im['sha256'] for decision in run['decisions'] for im in decision['images']}
    assert len(images) == checks['images'] == 105
    assert {path.stem for path in (ROOT / 'images').iterdir()} == images
    for digest in images:
        data = (ROOT / 'images' / (digest + '.png')).read_bytes()
        assert data.startswith(b'\x89PNG\r\n\x1a\n')
        assert hashlib.sha256(data).hexdigest() == digest


def test_portable_records_exclude_runtime_data_and_spending_authorizations():
    example = json.loads((ROOT / 'project.json').read_text(encoding='utf-8'))
    excluded = {'records', 'requests', 'connection_id', 'model_roles', 'api_key', 'budget',
                'authorized', 'market', 'inputs', 'raw_response', 'provider_response'}
    def check(value):
        if isinstance(value, dict):
            assert not (value.keys() & excluded)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(example)


def test_smaller_nvda_revision_is_preserved_as_a_distinct_portable_example():
    root=ROOT.parent/'nvda-revision'
    example=json.loads((root/'project.json').read_text(encoding='utf-8'))
    assert example['id']=='nvda-revision' and len(example['versions'])==2
    assert [v['number'] for v in example['versions']]==[2,3]
    assert len(example['builds'])==len(example['runs'])==2
    assert all(r['assumptions']['symbols']==['NVDA'] and r['total_sessions']==32 and r['status']=='completed' for r in example['runs'])
    assert [next(t['quantity'] for t in r['trades'] if t['action']=='buy') for r in example['runs']]==[100,50]
    images={im['sha256'] for r in example['runs'] for d in r['decisions'] for im in d['images']}
    assert {p.stem for p in (root/'images').iterdir()}==images
    for sha in images:assert hashlib.sha256((root/'images'/(sha+'.png')).read_bytes()).hexdigest()==sha
