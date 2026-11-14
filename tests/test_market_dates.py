import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timezone

import pytest

from lab.market import load_snapshot, parse_yahoo
from lab.contracts import Strategy
from lab.strategy import required_history
from tests.test_market_sources import source, BASIS
from tests.test_historical_data import historical_source


def frozen(root, folder, obj, symbol='AAPL', retrieved='2026-01-01T00:00:00Z'):
    path = root / 'artifacts' / folder
    path.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj).encode()
    (path / f'{symbol}.yahoo.json').write_bytes(raw)
    (path / f'{symbol}.fetch.json').write_text(json.dumps({
        'symbol': symbol, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
        'price_basis': BASIS, 'retrieved_utc': retrieved}))
    return path


def test_loader_discovers_differently_named_sources_and_skips_insufficient_warmup(tmp_path):
    frozen(tmp_path, 'market/short', source('AAPL'))
    frozen(tmp_path, 'market/long', historical_source(), retrieved='2026-02-01T00:00:00Z')
    bars = load_snapshot(tmp_path, ['AAPL'], '2023-10-02', '2023-12-29', required_warmup=250)['AAPL']
    assert bars[0].date == '2020-01-02'
    assert bars[-1].date == '2023-12-29'


def test_parser_uses_actual_strategy_warmup_not_universal_250():
    raw = json.dumps(historical_source(first='2020-09-30')).encode()
    bars, info = parse_yahoo(raw, 'AAPL', '2021-06-01', '2023-12-29', required_warmup=159)
    assert 159 <= info['warmup_sessions'] < 250
    with pytest.raises(ValueError, match='250.*warmup'):
        parse_yahoo(raw, 'AAPL', '2021-06-01', '2023-12-29', required_warmup=250)


def test_newer_valid_source_does_not_mask_corrupt_selected_receipt(tmp_path):
    old = frozen(tmp_path, 'market/a', historical_source())
    frozen(tmp_path, 'market/b', historical_source(), retrieved='2026-02-01T00:00:00Z')
    with (old / 'AAPL.yahoo.json').open('ab') as stream:
        stream.write(b' ')
    with pytest.raises(ValueError, match='checksum'):
        load_snapshot(tmp_path, ['AAPL'], '2021-01-04', '2023-12-29', required_warmup=159)


@pytest.mark.parametrize('corruption', ['identity', 'corporate-action'])
@pytest.mark.parametrize('shortage', ['coverage', 'warmup'])
def test_insufficient_coverage_does_not_hide_invalid_source(tmp_path, corruption, shortage):
    obj = source('AAPL')
    record = obj['chart']['result'][0]
    if corruption == 'identity':
        record['meta']['symbol'] = 'MSFT'
    else:
        record['events']['splits']['1718026200'].update(
            numerator=1253, denominator=1000, splitRatio='1253:1000')
    frozen(tmp_path, 'market/old-short', obj)
    frozen(tmp_path, 'market/new-long', historical_source(), retrieved='2026-02-01T00:00:00Z')
    with pytest.raises(ValueError, match=corruption):
        load_snapshot(tmp_path, ['AAPL'], '2021-01-04' if shortage=='coverage' else '2023-03-01',
                      '2023-12-29', required_warmup=159)


def test_freezer_accepts_generic_dates_and_fetches_calendar_warmup(tmp_path):
    from scripts.freeze_market import freeze_symbol
    raw = json.dumps(historical_source()).encode()
    receipt = freeze_symbol(tmp_path, 'AAPL', start='2022-04-04', end='2022-08-31',
                            required_warmup=159, transport=lambda _: (raw, 200, {}))
    query = parse_qs(urlparse(receipt['request_url']).query)
    begin = datetime.fromtimestamp(int(query['period1'][0]), timezone.utc).date().isoformat()
    end = datetime.fromtimestamp(int(query['period2'][0]), timezone.utc).date().isoformat()
    assert begin == '2021-08-17'  # 159 preceding XNYS sessions.
    assert end == '2022-09-01'  # Yahoo's exclusive upper bound.
    assert receipt['research_start'] == '2022-04-04'
    assert receipt['research_end'] == '2022-08-31'
    assert (tmp_path / receipt['source_folder'] / 'AAPL.yahoo.json').read_bytes() == raw
    again = freeze_symbol(tmp_path, 'AAPL', start='2022-04-04', end='2022-08-31',
                          required_warmup=159, transport=lambda _: pytest.fail('must reuse frozen bytes'))
    assert again == receipt
    assert load_snapshot(tmp_path, ['AAPL'], '2022-04-04', '2022-08-31', required_warmup=159)['AAPL'][-1].date == '2022-08-31'


def test_bad_date_stops_download_before_network(tmp_path):
    from scripts.freeze_market import freeze_symbol
    with pytest.raises(ValueError, match='trading session'):
        freeze_symbol(tmp_path, 'AAPL', start='2022-04-03', end='2022-08-31',
                      transport=lambda _: pytest.fail('must reject before transport'))


def test_default_required_history_is_159_not_250():
    assert required_history(Strategy()) == 159


def test_pre_epoch_listing_metadata_is_supported_on_windows():
    from lab.market import _day
    assert _day(-252406800) == '1962-01-01'
