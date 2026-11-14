import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab.contracts import Strategy, CandidateBatch
from lab.strategy import shortlist, validate_batch, mean_true_range, screen
from lab.contracts import Bar
from datetime import date, timedelta
from lab.market import load_snapshot
from lab.account import Account

ROOT = Path(__file__).resolve().parents[1]


def pattern():
    return {'candidate_id':'fixed-example','stop':95,'target':120,'volatility_unit':2}


def entered(strategy=None):
    s = strategy or Strategy()
    a = Account(100000)
    assert a.enter('A', '2024-01-01', 100, 95, s, pattern=pattern())
    a.open_day('2024-01-02', {'A':100/1.0005}, s)
    return a, s


def test_stagnation_uses_fifteen_no_progress_days_not_total_age():
    a,s = entered()
    for n in range(14):
        a.close_day(f'day-{n}', {'A':100.5}, s)
    assert not [o for o in a.orders if o['side']=='sell']
    a.close_day('fifteenth', {'A':102}, s)
    assert a.positions['A']['stagnant_sessions']==0
    for n in range(15):
        a.close_day(f'flat-{n}', {'A':101.5}, s)
    orders = [o for o in a.orders if o['side']=='sell']
    assert len(orders)==1 and orders[0]['reason']=='stagnation'
    a.close_day('still-flat', {'A':101}, s)
    assert len([o for o in a.orders if o['side']=='sell'])==1


def test_progress_can_continue_beyond_forty_sessions_and_survive_restart():
    a,s = entered()
    for n in range(1,46):
        a.close_day(f'progress-{n}', {'A':100+.25*n}, s)
        a = Account(100000, json.loads(json.dumps(a.dump())))
    assert a.positions['A']['held_sessions']==45
    assert a.positions['A']['volatility_unit']==2
    assert not [o for o in a.orders if o['side']=='sell']


@pytest.mark.parametrize('close,reason', [(94,'stop_close'),(120,'target_close')])
def test_price_exits_take_priority_and_fill_only_next_open(close,reason):
    a,s = entered()
    a.positions['A']['stagnant_sessions']=14
    a.close_day('signal', {'A':close}, s)
    assert 'A' in a.positions
    assert a.orders[-1]['reason']==reason
    a.open_day('zz-next', {'A':90}, s)
    assert not a.positions and len(a.trades)==1
    assert a.trades[0]['candidate_id']=='fixed-example'
    assert a.trades[0]['exit_price']==pytest.approx(89.955)


def test_invalid_frozen_exit_facts_cannot_create_order():
    a=Account(100000)
    with pytest.raises(ValueError):
        a.enter('A','2024-01-01',100,95,Strategy(),pattern={**pattern(),'volatility_unit':0})
    assert not a.orders


@pytest.mark.market_data
def test_shortlist_is_stable_bound_to_prefix_and_numerically_verified():
    s=Strategy()
    bars=load_snapshot(ROOT,['QQQ'],'2024-01-02','2026-11-10')['QQQ']
    i=next(i for i,b in enumerate(bars) if b.date=='2024-11-06')
    choices=shortlist(bars,i,s,'QQQ')
    assert 1<=len(choices)<=3
    assert choices==shortlist(bars[:i+1],i,s,'QQQ')
    assert len({c['candidate_id'] for c in choices})==len(choices)
    for c in choices:
        assert c['target']>bars[i].close>c['stop']
        assert c['right_rim']<bars[i].date
        assert c['volatility_unit']>0
        assert c['numeric_checks'] and all(x['passed'] for x in c['numeric_checks'])
    assert mean_true_range(bars,i,20)==pytest.approx(6.674501037597656)


def assessment(candidate,verdict='pass'):
    return dict(candidate_id=candidate['candidate_id'],verdict=verdict,
        checks=[dict(name=n,verdict=verdict,reason='Explicit offline fixture',start_date=candidate['handle_start'] if n=='handle' else candidate['left_rim'],end_date=candidate['handle_end'] if n!='cup' else candidate['right_rim'])
                for n in ['cup','handle','coherence']],evidence='Explicit offline fixture',missing_information=[])


@pytest.mark.market_data
def test_batch_must_cover_exact_candidate_ids_and_cannot_invent_geometry():
    s=Strategy();bars=load_snapshot(ROOT,['QQQ'],'2024-01-02','2026-11-10')['QQQ']
    i=next(i for i,b in enumerate(bars) if b.date=='2024-11-06')
    choices=shortlist(bars,i,s,'QQQ')
    obj={'assessments':[assessment(c) for c in choices]}
    batch=CandidateBatch.model_validate(obj)
    assert validate_batch(batch,choices,bars,i)['pattern']['candidate_id']==choices[0]['candidate_id']
    obj['assessments'][0]['candidate_id']='not-offered'
    with pytest.raises(ValueError,match='candidate'):
        validate_batch(CandidateBatch.model_validate(obj),choices,bars,i)
    obj['assessments'][0]['anchors']={'left_rim':'1900-01-01','right_rim':'2099-01-01'}
    with pytest.raises(ValidationError):CandidateBatch.model_validate(obj)


@pytest.mark.market_data
def test_candidate_id_does_not_license_evidence_from_unrelated_region():
    s=Strategy();bars=load_snapshot(ROOT,['QQQ'],'2024-01-02','2026-11-10')['QQQ']
    i=next(i for i,b in enumerate(bars) if b.date=='2024-11-06')
    choices=shortlist(bars,i,s,'QQQ');obj={'assessments':[assessment(c) for c in choices]}
    obj['assessments'][0]['checks'][1]['start_date']=choices[0]['left_rim']
    with pytest.raises(ValueError,match='region'):
        validate_batch(CandidateBatch.model_validate(obj),choices,bars,i)


def test_schema_does_not_lock_handle_to_twenty_sessions():
    assert Strategy(handle_max=40,cup_max=130).handle_max==40


def test_candidate_already_beyond_target_is_excluded_before_model_or_order():
    bars=[]
    for i in range(160):
        c=85 if i<120 else 98;high,low=c+1,c-1
        if i==120:c,high,low=99,100,98
        if i==135:c,high,low=95,96,94
        if i==155:c,high,low=97,97.2,96.8
        if 156<=i<=158:c,high,low=97.1,97.2,97
        if i==159:c,high,low=102,103,101
        bars.append(Bar(date=(date(2024,1,1)+timedelta(days=i)).isoformat(),open=c,high=high,low=low,close=c,volume=200 if i==159 else 100))
    assert screen(bars,159,Strategy())['pass']
    # Independently calculated T=97.2+(97.2-94)=100.4, already below close102.
    # It must never be offered to a model or reach Account.enter's fatal invariant.
    assert shortlist(bars,159,Strategy(target_multiple=1),'A')==[]
    raised=shortlist(bars,159,Strategy(),'A')
    assert len(raised)==1
    assert raised[0]['target']==pytest.approx(106.8)
    # At close102 the old objective100.4 is behind us, but the raised106.8 is still ahead.
    a=Account(100000)
    assert a.enter('A',bars[-1].date,102,raised[0]['stop'],Strategy(),raised[0])
    assert a.orders[0]['target']==pytest.approx(106.8)
    a.open_day('2024-06-09',{'A':102},Strategy())
    a.close_day('2024-06-09',{'A':104},Strategy())
    assert not [o for o in a.orders if o['side']=='sell']
    a.close_day('2024-06-10',{'A':107},Strategy())
    assert a.orders[-1]['reason']=='target_close'
