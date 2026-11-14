"""A date-only holdout must not retune the selected strategy or erase late IPOs."""
import hashlib
import json
from datetime import datetime, timezone

import exchange_calendars as xcals
import pytest

from lab.contracts import RunConfig, Strategy
from lab import market
from lab.strategy import screen


HISTORICAL = 'artifacts/market/2026-11-12/2021-2023'


def historical_source(symbol='AAPL', first='2020-01-02', listing='1980-12-12'):
    sessions = xcals.get_calendar('XNYS').sessions_in_range(first, '2023-12-29')
    n = len(sessions)
    listing_timestamp = int(datetime.fromisoformat(listing).replace(tzinfo=timezone.utc).timestamp()) + 15 * 3600
    return {'chart': {'error': None, 'result': [{
        'meta': {'symbol': symbol, 'currency': 'USD', 'instrumentType': 'EQUITY',
                 'exchangeTimezoneName': 'America/New_York', 'firstTradeDate': listing_timestamp},
        'timestamp': [int(d.timestamp()) + 15 * 3600 for d in sessions],
        'indicators': {'quote': [{'open': [100.] * n, 'high': [102.] * n,
                                 'low': [98.] * n, 'close': [101.] * n, 'volume': [100000] * n}]},
    }]}}


def test_historical_config_accepts_three_year_window_without_changing_strategy():
    original = RunConfig(approved=True)
    config = RunConfig.model_validate(dict(original.model_dump(), start='2021-01-04', end='2023-12-29'))
    assert config.strategy == original.strategy
    assert config.mode == 'baseline' and not config.paid_authorized


def test_config_has_no_calendar_year_policy_and_rejects_only_reversed_dates():
    config = RunConfig(start='2010-01-04', end='2030-12-31')
    assert config.start == '2010-01-04' and config.end == '2030-12-31'
    with pytest.raises(ValueError, match='Start'):
        RunConfig(start='2023-12-29', end='2021-01-04')


def test_loader_uses_actual_source_coverage_not_a_fixed_research_year(tmp_path):
    from scripts.freeze_market import freeze_symbol
    raw = json.dumps(historical_source()).encode()
    freeze_symbol(tmp_path, 'AAPL', start='2021-01-04', end='2023-12-29', required_warmup=250, transport=lambda _: (raw, 200, {}))
    # Dec 30 2020 is outside the former hard-coded 2021+ research range,
    # but the source has the required 251 preceding real sessions.
    bars = market.load_snapshot(tmp_path, ['AAPL'], '2020-12-30', '2021-01-04')['AAPL']
    assert bars[-1].date == '2021-01-04'


def test_historical_original_symbol_uses_separate_checksum_verified_split_source(tmp_path):
    # Original AAPL's 2024 source cannot cover this period. Historical quotes are
    # already split normalized; a second application would incorrectly divide 101.
    obj = historical_source()
    obj['chart']['result'][0]['events'] = {'splits': {'1598880600': {
        'date': 1598880600, 'numerator': 4, 'denominator': 1, 'splitRatio': '4:1'}}}
    raw = json.dumps(obj).encode()
    folder = tmp_path / HISTORICAL
    folder.mkdir(parents=True)
    (folder / 'AAPL.yahoo.json').write_bytes(raw)
    (folder / 'AAPL.fetch.json').write_text(json.dumps({
        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
        'symbol': 'AAPL', 'price_basis': market.PRICE_BASIS}))
    bars = market.load_snapshot(tmp_path, ['AAPL'], '2021-01-04', '2023-12-29')['AAPL']
    assert bars[0].close == 101.0
    assert bars[-1].date == '2023-12-29'


def test_recent_listing_has_real_bars_only_and_waits_for_unchanged_strategy_warmup():
    raw = json.dumps(historical_source('PLTR', '2020-09-30', '2020-09-30')).encode()
    bars, validation = market.parse_yahoo(raw, 'PLTR', '2021-01-04', '2023-12-29',
                                        allow_listing_warmup=True)
    assert validation['warmup_sessions'] == 65
    assert validation['listing_limited_warmup'] is True
    assert bars[0].date == '2020-09-30'
    assert screen(bars, 65, Strategy()) == {'pass': False, 'reason': 'warmup'}


def test_truncated_established_listing_cannot_masquerade_as_recent_ipo():
    raw = json.dumps(historical_source('AAPL', '2020-09-30')).encode()
    with pytest.raises(ValueError, match='warmup'):
        market.parse_yahoo(raw, 'AAPL', '2021-01-04', '2023-12-29', allow_listing_warmup=True)


def test_historical_freezer_downloads_original_symbol_and_reuses_exact_receipt(tmp_path):
    from scripts.freeze_market import freeze_symbol
    raw = json.dumps(historical_source()).encode()
    receipt = freeze_symbol(tmp_path, 'AAPL', start='2021-01-04', end='2023-12-29', required_warmup=250,
                            transport=lambda url: (raw, 200, {}))
    assert 'period1=1578355200' in receipt['request_url']
    assert 'period2=1703894400' in receipt['request_url']
    assert (tmp_path / receipt['source_folder'] / 'AAPL.yahoo.json').read_bytes() == raw
    assert receipt['validation']['warmup_sessions'] == 253
    again = freeze_symbol(tmp_path, 'AAPL', start='2021-01-04', end='2023-12-29', required_warmup=250,
                          transport=lambda _: pytest.fail('must not refetch frozen source'))
    assert again == receipt
