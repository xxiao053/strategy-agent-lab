import copy
from types import SimpleNamespace
import pytest
from lab.contracts import Bar
from lab.execution_contract import Manifest,validate_decision
from lab.project_runner import simulate
from tests.test_project_execution import manifest,proposal


def policy(**changes):
    return dict(mode='risk-managed',risk_fraction=.25,max_weight=1.,max_positions=10,
                entry_gap_limit=.01,commission=.0005,slippage=.0005,
                progress_units=1.,stagnation_sessions=30,trailing_stop_units=0.,**changes)


def candidate(cid='one',**changes):
    return dict(candidate_id=cid,stop=90.,target=150.,volatility_unit=5.,
                dates={'signal':'2024-01-03'},facts={'pattern':'fixture'},**changes)


def managed_manifest(model=False,changes=None):
    return Manifest.model_validate(dict(manifest(model),account={**policy(),**(changes or {})}))


def entry(symbol='SPY',**changes):
    return dict(symbol=symbol,action='buy',explanation='Approved entry',sizing={'shares':0},
                judgment=None,candidates=[candidate()],priority=1.,**changes)


def data(closes=(100,100,100,100),opens=None,symbols=('SPY',)):
    opens=opens or closes
    rows=[Bar(date=f'2024-01-0{i+2}',open=o,high=max(o,c)+1,low=min(o,c)-1,close=c,volume=100)
          for i,(o,c) in enumerate(zip(opens,closes))]
    return {s:rows for s in symbols}


CONFIG=dict(start='2024-01-03',end='2024-01-05',initial_cash=100000,fee_rate=.0005)


class OneEntry:
    def decide(self,c):return {'proposals':[entry()] if c['cutoff']=='2024-01-03' else [],'state':{}}


def test_risk_policy_generates_original_fee_gap_and_reservation_sized_order():
    result=simulate(data(),managed_manifest(),OneEntry(),CONFIG,compact_inputs=True)
    fill=result['trades'][0]
    # floor(100000/(101*1.0005))=989, paid at100.05 with49.47commission.
    assert fill['quantity']==989 and fill['price']==pytest.approx(100.05)
    assert fill['fee']==49.47 and result['curve'][-1]['cash']==1001.08
    assert result['positions']=={'SPY':989} and result['curve'][-1]['equity']==99901.08
    assert fill['date']=='2024-01-04' and fill['decision_id']==result['decisions'][0]['id']
    assert result['orders'][0]['reserved']==99938.95


@pytest.mark.parametrize('opening',[102,89,151])
def test_managed_entry_gap_cancels_without_resizing_or_altering_cash(opening):
    result=simulate(data(opens=(100,100,opening,100)),managed_manifest(),OneEntry(),CONFIG)
    assert result['orders'][0]['reason']=='cancelled_gap' and not result['trades']
    assert result['curve'][-1]['cash']==100000 and result['positions']=={}


@pytest.mark.parametrize('closing,reason',[(89,'stop_close'),(151,'target_close')])
def test_managed_close_exit_fills_next_open_and_keeps_traceable_decision(closing,reason):
    result=simulate(data(closes=(100,100,closing,110),opens=(100,100,100,110)),managed_manifest(),OneEntry(),CONFIG)
    buy,sell=result['trades']
    assert sell['date']=='2024-01-05' and sell['price']==pytest.approx(109.945)
    assert sell['reason']==reason and result['positions']=={}
    exit_decision=next(d for d in result['decisions'] if d['id']==sell['decision_id'])
    assert exit_decision['cutoff']=='2024-01-04' and exit_decision['proposal']['action']=='sell'


def test_managed_stagnation_is_progress_based_not_unconditional_holding_age():
    m=managed_manifest(changes={'stagnation_sessions':2})
    flat=simulate(data(),m,OneEntry(),CONFIG)
    growing=simulate(data(closes=(100,100,105,110),opens=(100,100,100,100)),m,OneEntry(),CONFIG)
    assert flat['orders'][-1]['reason']=='stagnation' and flat['orders'][-1]['status']=='unfilled'
    assert len(growing['orders'])==1 and growing['positions']=={'SPY':989}


