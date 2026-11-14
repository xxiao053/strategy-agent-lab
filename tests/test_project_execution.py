import copy
import json
import subprocess
from pathlib import Path

import pytest


def manifest(model=False):
    return {'schema':'strategy-v1','entrypoint':'strategy.py:decide','warmup_bars':1,'history_bars':3,
            'responsibilities':{'code':'Entry, exit and integer share sizing from approved rules.',
                                'model':'Assess trend evidence.' if model else None},
            'judgment':{'criteria':'Pass only a rising visible close series; cite dates.',
                        'trigger':'Requested buy proposals','tools':['read_bars','price_facts'],
                        'uncertainty':'skip'} if model else None}


def proposal(action='buy',shares=3,judgment=None):
    return {'symbol':'SPY','action':action,'explanation':'Approved rule R1',
            'sizing':{'shares':shares},'judgment':judgment}


def bars():
    from lab.contracts import Bar
    return {'SPY':[Bar(date=d,open=o,high=max(o,c)+1,low=min(o,c)-1,close=c,volume=100)
                   for d,o,c in [('2024-01-02',10,10),('2024-01-03',12,13),
                                 ('2024-01-04',20,21),('2024-01-05',15,16)]]}


def test_contract_is_method_neutral_and_rejects_missing_or_extra_fields():
    from lab.execution_contract import Manifest, validate_proposals
    contract=Manifest.model_validate(manifest())
    assert contract.history_bars==3
    assert validate_proposals([proposal()],contract,['SPY'])[0]['sizing']['shares']==3
    for bad in [{**manifest(),'cup_depth':.1}, {**manifest(),'history_bars':0},
                {**manifest(),'entrypoint':'other.py:run'}, {**manifest(),'warmup_bars':True},
                {**manifest(),'judgment':manifest(True)['judgment']}]:
        with pytest.raises(ValueError):Manifest.model_validate(bad)


@pytest.mark.parametrize('change',[
    {'balance':1000},{'symbol':'BAD'},{'action':'short'}, {'sizing':{'shares':1.5}},
    {'sizing':{'shares':float('nan')}},{'sizing':{'shares':True}}, {'judgment':'assess'},
    {'explanation':''}])
def test_proposals_reject_unsafe_output(change):
    from lab.execution_contract import Manifest, validate_proposals
    with pytest.raises(ValueError):validate_proposals([{**proposal(),**change}],Manifest.model_validate(manifest()),['SPY'])


def test_duplicate_proposals_and_non_json_output_fail_closed():
    from lab.execution_contract import Manifest, validate_proposals, parse_output
    contract=Manifest.model_validate(manifest())
    with pytest.raises(ValueError):validate_proposals([proposal(),proposal('sell')],contract,['SPY'])
    for text in ['NaN','[]\nhello','{"x":1,"x":2}', '['+' '*70000+']']:
        with pytest.raises(ValueError):parse_output(text)


def test_account_next_open_gap_cash_fee_rounding_and_no_final_liquidation():
    from lab.project_account import Account
    a=Account('100.00','0.005')
    order=a.order(proposal(shares=9),'d1','2024-01-02')
    assert a.snapshot({'SPY':10})=={'cash':100.0,'equity':100.0,'positions':{}}
    a.fill([order],{'SPY':12},'2024-01-03')
    assert order['status']=='cancelled' and order['reason']=='insufficient_cash_at_open'
    order=a.order(proposal(shares=3),'d2','2024-01-03')
    a.fill([order],{'SPY':20},'2024-01-04')
    assert order['fee']==.30 and order['price']==20 and order['quantity']==3
    assert a.snapshot({'SPY':21})=={'cash':39.70,'equity':102.70,'positions':{'SPY':3}}
    sell=a.order(proposal('sell',4),'d3','2024-01-04')
    a.fill([sell],{'SPY':15},'2024-01-05')
    assert sell['status']=='cancelled' and a.positions=={'SPY':3}
    sell=a.order(proposal('sell',2),'d4','2024-01-04')
    a.fill([sell],{'SPY':15},'2024-01-05')
    assert a.snapshot({'SPY':16})=={'cash':69.55,'equity':85.55,'positions':{'SPY':1}}


