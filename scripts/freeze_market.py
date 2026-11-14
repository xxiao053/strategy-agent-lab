"""Freeze real daily Yahoo responses for a requested interval; never overwrite sources.

Example: python -m scripts.freeze_market --start 2022-04-04 --end 2022-08-31 --symbols AAPL MSFT
Use --config saved-config.json to derive instruments, interval and strategy warmup.
No credentials, paid LLM calls or database writes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import time
import httpx
from urllib.parse import quote
from urllib.request import Request, urlopen

from lab.contracts import RunConfig
from lab.market import (PRICE_BASIS, PRICE_BASIS_NOTE, SourceUnavailable, market_calendar,
                        parse_yahoo, select_source, warmup_requirement)
from lab.strategy import required_history
from lab.universe import SYMBOLS
from lab.provider_io import chunks as bounded_chunks


def _transport(url):
    if not url.startswith('https://query1.finance.yahoo.com/v8/finance/chart/'):
        raise ValueError('Only the fixed market provider is supported.')
    deadline=time.monotonic()+30;raw=bytearray()
    with httpx.Client(timeout=10,follow_redirects=False) as client:
        with client.stream('GET',url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json','Accept-Encoding':'identity'}) as response:
            try:
                for chunk in bounded_chunks(response,limit=4000000,deadline=deadline):raw.extend(chunk)
            except ValueError:
                raise ValueError('Market response violates size, encoding or time limit.') from None
            return bytes(raw),response.status_code,dict(response.headers)


def request_interval(start, end, warmup):
    begin = date.fromisoformat(start)-timedelta(days=max(366, warmup*2+30))
    calendar = market_calendar(begin.isoformat(), end)
    if not calendar.is_session(start) or not calendar.is_session(end):
        raise ValueError('Start/end must be trading sessions')
    sessions = calendar.sessions_in_range(calendar.first_session, start)
    if len(sessions) <= warmup:
        raise ValueError('Insufficient calendar coverage for required warmup')
    first = sessions[-warmup-1].strftime('%Y-%m-%d')
    last_exclusive = (date.fromisoformat(end)+timedelta(days=1)).isoformat()
    stamp = lambda day: int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    return first, stamp(first), stamp(last_exclusive)


def freeze_symbol(root: Path, symbol: str, *, start: str, end: str, required_warmup=None,
                  transport=_transport, retries=3):
    if symbol not in SYMBOLS or not 1 <= retries <= 3:
        raise ValueError('Choose an authorized symbol and 1..3 bounded attempts')
    warmup = warmup_requirement(required_warmup)
    first, period1, period2 = request_interval(start, end, warmup)
    try:
        path, receipt, _, validation = select_source(root, symbol, start, end, required_warmup=warmup)
        return dict(receipt, source_folder=path.parent.relative_to(root).as_posix(),
                    validation=validation)
    except SourceUnavailable:
        pass  # Only coverage shortage permits fetching; corrupt receipts fail closed.
    spec = dict(start=start, end=end, warmup=warmup, price_basis=PRICE_BASIS)
    key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
    folder = root / 'artifacts/market' / f'{start}_{end}_{key}'
    raw_path = folder / f'{symbol}.yahoo.json'
    receipt_path = folder / f'{symbol}.fetch.json'
    if raw_path.exists() or receipt_path.exists():
        raise ValueError(f'{symbol}: existing incomplete/insufficient snapshot; refusing overwrite')
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe="-")}?'
           f'period1={period1}&period2={period2}&interval=1d&events=div%2Csplits')
    errors = []
    for attempt in range(1, retries+1):
        try:
            raw, status, headers = transport(url)
            if status != 200:
                raise ValueError(f'Unexpected HTTP status {status}')
            _, validation = parse_yahoo(raw, symbol, start, end, allow_listing_warmup=True,
                                         required_warmup=warmup)
            receipt = {
                'symbol': symbol, 'request_url': url,
                'retrieved_utc': datetime.now(timezone.utc).isoformat(),
                'http_status': status,
                'response_headers': {k: v for k, v in headers.items()
                                     if k.lower() in {'date', 'content-type', 'etag', 'last-modified'}},
                'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                'attempts': attempt, 'prior_errors': errors,
                'research_start': start, 'research_end': end, 'requested_start': first,
                'required_warmup': warmup, 'source_folder': folder.relative_to(root).as_posix(),
                'price_basis': PRICE_BASIS, 'price_basis_note': PRICE_BASIS_NOTE,
                'validation': validation,
            }
            folder.mkdir(parents=True, exist_ok=True)
            with raw_path.open('xb') as stream:
                stream.write(raw)
            with receipt_path.open('x', encoding='utf-8') as stream:
                json.dump(receipt, stream, indent=2, allow_nan=False)
            return receipt
        except (OSError, ValueError, HTTPException, httpx.HTTPError) as error:
            errors.append(f'{type(error).__name__}: {error}')
            if raw_path.exists() or receipt_path.exists():
                raise ValueError(f'{symbol}: partial save; refusing overwrite: {error}') from error
            if attempt < retries:
                time.sleep(.25*attempt)
    raise ValueError(f'{symbol}: failed after {retries} attempts: ' + '; '.join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=5, choices=range(1, 7))
    parser.add_argument('--config', type=Path, help='Saved RunConfig JSON; explicit flags override it')
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--symbols', nargs='+', choices=SYMBOLS)
    parser.add_argument('--warmup', type=int, help='Required prior sessions; normally derived from strategy')
    args = parser.parse_args()
    cfg = RunConfig.model_validate(json.loads(args.config.read_text(encoding='utf-8-sig'))) if args.config else None
    start, end = args.start or (cfg.start if cfg else None), args.end or (cfg.end if cfg else None)
    if not start or not end:
        parser.error('Provide --start and --end, or --config; there is no fixed research period')
    symbols = args.symbols or (cfg.symbols if cfg else list(SYMBOLS))
    if len(symbols) != len(set(symbols)):
        parser.error('Symbols must be distinct')
    warmup = warmup_requirement(args.warmup if args.warmup is not None else
                               required_history(cfg.strategy) if cfg else None)
    first, _, _ = request_interval(start, end, warmup)
    root = Path(__file__).resolve().parents[1]
    accepted, excluded = {}, {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(freeze_symbol, root, symbol, start=start, end=end,
                               required_warmup=warmup): symbol for symbol in symbols}
        for future in as_completed(pending):
            symbol = pending[future]
            try:
                accepted[symbol] = future.result()
                print(f'ACCEPTED {symbol}: {accepted[symbol]["validation"]["sessions"]} sessions', flush=True)
            except Exception as error:
                excluded[symbol] = f'{type(error).__name__}: {error}'
                print(f'EXCLUDED {symbol}: {error}', flush=True)
    manifest = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'source': 'Yahoo chart HTTPS responses as returned; no fabricated or interpolated bars',
        'requested_start': first, 'research_start': start, 'research_end': end,
        'required_warmup': warmup, 'price_basis': PRICE_BASIS, 'price_basis_note': PRICE_BASIS_NOTE,
        'scope_note': 'User-selected demonstration universe; present-day selection is not survivorship-free.',
        'accepted': {symbol: accepted[symbol] for symbol in symbols if symbol in accepted},
        'excluded': excluded,
    }
    folder = root / 'artifacts/market/manifests'
    folder.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime('manifest-%Y%m%dT%H%M%S%fZ.json')
    with (folder/name).open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
    print(json.dumps({'accepted_count': len(accepted), 'excluded': excluded, 'manifest': str(folder/name)}))
    return 0 if len(accepted) == len(symbols) else 1


if __name__ == '__main__':
    raise SystemExit(main())