def test_managed_priority_and_slots_prevent_unexecutable_model_calls():
    judged=[]
    class Programs:
        def decide(self,c):
            return {'proposals':[{**entry('SPY'),'priority':1.,'judgment':'criteria'},
                                 {**entry('QQQ'),'priority':2.,'judgment':'criteria'}] if c['cutoff']=='2024-01-03' else [],'state':{}}
    def judge(d,c,p):judged.append(p['symbol']);return {'verdict':'pass','selected_candidate_id':'one'}
    result=simulate(data(symbols=('SPY','QQQ')),managed_manifest(True,{'max_positions':1}),Programs(),CONFIG,judge=judge)
    assert judged==['QQQ'] and result['positions']=={'QQQ':989}
    assert next(d for d in result['decisions'] if d['proposal']['symbol']=='SPY')['status']=='sizing_rejected'


def test_managed_contract_rejects_invented_cash_unapproved_candidates_and_future_evidence():
    m=managed_manifest()
    for value in [{**entry(),'sizing':{'shares':999}}, {**entry(),'account':{'cash':999}},
                  {**entry(),'candidates':[candidate(),candidate()]}]:
        with pytest.raises(ValueError):validate_decision({'proposals':[value],'state':{}},m,['SPY'])
    with pytest.raises(ValueError):validate_decision({'proposals':[entry()],'state':{}},Manifest.model_validate(manifest()),['SPY'])
    class Future:
        def decide(self,c):return {'proposals':[{**entry(),'candidates':[{**candidate(),'dates':{'signal':'2030-01-01'}}]}],'state':{}}
    with pytest.raises(ValueError,match='date|Date|cutoff'):simulate(data(),m,Future(),CONFIG)
    with pytest.raises(ValueError,match='fee|Fee|commission'):simulate(data(),m,OneEntry(),dict(CONFIG,fee_rate=0))


def test_managed_account_matches_existing_engine_for_identical_fixed_plans():
    from lab.account import Account
    m=managed_manifest();market=data(closes=(100,100,89,110),opens=(100,100,100,110))
    result=simulate(market,m,OneEntry(),CONFIG)
    reference=Account(100000);rules=SimpleNamespace(**{k:v for k,v in policy().items() if k!='mode'})
    for row in market['SPY'][1:]:
        reference.open_day(row.date,{'SPY':row.open},rules);reference.close_day(row.date,{'SPY':row.close},rules)
        if row.date=='2024-01-03':reference.enter('SPY',row.date,row.close,90,rules,pattern=candidate())
    assert [p['equity'] for p in result['curve']]==[p['equity'] for p in reference.curve]
    assert result['curve'][-1]['cash']==reference.cash


@pytest.mark.parametrize('verdict',['pass','fail','insufficient_evidence'])
def test_managed_explicit_sell_obeys_its_approved_model_judgment(verdict):
    calls=[]
    class Program(OneEntry):
        def decide(self,c):
            if c['cutoff']=='2024-01-04':
                return {'proposals':[proposal('sell',989,'Check approved exit evidence')],'state':{}}
            return super().decide(c)
    def judge(d,c,p):calls.append(p['action']);return {'verdict':verdict}
    result=simulate(data(),managed_manifest(True),Program(),CONFIG,judge=judge)
    assert calls==['sell']
    assert len(result['trades'])==(2 if verdict=='pass' else 1)
    assert result['decisions'][-1]['model']['verdict']==verdict


def test_managed_fill_observations_keep_standard_gross_and_explanation():
    observed=[]
    class Program(OneEntry):
        def decide(self,c):
            observed.extend(c['previous_orders'])
            return super().decide(c)
    result=simulate(data(),managed_manifest(),Program(),CONFIG)
    filled=observed[0]
    assert filled['gross']==98949.45
    assert filled['explanation']=='Approved entry'
    assert result['trades'][0]['gross']==98949.45


def test_managed_construction_smoke_includes_the_runtime_account_fields(tmp_path):
    import json,subprocess
    from lab.execution_contract import verify_execution_contract
    method={'rules':[{'rule':'Approved managed policy'}],'questions':[]}
    for name,value in {'method.json':json.dumps(method),'execution.json':json.dumps(managed_manifest().model_dump(by_alias=True)),
        'strategy.py':"def decide(c):\n return {'proposals': [], 'state': {'available':c['account']['available_cash'], 'positions':c['account']['position_details']}}\n"}.items():
        (tmp_path/name).write_text(value,encoding='utf-8')
    def isolated(args):return subprocess.run(args,cwd=tmp_path,text=True,capture_output=True)
    result=verify_execution_contract(tmp_path,method,isolated)
    assert result['independent_decisions']==2
