from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from lab.contracts import Bar, Decision, Strategy, RunConfig
from lab.market import load_snapshot, validate_bars
from lab.strategy import screen, feasible_anchors, validate_decision, read_bars
from lab.account import Account, quantity
from tests.helpers import exit_facts

ROOT = Path(__file__).resolve().parents[1]


def bars(n=200):
    return [Bar(date=str(date(2023, 1, 1) + timedelta(days=i)), open=100, high=101, low=99,
                close=100, volume=100) for i in range(n)]


def test_size_reference_and_gap_cancellation():
    # Preserve the original reference scenario explicitly, not as current defaults.
    strategy = Strategy(risk_fraction=.005)
    assert quantity(100000, 100, 92, 100000, strategy) == 45
    a = Account(100000)
    assert a.enter('AAPL', '2024-01-02', 100, 92, strategy, pattern=exit_facts())
    a.open_day('2024-01-03', {'AAPL': 104}, strategy)
    assert a.cash == 100000 and not a.positions
    assert a.orders[0]['status'] == 'cancelled_gap'


def test_reserved_cash_and_slot_limit():
    strategy = Strategy(max_positions=3)
    a = Account(100000)
    for symbol in ['A', 'B', 'C']:
        assert a.enter(symbol, '2024-01-02', 100, 99, strategy, pattern=exit_facts(99))
    assert not a.enter('D', '2024-01-02', 100, 99, strategy, pattern=exit_facts(99))
    assert a.available >= 0
    a.open_day('2024-01-03', dict(A=100, B=100, C=100), strategy)
    assert a.cash >= 0 and len(a.positions) == 3


def test_stop_uses_next_open_and_keeps_open_end_positions():
    a = Account(100000)
    a.enter('A', '2024-01-02', 100, 92, Strategy(), pattern=exit_facts())
    a.open_day('2024-01-03', {'A': 100}, Strategy())
    a.close_day('2024-01-03', {'A': 90}, Strategy())
    assert 'A' in a.positions
    a.open_day('2024-01-04', {'A': 80}, Strategy())
    assert not a.positions
    assert a.trades[0]['exit_price'] == pytest.approx(79.96)
    assert a.trades[0]['pnl'] < 0
    assert a.cash == pytest.approx(100000 + a.trades[0]['pnl'])


def test_volume_screen_excludes_current_day():
    b = bars()
    for i in range(150, 199):
        b[i] = b[i].model_copy(update={'close': 102, 'high': 103, 'open': 102})
    b[-1] = b[-1].model_copy(update={'close': 104, 'high': 105, 'open': 104, 'volume': 120})
    assert screen(b, 199, Strategy())['pass']
    b[-1] = b[-1].model_copy(update={'volume': 119})
    assert not screen(b, 199, Strategy())['pass']


def test_read_tool_rejects_future_wrong_symbol_and_oversized_range():
    b = bars()
    assert len(read_bars(b[-40:], 'AAPL', 'AAPL', b[-2].date, b[-1].date)) == 2
    for symbol, start, end in [('MSFT', b[-2].date, b[-1].date),
                                ('AAPL', b[-41].date, b[-1].date),
                                ('AAPL', b[-2].date, '2099-01-01')]:
        with pytest.raises(ValueError):
            read_bars(b, 'AAPL', symbol, start, end)


def test_contract_rejects_unapproved_or_invalid_config():
    with pytest.raises(ValidationError):
        RunConfig(symbols=['../../secret'], approved=True)
    with pytest.raises(ValidationError):
        Strategy(cup_min=110, cup_max=90)
    with pytest.raises(ValidationError):
        RunConfig(start='2026-01-02', end='2024-01-01', approved=True)
    with pytest.raises(ValidationError):
        RunConfig(capital=float('nan'), approved=True)


def test_bad_data_rejected():
    b = bars()
    with pytest.raises(ValueError):
        validate_bars([b[0], b[0]])
    with pytest.raises(ValidationError):
        Bar(date='2024-01-01', open=2, high=1, low=1, close=2, volume=10)


@pytest.mark.market_data
def test_frozen_snapshot_counts_and_prefix_invariance():
    historical = Strategy(cup_max=100,handle_max=20)
    data = load_snapshot(ROOT, ['AAPL', 'MSFT', 'AMZN', 'QQQ', 'SPY'], '2024-01-02', '2026-11-10')
    counts = []
    for symbol, b in data.items():
        candidates = feasible = 0
        for i, bar in enumerate(b):
            if '2024-01-02' <= bar.date < '2026-11-10' and screen(b, i, historical)['pass']:
                candidates += 1
                pairs = feasible_anchors(b, i, historical)
                feasible += bool(pairs)
                assert screen(b[:i+1], i, Strategy()) == screen(b, i, Strategy())
        counts.append((symbol, candidates, feasible))
    assert counts == [('AAPL', 18, 15), ('MSFT', 11, 5), ('AMZN', 14, 13), ('QQQ', 9, 8), ('SPY', 10, 2)]


def test_decision_checks_are_consistent_and_dates_visible():
    b = bars()
    obj = {'verdict': 'pass', 'checks': [{'name': x, 'verdict': 'pass', 'reason': 'example',
             'start_date': b[-80].date, 'end_date': b[-2].date} for x in ['cup', 'handle', 'coherence']],
           'anchors': {'left_rim': b[-80].date, 'right_rim': b[-8].date}, 'evidence': 'test'}
    d = Decision.model_validate(obj)
    assert validate_decision(d, b, len(b)-1, Strategy())['accepted'] is False
    obj['anchors']['right_rim'] = b[-1].date
    with pytest.raises(ValueError):
        validate_decision(Decision.model_validate(obj), b, len(b)-1, Strategy())
    obj['checks'][0]['verdict'] = 'fail'
    with pytest.raises(ValidationError):
        Decision.model_validate(obj)
