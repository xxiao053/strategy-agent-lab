import copy
from datetime import date,timedelta
import json
from pathlib import Path
import pytest
from lab.contracts import Bar
from lab.execution_contract import Manifest,canonical,digest
from lab.project_runner import simulate
from tests.test_project_execution import manifest


def full_scope(model=False):
    original=json.loads((Path(__file__).parents[1]/'examples/cup-handle/config.json').read_text())
    days=[];day=date(2023,1,2)
    while len(days)<878:
        if day.weekday()<5:days.append(day.isoformat())
        day+=timedelta(days=1)
    rows=[Bar(date=d,open=10,high=11,low=9,close=10,volume=100) for d in days]
    data={s:rows for s in original['symbols']}
    m=Manifest.model_validate(dict(manifest(model),warmup_bars=159,history_bars=160))
    return data,m,dict(start=days[160],end=days[-1],initial_cash=100000,fee_rate=.0005)


def test_complete_forty_instrument_718_session_run_keeps_compact_cutoff_evidence():
    data,m,config=full_scope();seen=[]
    class Program:
        def decide(self,c):
            assert len(c['bars'])==40
            assert all(len(rows)==160 and rows[-1]['date']==c['cutoff'] for rows in c['bars'].values())
            if not seen:seen.append(copy.deepcopy(c))
            return {'proposals':[],'state':{}}
    result=simulate(data,m,Program(),config,compact_inputs=True)
    assert result['status']=='completed' and result['completed_sessions']==718
    assert len(result['curve'])==718 and result['curve'][-1]['equity']==100000
    assert len(canonical(result['inputs']).encode())<500000
    assert 'bars' not in result['inputs'][config['start']]
    from lab.project_history import restore_context
    from lab.market import snapshot_id
    run=dict(result,market={s:[b.model_dump() for b in rows] for s,rows in data.items()},
             frozen={'market_hash':snapshot_id(data),'manifest':m.model_dump(by_alias=True)})
    recovered=restore_context(run,config['start'])
    assert recovered==seen[0] and digest(recovered)==digest(seen[0])
    run['market']['SPY'][161]['close']=99
    with pytest.raises(ValueError,match='market|Market'):restore_context(run,config['start'])


def test_forty_symbol_model_run_can_reserve_next_session_without_requesting_unneeded_judgments():
    data,m,config=full_scope(model=True);config['end']=config['start']
    class Program:
        def decide(self,c):return {'proposals':[],'state':{}}
    result=simulate(data,m,Program(),config,compact_inputs=True)
    assert result['status']=='completed' and result['completed_sessions']==1


def test_api_options_accept_complete_original_universe():
    from lab.project_runs import RunOptions
    original=json.loads((Path(__file__).parents[1]/'examples/cup-handle/config.json').read_text())
    options=RunOptions(build_id='complete',symbols=original['symbols'],start=original['start'],end=original['end'],initial_cash=100000,fee_rate=.0005)
    assert len(options.symbols)==40 and options.end=='2026-11-10'


def test_compact_reference_rejects_modified_window_or_conflicting_inline_data():
    from lab.project_history import compact_context,restore_context
    from lab.market import snapshot_id
    data,m,c=full_scope();rows=data['SPY'][1:161]
    context=dict(schema='strategy-v1',cutoff=c['start'],bars={'SPY':[b.model_dump() for b in rows]},account={},state={},previous_orders=[])
    saved=compact_context(context,160)
    run={'inputs':{c['start']:saved},'market':{'SPY':[b.model_dump() for b in data['SPY']]},
         'frozen':{'market_hash':snapshot_id({'SPY':data['SPY']}),'manifest':m.model_dump(by_alias=True)}}
    assert restore_context(run,c['start'])==context
    saved['bars_ref']['history_bars']=161
    with pytest.raises(ValueError):restore_context(run,c['start'])
    saved['bars_ref']['history_bars']=160;saved['bars']={}
    with pytest.raises(ValueError):restore_context(run,c['start'])


def test_large_cutoff_input_crosses_evaluator_and_container_pack_without_host_execution(tmp_path):
    import subprocess,tarfile,io
    from lab.project_evaluator import IsolatedEvaluator
    from lab.docker_policy import pack_files
    context={'cutoff':'2024-01-03','bars':{},'state':{'fixture':'x'*2000000}}
    class Boundary:
        def __init__(self,work,home):self.work=work
        def probe(self):pass
        def run(self,args):
            files={p.name:p.read_text(encoding='utf-8') for p in self.work.iterdir()}
            payload=pack_files(files)
            with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
                assert json.load(archive.extractfile('context.json'))==context
            return subprocess.CompletedProcess(args,0,'{"proposals":[],"state":{}}','')
    result=IsolatedEvaluator(tmp_path,[{'name':'strategy.py','text':'raise RuntimeError("never host execution")'}],boundary_factory=Boundary).decide(context)
    assert result=={'proposals':[],'state':{}} and list(tmp_path.iterdir())==[]
    with pytest.raises(ValueError):pack_files({'context.json':'x'*(8*1024*1024+1)})
    with pytest.raises(ValueError):pack_files({'other.json':'x'*2000000})


def test_project_runs_store_compact_inputs_and_resolve_them_for_evidence(tmp_path,monkeypatch):
    from tests.test_project_runs_api import prepared,body
    from tests.test_project_execution import bars,proposal
    from lab.project_evidence import resolve_evidence
    from lab.project_charts import render_chart,verify_chart_source
    from lab.project_history import restore_context
    store,pid,runs=prepared(tmp_path);data,_,_=full_scope()
    market={s:bars()['SPY'] for s in data}
    monkeypatch.setattr(runs,'load_market',lambda *args:(market,{}))
    monkeypatch.setattr('lab.project_runs.threading.Thread.start',lambda self:None)
    class Program:
        def __init__(self,*args):pass
        def decide(self,c):return {'proposals':[proposal()] if c['cutoff']=='2024-01-03' else [],'state':{}}
    monkeypatch.setattr(runs,'evaluator_factory',Program)
    summary=runs.start(pid,dict(body(),symbols=list(market)));runs.execute(pid,summary['id'])
    result=runs.get(pid,summary['id'])
    assert result['status']=='completed' and 'bars_ref' in result['inputs']['2024-01-03']
    evidence=resolve_evidence(store,pid,{'run_id':summary['id'],'decision_id':'2024-01-03-1'})
    assert evidence['input_hash']==result['decisions'][0]['input_hash']
    context=restore_context(result,'2024-01-03')
    assert set(context['bars'])==set(market)
    verify_chart_source(result,result['decisions'][0],render_chart(context,'SPY'))
