"""Load the approved frozen source; derive bars from verified raw JSON, not diagnostic CSV code."""
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import exchange_calendars as xcals
from .contracts import Bar, Strategy, iso
from .strategy import required_history
from .universe import UNIVERSE

PRICE_BASIS = 'yahoo_split_adjusted_ohlcv_no_dividend_adjustment'
PRICE_BASIS_NOTE = (
    'Yahoo chart quote OHLC and volume are used as provided, in snapshot split-adjusted '
    'share units; never apply split factors a second time. adjclose is not used. '
    'Dividends/capital gains are not reinvested or credited. This is price return, not '
    'total return or point-in-time as-traded share quantities. Future snapshot splits '
    'can rescale earlier quoted prices/volume; this frozen normalization is disclosed.'
)


def _day(timestamp):
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
        raise ValueError('Invalid market timestamp/event date')
    return (datetime(1970, 1, 1, tzinfo=timezone.utc)+timedelta(seconds=timestamp)).astimezone(
        ZoneInfo('America/New_York')).date().isoformat()


def _events(obj):
    events = obj.get('events', {})
    if not isinstance(events, dict) or set(events) - {'splits', 'dividends', 'capitalGains'}:
        raise ValueError('Unsupported corporate event type')
    splits = []
    for kind, records in events.items():
        if not isinstance(records, dict):
            raise ValueError('Invalid corporate event records')
        for event in records.values():
            if not isinstance(event, dict) or 'date' not in event:
                raise ValueError('Invalid corporate event')
            _day(event['date'])
            if kind == 'splits':
                factors = [event.get('numerator'), event.get('denominator')]
                if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0
                       for x in factors):
                    raise ValueError('Invalid split factor')
                try:
                    ratio = event['splitRatio'].replace('/', ':').split(':')
                    consistent = len(ratio) == 2 and math.isclose(float(ratio[0]) / float(ratio[1]), factors[0] / factors[1])
                except (KeyError, ValueError, TypeError, ZeroDivisionError, AttributeError):
                    consistent = False
                if not consistent:
                    raise ValueError('Invalid or inconsistent split ratio')
                factor = factors[0] / factors[1]
                if not (math.isclose(factor, round(factor)) or math.isclose(1 / factor, round(1 / factor))):
                    raise ValueError('Fractional/spinoff-like split requires corporate-action review')
                splits.append(dict(event, day=_day(event['date'])))
            else:
                amount = event.get('amount')
                if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                    raise ValueError('Invalid cash distribution event')
    return sorted(splits, key=lambda event: event['date'])


def warmup_requirement(value=None):
    value = required_history(Strategy()) if value is None else value
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError('Required warmup must be a nonnegative number of sessions')
    return value


def market_calendar(start, end):
    iso(start); iso(end)
    if start > end:
        raise ValueError('Start must not be after end')
    # Avoid the calendar library's rolling default year range.
    return xcals.get_calendar('XNYS', start=start,
                              end=(date.fromisoformat(end)+timedelta(days=1)).isoformat())


def parse_yahoo(raw: bytes, symbol: str, start: str, end: str, *, allow_listing_warmup=False,
                required_warmup=None):
    """Validate source structure and split-only quotes; never substitute adjclose.

    Yahoo has already normalized historical quote OHLCV for splits. Applying factors
    again is wrong. Cash distributions are validated but deliberately not added to
    this project's price-return ledger. Unknown corporate events fail closed.
    """
    warmup = warmup_requirement(required_warmup)
    iso(start); iso(end)
    if start > end:
        raise ValueError('Start must not be after end')
    try:
        chart = json.loads(raw)['chart']
        if chart.get('error') or len(chart.get('result') or []) != 1:
            raise ValueError('Yahoo chart returned an error or ambiguous result')
        obj = chart['result'][0]
        meta = obj['meta']
        expected_type = 'ETF' if UNIVERSE[symbol]['kind'] == 'etf' else 'EQUITY'
        if (meta.get('symbol') != symbol or meta.get('currency') != 'USD'
                or meta.get('instrumentType') != expected_type
                or meta.get('exchangeTimezoneName') != 'America/New_York'):
            raise ValueError(f'{symbol}: instrument identity/currency/type/timezone mismatch')
        times = obj['timestamp']
        quotes = obj['indicators']['quote']
        if not isinstance(times, list) or len(quotes) != 1:
            raise ValueError('Invalid quote/timestamp arrays')
        quote = quotes[0]
        keys = ('open', 'high', 'low', 'close', 'volume')
        if any(not isinstance(quote.get(key), list) or len(quote[key]) != len(times) for key in keys):
            raise ValueError('OHLCV array length mismatch')
        splits = _events(obj)
        bars = []
        for i, timestamp in enumerate(times):
            day = _day(timestamp)
            values = {key: quote[key][i] for key in keys}
            if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
                   for v in values.values()):
                raise ValueError(f'{symbol}: nonfinite or missing OHLCV on {day}')
            try:
                bar = Bar(date=day, **values)
            except ValueError as error:
                raise ValueError(f'{symbol}: invalid OHLCV on {day}: {error}') from error
            if day <= end:
                bars.append(bar)
        validate_bars(bars)
        calendar = market_calendar(bars[0].date, bars[-1].date)
        expected = [d.strftime('%Y-%m-%d') for d in calendar.sessions_in_range(bars[0].date, bars[-1].date)]
        if [bar.date for bar in bars] != expected:
            raise ValueError(f'{symbol}: missing or extra sessions')
        dates = [bar.date for bar in bars]
        if start not in dates or end not in dates:
            raise ValueError('Start/end must be covered trading sessions')
        listing_limited = False
        if dates.index(start) < warmup and allow_listing_warmup:
            # A genuine recent IPO cannot supply pre-listing bars. Keep its real
            # history; screen() still enforces the unchanged strategy warmup.
            listing_limited = ('firstTradeDate' in meta and _day(meta['firstTradeDate']) == dates[0])
        if dates.index(start) < warmup and not listing_limited:
            raise ValueError(f'Start/end require {warmup} prior warmup bars')
        return bars, {'sessions': len(bars), 'first': dates[0], 'last': dates[-1],
                      'warmup_sessions': dates.index(start), 'splits': splits,
                      'listing_limited_warmup': listing_limited,
                      'dividend_events': len(obj.get('events', {}).get('dividends', {})),
                      'capital_gain_events': len(obj.get('events', {}).get('capitalGains', {}))}
    except (KeyError, IndexError, TypeError, OverflowError) as error:
        raise ValueError(f'{symbol}: malformed Yahoo market response: {error}') from error


