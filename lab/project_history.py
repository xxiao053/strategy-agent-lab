"""Lossless cutoff references to immutable market data; old inline inputs stay readable."""
import copy
import hashlib
import json


def compact_context(context,history_bars):
    result=copy.deepcopy({k:v for k,v in context.items() if k!='bars'})
    result['bars_ref']=dict(schema='cutoff-bars-v1',history_bars=history_bars,symbols=list(context['bars']))
    return result


def restore_context(run,day):
    saved=run.get('inputs',{}).get(day)
    if saved is None or 'bars_ref' not in saved:return saved
    ref=saved['bars_ref'];frozen=run['frozen'];market=run['market']
    if ('bars' in saved or saved.get('cutoff')!=day or not isinstance(ref,dict) or
        set(ref)!={'schema','history_bars','symbols'} or ref['schema']!='cutoff-bars-v1' or
        type(ref['history_bars']) is not int or ref['history_bars']!=frozen['manifest']['history_bars'] or
        not isinstance(ref['symbols'],list) or len(set(ref['symbols']))!=len(ref['symbols']) or
        set(ref['symbols'])!=set(market)):
        raise ValueError('Saved cutoff reference changed.')
    if hashlib.sha256(json.dumps(market,sort_keys=True).encode()).hexdigest()!=frozen['market_hash']:
        raise ValueError('Frozen market evidence changed.')
    bars={}
    for symbol in ref['symbols']:
        rows=market[symbol];dates=[b['date'] for b in rows]
        if dates!=sorted(set(dates)) or day not in dates:raise ValueError('Missing ordered cutoff market data.')
        end=dates.index(day)+1
        bars[symbol]=copy.deepcopy(rows[max(0,end-ref['history_bars']):end])
    return dict(copy.deepcopy({k:v for k,v in saved.items() if k!='bars_ref'}),bars=bars)