def test_account_cannot_fill_on_signal_date_or_sell_without_shares():
    from lab.project_account import Account
    a=Account(100,0)
    order=a.order(proposal(),'d','2024-01-03')
    with pytest.raises(ValueError):a.fill([order],{'SPY':10},'2024-01-03')
    assert not a.eligible(proposal('sell'),{'SPY':10})
    assert not a.eligible(proposal(shares=11),{'SPY':10})


def test_build_seal_rejects_tampering_and_legacy_builds():
    from lab.execution_contract import seal_build, resolve_build
    method={'rules':[{'rule':'R1'}],'questions':[]}
    artifacts=[{'name':'strategy.py','text':'def decide(context): return []'},
               {'name':'execution.json','text':json.dumps(manifest())},
               {'name':'method.json','text':json.dumps(method)}]
    build={'id':'b','status':'completed','version':1,'artifacts':artifacts}
    project={'versions':[{'version':1,'method':method}],'builds':[build]}
    with pytest.raises(ValueError,match='rebuild|Rebuild'):resolve_build(project,'b')
    build['execution_hash']=seal_build(artifacts,method)
    assert resolve_build(project,'b')[1]['method']==method
    build['artifacts'][0]['text']+='\n# changed'
    with pytest.raises(ValueError,match='changed|hash'):resolve_build(project,'b')
    with pytest.raises(ValueError):resolve_build(project,'other-project-build')
    for name in ['../strategy.py','/strategy.py','C:/x.py','x\\y.py','x/../strategy.py']:
        with pytest.raises(ValueError):seal_build([*artifacts,{'name':name,'text':'pass'}],method)


def test_evaluator_passes_only_cutoff_context_through_isolate_and_checks_source(tmp_path):
    from lab.project_evaluator import IsolatedEvaluator
    source=[{'name':'strategy.py','text':'raise RuntimeError("MUST NEVER IMPORT IN HOST")'}]
    context={'cutoff':'2024-01-03','bars':{'SPY':[b.model_dump() for b in bars()['SPY'][:2]]},'account':{}}
    calls=[]
    class Boundary:
        def __init__(self,work,home):self.work=work
        def probe(self):calls.append('probe')
        def run(self,args):
            calls.append('run')
            assert repr(str(self.work)) not in args[-1], 'Boundary must support remapped container cwd without rewriting Python source.'
            assert sorted(p.name for p in self.work.iterdir())==['context.json','strategy.py']
            assert json.loads((self.work/'context.json').read_text())==context
            assert not (self.work/'full-history.json').exists()
            return subprocess.CompletedProcess(args,0,json.dumps({'proposals':[proposal()],'state':{}}),'')
    result=IsolatedEvaluator(tmp_path,source,boundary_factory=Boundary).decide(context)
    assert result=={'proposals':[proposal()],'state':{}} and calls==['probe','run']
    class Tampering(Boundary):
        def run(self,args):
            (self.work/'strategy.py').write_text('pass')
            return subprocess.CompletedProcess(args,0,'[]','')
    with pytest.raises(ValueError,match='changed'):
        IsolatedEvaluator(tmp_path,source,boundary_factory=Tampering).decide(context)


def test_shared_simulator_cutoff_and_distinct_methods_preserve_open_positions():
    from lab.execution_contract import Manifest
    from lab.project_runner import simulate
    seen=[]
    class Program:
        def __init__(self,kind):self.kind=kind
        def decide(self,context):
            seen.append(context)
            assert max(b['date'] for b in context['bars']['SPY'])==context['cutoff']
            if self.kind=='entry' and context['cutoff']=='2024-01-03':return {'proposals':[proposal()],'state':{}}
            if self.kind=='exit' and context['cutoff']=='2024-01-04':return {'proposals':[proposal()],'state':{}}
            return {'proposals':[],'state':{}}
    config={'start':'2024-01-03','end':'2024-01-05','initial_cash':100,'fee_rate':0}
    a=simulate(bars(),Manifest.model_validate(manifest()),Program('entry'),config)
    b=simulate(bars(),Manifest.model_validate(manifest()),Program('exit'),config)
    assert a['curve'][-1]['equity']==88 and b['curve'][-1]['equity']==103
    assert a['positions']=={'SPY':3} and len(a['trades'])==1
    assert a['trades'][0]['date']=='2024-01-04'
    assert len(seen[-1]['bars']['SPY'])==3