def validate_bars(bars):
    dates = [b.date for b in bars]
    if not dates or dates != sorted(set(dates)):
        raise ValueError('Empty, duplicate or unsorted market data')


class SourceUnavailable(ValueError):
    """Coverage shortage, distinct from a corrupt or unverified source."""


def read_source(path, symbol, receipt=None):
    receipt = receipt or json.loads(path.with_name(f'{symbol}.fetch.json').read_text(encoding='utf-8-sig'))
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt.get('sha256'):
        raise ValueError(f'{symbol}: snapshot checksum mismatch')
    if receipt.get('bytes') != len(raw):
        raise ValueError(f'{symbol}: invalid snapshot receipt identity/size')
    # Frozen v1 receipts lack schema fields. Decode their no-split data through
    # the same validator; never infer this exemption from a dated folder name.
    legacy_fields = {'request_url', 'retrieved_utc', 'sha256', 'bytes'}
    legacy = legacy_fields <= set(receipt) <= legacy_fields | {'symbol', 'http_status'}
    if 'symbol' in receipt and receipt['symbol'] != symbol:
        raise ValueError(f'{symbol}: invalid snapshot receipt identity/size')
    if not legacy:
        if receipt.get('price_basis') != PRICE_BASIS:
            raise ValueError(f'{symbol}: unverified snapshot price basis')
        if receipt.get('symbol') != symbol:
            raise ValueError(f'{symbol}: invalid snapshot receipt identity/size')
    if legacy and json.loads(raw)['chart']['result'][0].get('events', {}).get('splits'):
        raise ValueError(f'{symbol}: legacy receipt requires split/corporate-action review')
    return raw, receipt


def select_source(root, symbol, start, end, *, required_warmup=None):
    """Oldest sufficient immutable receipt wins; corruption never falls back."""
    warmup = warmup_requirement(required_warmup)
    if symbol not in UNIVERSE:
        raise ValueError('Unsupported symbol')
    iso(start); iso(end)
    if start > end:
        raise ValueError('Start must not be after end')
    sources = []
    for base in ('artifacts/preflight', 'artifacts/market'):
        for path in (Path(root)/base).rglob(f'{symbol}.yahoo.json'):
            receipt = json.loads(path.with_name(f'{symbol}.fetch.json').read_text(encoding='utf-8-sig'))
            sources.append((receipt.get('retrieved_utc', '9999'), path.as_posix(), path, receipt))
    coverage = []
    for _, _, path, receipt in sorted(sources):
        raw, receipt = read_source(path, symbol, receipt)
        obj = json.loads(raw)['chart']['result'][0]
        dates = [_day(t) for t in obj['timestamp']]
        if not dates:
            raise ValueError(f'{symbol}: empty source history')
        # Coverage shortage may select another source, but not hide malformed
        # identity, events, bars or continuity in the source being considered.
        parse_yahoo(raw, symbol, dates[0], dates[-1], required_warmup=0)
        if dates:
            coverage.append(f'{dates[0]}..{dates[-1]}')
        if start not in dates or end not in dates:
            continue
        listing = obj.get('meta', {}).get('firstTradeDate')
        listing_limited = listing is not None and _day(listing) == dates[0]
        if dates.index(start) < warmup and not listing_limited:
            continue
        bars, validation = parse_yahoo(raw, symbol, start, end, allow_listing_warmup=True,
                                       required_warmup=warmup)
        return path, receipt, bars, validation
    raise SourceUnavailable(f'{symbol}: Start/end need covered trading sessions and {warmup} prior warmup bars; '
                            f'available: {", ".join(coverage) or "none"}. Fetch and freeze the required real data first.')


def load_snapshot(root: Path, symbols: list[str], start: str, end: str, *, required_warmup=None):
    return {symbol: select_source(root, symbol, start, end, required_warmup=required_warmup)[2]
            for symbol in symbols}


def snapshot_id(data):
    payload = {s: [b.model_dump() for b in bars] for s, bars in sorted(data.items())}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
