"""Expansion must preserve source bytes and use one explicit split-only price basis."""
import hashlib
import json
from http.client import IncompleteRead
from pathlib import Path

import exchange_calendars as xcals
import pytest

from lab import market


ROOT = Path(__file__).resolve().parents[1]
NEW_FOLDER = 'artifacts/market/2026-11-12'
BASIS = 'yahoo_split_adjusted_ohlcv_no_dividend_adjustment'


def source(symbol='NVDA'):
    sessions = xcals.get_calendar('XNYS').sessions_in_range('2023-01-03', '2026-11-10')
    times = [int(d.timestamp()) + 15 * 3600 for d in sessions]
    n = len(times)
    return {'chart': {'error': None, 'result': [{
        'meta': {'symbol': symbol, 'currency': 'USD', 'instrumentType': 'EQUITY',
                 'exchangeTimezoneName': 'America/New_York'},
        'timestamp': times,
        'indicators': {'quote': [{'open': [14.8] * n, 'high': [15.0] * n,
                                  'low': [14.0] * n, 'close': [14.315] * n,
                                  'volume': [401277000] * n}],
                       'adjclose': [{'adjclose': [13.0] * n}]},
        'events': {'splits': {'1718026200': {'date': 1718026200, 'numerator': 10.0,
                                          'denominator': 1.0, 'splitRatio': '10:1'}},
                   'dividends': {'1709649000': {'amount': .004, 'date': 1709649000}}},
    }]}}


def freeze_fixture(root, obj, symbol='NVDA', basis=BASIS):
    folder = root / NEW_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj).encode()
    (folder / f'{symbol}.yahoo.json').write_bytes(raw)
    (folder / f'{symbol}.fetch.json').write_text(json.dumps({
        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'price_basis': basis,
        'symbol': symbol, 'request_url': f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}',
    }))
    return folder


def test_split_adjusted_quotes_are_neither_split_twice_nor_dividend_adjusted(tmp_path):
    # A second split adjustment or using adjclose would change 14.315 to 1.4315 or 13.
    freeze_fixture(tmp_path, source())
    data = market.load_snapshot(tmp_path, ['NVDA'], '2024-01-02', '2026-11-10')['NVDA']
    assert len(data) == 968
    assert data[0].close == 14.315
    assert data[0].volume == 401277000
    assert data[-1].date == '2026-11-10'


@pytest.mark.parametrize('mutation,match', [
    ('checksum', 'checksum'), ('identity', 'identity'), ('basis', 'basis'),
    ('missing', 'sessions'), ('null', 'OHLCV'), ('nonfinite', 'OHLCV'),
    ('zero_split', 'split'), ('unknown_event', 'event'), ('short_array', 'length'),
    ('spinoff_like', 'corporate-action review'),
])
def test_expanded_snapshot_fails_closed(tmp_path, mutation, match):
    obj = source()
    result = obj['chart']['result'][0]
    if mutation == 'identity':
        result['meta']['symbol'] = 'MSFT'
    elif mutation == 'missing':
        result['timestamp'].pop(300)
        for values in result['indicators']['quote'][0].values():
            values.pop(300)
    elif mutation == 'null':
        result['indicators']['quote'][0]['close'][10] = None
    elif mutation == 'nonfinite':
        result['indicators']['quote'][0]['volume'][10] = float('inf')
    elif mutation == 'zero_split':
        result['events']['splits']['1718026200']['denominator'] = 0
    elif mutation == 'unknown_event':
        result['events']['merger'] = {'1': {'date': 1718026200}}
    elif mutation == 'short_array':
        result['indicators']['quote'][0]['open'].pop()
    elif mutation == 'spinoff_like':
        result['events']['splits']['1718026200'].update(numerator=1253.0, denominator=1000.0,
                                                      splitRatio='1253:1000')
    folder = freeze_fixture(tmp_path, obj, basis='unverified' if mutation == 'basis' else BASIS)
    if mutation == 'checksum':
        with (folder / 'NVDA.yahoo.json').open('ab') as stream:
            stream.write(b' ')
    with pytest.raises(ValueError, match=match):
        market.load_snapshot(tmp_path, ['NVDA'], '2024-01-02', '2026-11-10')