def test_final_day_orders_unfilled_and_cancellation_keeps_completed_evidence():
    from lab.execution_contract import Manifest
    from lab.project_runner import simulate
    class Program:
        def decide(self,c):return {'proposals':[proposal(shares=1)],'state':{'anchor':c['cutoff']}}
    config={'start':'2024-01-03','end':'2024-01-05','initial_cash':100,'fee_rate':0}
    a=simulate(bars(),Manifest.model_validate(manifest()),Program(),config)
    assert a['orders'][-1]['reason']=='no_next_session' and a['orders'][-1]['status']=='unfilled'
    progress=[]
    b=simulate(bars(),Manifest.model_validate(manifest()),Program(),config,
               on_progress=lambda r:progress.append(copy.deepcopy(r)),cancelled=lambda:len(progress)>0)
    assert b['status']=='cancelled' and len(b['decisions'])==1
    assert b['state']=={'anchor':'2024-01-03'}


def test_strategy_state_is_json_bounded_and_not_account_authority():
    from lab.execution_contract import validate_state
    assert validate_state({'entry':{'date':'2024-01-03','anchor':20}})['entry']['anchor']==20
    for value in [{'x':float('nan')},{'x':'x'*17000}, {'x':[[[[[[[[[1]]]]]]]]]}]:
        with pytest.raises(ValueError):validate_state(value)


def test_independent_builder_contract_check_uses_isolate_and_rejects_invalid_output(tmp_path):
    from lab.execution_contract import verify_execution_contract
    method={'rules':[{'rule':'R1'}],'questions':[]}
    (tmp_path/'method.json').write_text(json.dumps(method))
    (tmp_path/'execution.json').write_text(json.dumps(manifest()))
    (tmp_path/'strategy.py').write_text('raise RuntimeError("never host import")')
    calls=[]
    def isolated(args):
        calls.append(args)
        return subprocess.CompletedProcess(args,0,'{"proposals":[],"state":{}}','')
    result=verify_execution_contract(tmp_path,method,isolated)
    assert result['execution_contract']=='strategy-v1' and result['independent_decisions']==2 and len(calls)==2
    assert not (tmp_path/'contract-context.json').exists()
    def bad(args):return subprocess.CompletedProcess(args,0,'{"proposals":[],"state":{},"cash":500}','')
    with pytest.raises(ValueError):verify_execution_contract(tmp_path,method,bad)


def test_mxc_boundary_fails_closed_and_does_not_receive_provider_credentials(tmp_path,monkeypatch):
    from lab.project_evaluator import MXCBoundary
    work=tmp_path/'work';home=tmp_path/'home';work.mkdir();home.mkdir()
    monkeypatch.setenv('OPENAI_API_KEY','private-probe-key')
    monkeypatch.setattr('lab.project_evaluator.shutil.which',lambda _:None)
    with pytest.raises(ValueError,match='No host fallback'):MXCBoundary(work,home)
    monkeypatch.setattr('lab.project_evaluator.shutil.which',lambda _:'codex')
    def bounded(args,**kw):
        assert args[:4]==['codex','sandbox','--permission-profile','builder']
        assert 'OPENAI_API_KEY' not in kw['env'] and kw['output_limit']==65536
        assert kw['timeout']==20 and kw['cwd']==work
        return subprocess.CompletedProcess(args,0,'FAILED','')
    monkeypatch.setattr('lab.project_evaluator.bounded_run',bounded)
    with pytest.raises(ValueError,match='probe failed'):MXCBoundary(work,home).probe()


