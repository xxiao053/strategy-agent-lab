"""Separate spend authorization, reported token pricing and provider billing.

The application has no provider invoice integration. Token pricing is never a
provider-confirmed charge, and the reservation margin never prices completed usage.
"""
from decimal import Decimal,InvalidOperation

RESERVATION_MULTIPLIER=1.5
LONG_CONTEXT_INPUT_TOKENS=272000


def _rate(value):
    try:
        result=Decimal(str(value))
        return result if result.is_finite() and result>=0 else None
    except (InvalidOperation,ValueError):return None


def pricing_snapshot(cfg):
    luna=cfg.get('provider')=='openai' and cfg.get('model')=='gpt-6-luna'
    base=_rate(cfg.get('input_price'))
    cached=cfg.get('cached_input_price')
    write=cfg.get('cache_write_price')
    if luna and base is not None:
        if cached is None:cached=float(base*Decimal('.1'))
    return dict(input_price=cfg.get('input_price'),output_price=cfg.get('output_price'),
                cached_input_price=cached,cache_write_price=write,
                tariff='luna-standard-configured-rates-v1' if luna else 'configured-token-rates-v1')


def _tiers(pricing,input_tokens):
    if pricing['tariff']=='luna-standard-configured-rates-v1' and input_tokens>LONG_CONTEXT_INPUT_TOKENS:
        return Decimal(2),Decimal('1.5')
    return Decimal(1),Decimal(1)


def reserve_cost(cfg,input_bound,output_bound):
    """Before dispatch only; tariff changes and 1.5x safety margin are distinct."""
    prices=pricing_snapshot(cfg)
    input_rate,output_rate=_rate(prices['input_price']),_rate(prices['output_price'])
    if input_rate is None or output_rate is None:raise ValueError('Configure valid token prices before authorizing model calls.')
    input_rate=max(input_rate,*(_rate(prices[k]) or Decimal(0) for k in ('cached_input_price','cache_write_price')))
    input_tier,output_tier=_tiers(prices,input_bound)
    return float((Decimal(input_bound)*input_rate*input_tier+Decimal(output_bound)*output_rate*output_tier)*Decimal(str(RESERVATION_MULTIPLIER))/1000000)


def record_pricing(cfg):
    return dict(accounting_version=2,pricing=pricing_snapshot(cfg),reservation_multiplier=RESERVATION_MULTIPLIER,
                usage_cost=None,billed_cost=None,cost_status='reserved')


def usage_reported(provider,raw):
    value=raw.get('usageMetadata' if provider=='gemini' else 'usage') or {}
    keys=('promptTokenCount','candidatesTokenCount') if provider=='gemini' else (
        ('input_tokens','output_tokens') if provider in {'openai','anthropic'} else ('prompt_tokens','completion_tokens'))
    if not isinstance(value,dict) or not all(type(value.get(key)) is int and value[key]>=0 for key in keys):return False
    if provider=='gemini':
        optional=[value.get('thoughtsTokenCount',0),value.get('cachedContentTokenCount',0)]
        if not all(type(v) is int and v>=0 for v in optional):return False
        return optional[1]<=value['promptTokenCount']
    if provider=='anthropic':
        return all(type(value.get(k,0)) is int and value.get(k,0)>=0 for k in ('cache_read_input_tokens','cache_creation_input_tokens'))
    input_details=value.get('input_tokens_details' if provider=='openai' else 'prompt_tokens_details') or {}
    output_details=value.get('output_tokens_details' if provider=='openai' else 'completion_tokens_details') or {}
    if not isinstance(input_details,dict) or not isinstance(output_details,dict):return False
    cached=input_details.get('cached_tokens',value.get('prompt_cache_hit_tokens',0))
    reasoning=output_details.get('reasoning_tokens',0)
    return (type(cached) is int and 0<=cached<=value[keys[0]] and
            type(reasoning) is int and 0<=reasoning<=value[keys[1]])


def settlement(cfg,usage,*,reserve):
    prices=pricing_snapshot(cfg)
    unpriced=dict(usage_cost=None,billed_cost=None,committed_cost=reserve,cost_status='usage_unpriced')
    if not isinstance(usage,dict) or not {'input','output'}<=usage.keys():return unpriced
    counts=[usage.get(key,0) for key in ('input','output','cached','cache_write')]
    if any(type(value) is not int or value<0 for value in counts):return unpriced
    input_tokens,output_tokens,cached,write=counts
    if cached+write>input_tokens:return unpriced
    components=[(input_tokens-cached-write,prices['input_price']),(cached,prices['cached_input_price']),(write,prices['cache_write_price'])]
    input_total=Decimal(0)
    for count,price in components:
        rate=_rate(price)
        if count and rate is None:return unpriced
        input_total+=count*(rate or Decimal(0))
    output_rate=_rate(prices['output_price'])
    if output_rate is None:return unpriced
    input_tier,output_tier=_tiers(prices,input_tokens)
    amount=float((input_total*input_tier+output_tokens*output_rate*output_tier)/1000000)
    return dict(usage_cost=amount,billed_cost=None,committed_cost=amount,cost_status='usage_priced')
