from datetime import date, timedelta
import json

import pytest

from lab.contracts import Bar, RunConfig, Strategy
from lab.prompts import make_context
from lab.strategy import mean_true_range, rank_symbols, screen


def rising_bars(n=180):
    return [Bar(date=(date(2020, 1, 1)+timedelta(days=i)).isoformat(),
                open=100+i, high=101+i, low=99+i, close=100.5+i, volume=1000)
            for i in range(n)]


def test_model_facts_describe_actual_configured_periods():
    s = Strategy(trend_period=20, trend_slope_sessions=5, breakout_lookback=40,
                 volume_lookback=10)
    facts = json.loads(make_context('AAPL', rising_bars(), 179,
                                   RunConfig(strategy=s, use_images=False), candidates=[])['text'])['candidate']
    assert facts['trend_sma'] == 270.0
    assert facts['trend_sma_prior'] == 265.0
    assert facts['breakout_prior_high'] == 279.0
    assert facts['periods'] == {'trend': 20, 'trend_shift': 5, 'breakout': 40, 'volume': 10}
    assert not {'sma50', 'sma50_prior10', 'prior_high20'} & facts.keys()


def test_screen_waits_for_volatility_previous_close_before_candidate_work():
    bars = rising_bars()
    s = Strategy(history_window=100, volatility_period=100, volume_multiple=.9)
    assert screen(bars, 99, s) == {'pass': False, 'reason': 'warmup'}
    assert screen(bars, 100, s)['pass']
    assert mean_true_range(bars, 100, 100) == 2.0


@pytest.mark.parametrize('priority', ['breakout_strength', 'momentum'])
def test_new_listing_ranking_is_safe_and_keeps_warmed_names_first(priority):
    bars = rising_bars()
    s = Strategy(entry_priority=priority)
    bars[-1] = Bar(date=bars[-1].date, open=1, high=2, low=.5, close=1, volume=1000)
    assert rank_symbols({'AAPL': bars[:1], 'NVDA': bars, 'MSFT': bars[:1]},
                        {'AAPL': 0, 'NVDA': 179, 'MSFT': 0}, s) == ['NVDA', 'AAPL', 'MSFT']