def test_missing_data_and_unaligned_sessions_are_not_no_trade():
    from lab.execution_contract import Manifest
    from lab.project_runner import simulate
    config={'start':'2024-01-03','end':'2024-01-05','initial_cash':100,'fee_rate':0}
    with pytest.raises(ValueError,match='data|session|history'):
        simulate({'SPY':bars()['SPY'][2:]},Manifest.model_validate(manifest()),None,config)


def test_pending_buy_cash_is_reserved_before_later_paid_judgment():
    from lab.execution_contract import Manifest
    from lab.project_runner import simulate
    data=bars();data['QQQ']=data['SPY']
    judged=[]
    class Program:
        def decide(self,c):return {'proposals':[proposal(shares=6,judgment='check'),{**proposal(shares=6,judgment='check'),'symbol':'QQQ'}] if c['cutoff']=='2024-01-03' else [],'state':{}}
    result=simulate(data,Manifest.model_validate(manifest(True)),Program(),
                    {'start':'2024-01-03','end':'2024-01-05','initial_cash':100,'fee_rate':0},
                    judge=lambda d,c,p:(judged.append(p['symbol']) or {'verdict':'pass'}))
    assert judged==['SPY'] and result['decisions'][1]['status']=='sizing_rejected'


def test_failed_judgment_records_distinct_outcome_and_full_input_state():
    from lab.execution_contract import Manifest
    from lab.project_runner import simulate
    saved=[]
    class Program:
        def decide(self,c):return {'proposals':[proposal(judgment='check')],'state':{'anchor':13}}
    def judge(*args):raise ValueError('infrastructure_failure: receipt retained')
    with pytest.raises(ValueError,match='infrastructure_failure'):
        simulate(bars(),Manifest.model_validate(manifest(True)),Program(),
                 {'start':'2024-01-03','end':'2024-01-05','initial_cash':100,'fee_rate':0},
                 judge=judge,on_progress=lambda r:saved.append(r))
    assert saved[-1]['decisions'][0]['status']=='infrastructure_failure'
    assert saved[-1]['inputs']['2024-01-03']['state']=={}
    assert saved[-1]['state']=={'anchor':13}


def test_final_session_does_not_spend_on_an_unfillable_proposal():
    from lab.execution_contract import Manifest
    from lab.project_runner import simulate
    class Program:
        def decide(self,c):return {'proposals':[proposal(judgment='check')],'state':{}}
    def judge(*args):pytest.fail('No next session exists; do not spend.')
    result=simulate(bars(),Manifest.model_validate(manifest(True)),Program(),
                    {'start':'2024-01-05','end':'2024-01-05','initial_cash':100,'fee_rate':0},judge=judge)
    assert result['orders'][0]['reason']=='no_next_session' and result['decisions'][0]['status']=='unfilled'


def test_failure_cancels_earlier_same_day_orders_and_retains_account_checkpoint():
    from lab.execution_contract import Manifest
    from lab.project_runner import simulate
    data=bars();data['QQQ']=data['SPY'];saved=[]
    class Program:
        def decide(self,c):return {'proposals':[proposal(shares=1),{**proposal(shares=1,judgment='check'),'symbol':'QQQ'}],'state':{}}
    def judge(*args):raise ValueError('invalid_response: stopped')
    with pytest.raises(ValueError):
        simulate(data,Manifest.model_validate(manifest(True)),Program(),
                 {'start':'2024-01-03','end':'2024-01-05','initial_cash':100,'fee_rate':0},judge=judge,on_progress=saved.append)
    assert saved[-1]['orders'][0]['status']=='cancelled'
    assert saved[-1]['orders'][0]['reason']=='execution_failed'
    assert saved[-1]['curve'][-1]['equity']==100 and saved[-1]['curve'][-1]['date']=='2024-01-03'