def test_expanded_snapshot_enforces_requested_warmup_and_end_session(tmp_path):
    freeze_fixture(tmp_path, source())
    with pytest.raises(ValueError, match='250.*warmup'):
        market.load_snapshot(tmp_path, ['NVDA'], '2023-12-29', '2026-11-10', required_warmup=250)
    with pytest.raises(ValueError, match='Start/end'):
        market.load_snapshot(tmp_path, ['NVDA'], '2024-01-02', '2026-11-11')


@pytest.mark.market_data
def test_original_five_remain_bound_to_original_snapshot():
    # Catch changing legacy inputs when a second copy or refreshed source appears.
    data = market.load_snapshot(ROOT, ['AAPL', 'MSFT', 'AMZN', 'QQQ', 'SPY'],
                                '2024-01-02', '2026-11-10')
    assert len(data['AAPL']) == 968
    source, *_ = market.select_source(ROOT, 'AAPL', '2024-01-02', '2026-11-10')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (
        'efa2bd8e400e17119389226e7d150d42d6a2bde0504cf5737702ffea8d460bb5')


def test_universe_expansion_enables_mainstream_stocks_and_unleveraged_etfs():
    from lab.universe import SYMBOLS, UNIVERSE
    assert len(SYMBOLS) >= 30
    assert set(SYMBOLS) == set(UNIVERSE)
    assert {'NVDA', 'META', 'GOOG', 'AVGO', 'JPM', 'VTI', 'SMH', 'TLT', 'HD'} <= set(SYMBOLS)
    assert UNIVERSE['NVDA'] == {'name': 'NVIDIA', 'kind': 'stock'}
    assert UNIVERSE['VTI']['kind'] == 'etf'
    assert not {'TQQQ', 'SQQQ', 'SOXL', 'SPXL'} & set(SYMBOLS)
    assert 'GE' not in SYMBOLS  # Fractional spinoff normalization is not a simple split.


def test_freezer_records_bytes_basis_retries_and_does_not_overwrite(tmp_path):
    from scripts.freeze_market import freeze_symbol
    payload = json.dumps(source()).encode()
    attempts = []

    def transport(url):
        attempts.append(url)
        if len(attempts) == 1:
            raise OSError('temporary network failure')
        return payload, 200, {'Content-Type': 'application/json'}

    receipt = freeze_symbol(tmp_path, 'NVDA', start='2024-01-02', end='2026-11-10', required_warmup=250, transport=transport, retries=2)
    folder = tmp_path / receipt['source_folder']
    assert (folder / 'NVDA.yahoo.json').read_bytes() == payload
    assert receipt['sha256'] == hashlib.sha256(payload).hexdigest()
    assert receipt['price_basis'] == BASIS
    assert receipt['attempts'] == 2
    assert receipt['validation']['sessions'] == 968
    assert receipt['validation']['splits'][0]['splitRatio'] == '10:1'
    assert 'period1=1672704000' in receipt['request_url']
    assert 'period2=1794355200' in receipt['request_url']
    # Existing verified files are reused, not fetched or refreshed.
    reused = freeze_symbol(tmp_path, 'NVDA', start='2024-01-02', end='2026-11-10', required_warmup=250, transport=lambda _: pytest.fail('unexpected refresh'))
    assert reused['sha256'] == receipt['sha256']


def test_freezer_bounded_failures_leave_no_accepted_snapshot(tmp_path):
    from scripts.freeze_market import freeze_symbol

    def failed_transport(url):
        raise OSError('offline')

    with pytest.raises(ValueError, match='2 attempts'):
        freeze_symbol(tmp_path, 'NVDA', start='2024-01-02', end='2026-11-10', required_warmup=250, transport=failed_transport, retries=2)
    assert not list(tmp_path.rglob('NVDA.fetch.json'))


def test_freezer_retries_truncated_http_body_instead_of_excluding_symbol(tmp_path):
    from scripts.freeze_market import freeze_symbol
    payload = json.dumps(source()).encode()
    attempts = []

    def truncated_once(url):
        attempts.append(url)
        if len(attempts) == 1:
            raise IncompleteRead(b'{"chart":')
        return payload, 200, {}

    receipt = freeze_symbol(tmp_path, 'NVDA', start='2024-01-02', end='2026-11-10', required_warmup=250, transport=truncated_once, retries=2)
    assert receipt['attempts'] == 2
    assert 'IncompleteRead' in receipt['prior_errors'][0]
    assert (tmp_path / receipt['source_folder'] / 'NVDA.yahoo.json').read_bytes() == payload