def test_actual_evidence_limit_preserves_every_paid_judgment_and_prior_fill():
    from datetime import date,timedelta
    from lab.contracts import Bar
    from lab.execution_contract import Manifest,canonical
    from lab.project_runner import simulate
    symbols=['SPY','QQQ','AAPL','MSFT','NVDA','META','GOOG','AMZN','AMD','TSLA']
    rows=[Bar(date=(date(2020,1,1)+timedelta(days=i)).isoformat(),open=10,high=11,low=9,close=10,volume=1000000) for i in range(540)]
    data={s:rows for s in symbols};paid=[];saved=[]
    class Program:
        def decide(self,c):
            return {'proposals':[{**proposal(shares=1,judgment='affordable review' if s=='SPY' else None),'symbol':s} for s in symbols],
                    'state':{'remember':'x'*16000}}
    def judge(d,c,p):
        paid.append(d['id'])
        assert c['account']['cash']>=10
        return {'verdict':'pass','reason':'visible evidence','evidence':[{'symbol':'SPY','date':c['cutoff']}],'request_ids':['receipt-'+d['id']],'tools':[]}
    with pytest.raises(ValueError,match='evidence|Evidence'):
        simulate(data,Manifest.model_validate({**manifest(True),'warmup_bars':500,'history_bars':501}),Program(),
                 {'start':rows[500].date,'end':rows[-1].date,'initial_cash':1000000,'fee_rate':0},
                 judge=judge,on_progress=lambda r:saved.append(copy.deepcopy(r)))
    terminal=saved[-1]
    assert paid and terminal['trades'], 'Exercise real charged judgments and previous-session fills.'
    assert {d['id'] for d in terminal['decisions'] if d['model']}==set(paid)
    assert len(terminal['trades'])==10*(len(paid)-1)
    assert all(o['status']!='pending' for o in terminal['orders'])
    assert terminal['status']=='failed' and len(canonical(terminal).encode())<=12000000


def test_historical_mxc_config_is_readonly_and_probe_rejects_inside_writes(tmp_path,monkeypatch):
    import tomllib
    from lab.project_evaluator import MXCBoundary
    from lab.build_runtime import runtime_config
    work=tmp_path/'work';home=tmp_path/'home';work.mkdir();home.mkdir()
    monkeypatch.setattr('lab.project_evaluator.shutil.which',lambda _:'codex')
    boundary=MXCBoundary(work,home)
    config=tomllib.loads((home/'config.toml').read_text())
    assert config['permissions']['builder']['filesystem'][':workspace_roots']['.']=='read'
    assert tomllib.loads(runtime_config('http://127.0.0.1:1','x',''))['permissions']['builder']['filesystem'][':workspace_roots']['.']=='write'
    # Simulate a boundary that still permits inside writes: the real probe script must reject it.
    import ast
    scripts=[]
    def runner(args):
        scripts.append(args[-1])
        tree=ast.parse(args[-1])
        writes=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='write_text']
        assert len(writes)>=3, 'Probe outside writes, existing inside overwrite and new inside file creation.'
        return subprocess.CompletedProcess(args,2,'FAILED','')
    monkeypatch.setattr(boundary,'run',runner)
    with pytest.raises(ValueError,match='probe failed'):boundary.probe()


@pytest.mark.parametrize('attack',['count','aggregate','depth'])
def test_host_inspection_and_cleanup_bound_adversarial_filesystem(tmp_path,attack):
    from lab.project_evaluator import source_hash,bounded_cleanup
    work=tmp_path/'scope';work.mkdir()
    if attack=='count':
        for i in range(520):(work/f'f{i}.txt').write_text('x')
    elif attack=='aggregate':
        for i in range(3):(work/f'f{i}.txt').write_bytes(b'x'*900000)
    else:
        folder=work
        for i in range(10):folder=folder/'d';folder.mkdir()
    with pytest.raises(ValueError,match='limit|bounded'):source_hash(work)
    with pytest.raises(ValueError,match='retained|limit|bounded'):bounded_cleanup(work)
    assert work.exists(), 'An out-of-contract tree is retained, never sent to unbounded recursive cleanup.'
