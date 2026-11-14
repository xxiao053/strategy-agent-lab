import hashlib
import json
from .contracts import Decision


def required_history(s):
    """Prior bars needed at a decision close, including ATR's previous close."""
    return max(s.history_window-1, s.trend_period+s.trend_slope_sessions-1,
               s.breakout_lookback, s.volume_lookback, s.volatility_period)


def screen(bars, i, s):
    if i < required_history(s):
        return {'pass': False, 'reason': 'warmup'}
    c = bars[i].close
    sma = sum(b.close for b in bars[i-s.trend_period+1:i+1]) / s.trend_period
    old_sma = sum(b.close for b in bars[i-s.trend_slope_sessions-s.trend_period+1:i-s.trend_slope_sessions+1]) / s.trend_period
    high = max(b.high for b in bars[i-s.breakout_lookback:i])
    volume = sum(b.volume for b in bars[i-s.volume_lookback:i]) / s.volume_lookback
    return {'pass': c > sma*(1+s.trend_buffer) and sma>old_sma*(1+s.trend_slope_min) and c > high*(1+s.breakout_buffer) and volume > 0 and bars[i].volume >= s.volume_multiple * volume,
            'close': c, 'trend_sma': sma, 'trend_sma_prior': old_sma, 'breakout_prior_high': high,
            'periods': {'trend': s.trend_period, 'trend_shift': s.trend_slope_sessions,
                        'breakout': s.breakout_lookback, 'volume': s.volume_lookback},
            'volume_ratio': bars[i].volume / volume if volume else 0}


def hard_checks(bars, t, l, r, s):
    if not max(s.prior_advance_lookback, t-s.history_window+1) <= l < r < t:
        return None
    b = min(range(l, r+1), key=lambda j: bars[j].low)
    if not l < b < r or not s.cup_min <= r-l+1 <= s.cup_max or not s.handle_min <= t-r-1 <= s.handle_max:
        return None
    L, R, B = bars[l].high, bars[r].high, bars[b].low
    S = min(x.low for x in bars[r+1:t])
    P = max(x.high for x in bars[r:t])
    if (abs(R-L)/L > s.rim_tolerance or not s.depth_min <= (L-B)/L <= s.depth_max or
        L / bars[l-s.prior_advance_lookback].close - 1 < s.prior_advance or S < B+s.handle_midpoint_fraction*(L-B) or
        not 0 <= (R-S)/R <= s.handle_max_drop or not P*(1+s.breakout_buffer) < bars[t].close <= (1+s.max_breakout_extension)*P):
        return None
    # Reject before ranking/inference: a signal already at its objective has no entry headroom.
    target=P+s.target_multiple*(R-B)
    if not S < bars[t].close < target:
        return None
    return {'left_rim': bars[l].date, 'right_rim': bars[r].date, 'bottom': bars[b].date,
            'stop': S, 'pivot': P, 'target':target,'cup_depth': (L-B)/L, 'cup_sessions': r-l+1, 'handle_sessions': t-r-1}


def feasible_anchors(bars, i, s):
    pairs = []
    for r in range(max(0, i-s.handle_max-1), i-s.handle_min):
        for l in range(max(s.prior_advance_lookback, i-s.history_window+1, r-s.cup_max+1), r-s.cup_min+2):
            check = hard_checks(bars, i, l, r, s)
            if check:
                pairs.append(check)
    # Deterministic code-only baseline: longest cup, then earliest right/left rim.
    return sorted(pairs, key=lambda x: (-x['cup_sessions'], x['right_rim'], x['left_rim']))


def validate_decision(d: Decision, bars, i, s):
    visible = {b.date: j for j, b in enumerate(bars[max(0, i-159):i+1], start=max(0, i-159))}
    for check in d.checks:
        if check.start_date not in visible or check.end_date not in visible or check.start_date > check.end_date:
            raise ValueError('Evidence dates outside visible window')
    if d.anchors:
        l, r = d.anchors.left_rim, d.anchors.right_rim
        if l not in visible or r not in visible or not visible[l] < visible[r] < i:
            raise ValueError('Anchors must be ordered and before decision close')
    if d.verdict != 'pass':
        return {'accepted': False, 'reason': d.verdict}
    check = hard_checks(bars, i, visible[d.anchors.left_rim], visible[d.anchors.right_rim], s)
    return {'accepted': check is not None, 'reason': 'numeric_pass' if check else 'numeric_rejection', 'pattern': check}


def read_bars(bars, expected_symbol, symbol, start_date, end_date):
    dates = [b.date for b in bars]
    if symbol != expected_symbol or start_date not in dates or end_date not in dates or start_date > end_date:
        raise ValueError('Tool scope: same instrument and visible dates only')
    selected = bars[dates.index(start_date):dates.index(end_date)+1]
    if len(selected) > 40:
        raise ValueError('Tool limit: 40 bars')
    return [b.model_dump() for b in selected]


def diagnose_anchors(bars,t,l,r,s):
    """Explain the existing hard checks for inspection; never changes a run's execution or saved state."""
    if not max(s.prior_advance_lookback,t-s.history_window+1)<=l<r<t:
        return [dict(name='anchor_order',value=False,passed=False)]
    b=min(range(l,r+1),key=lambda j:bars[j].low)
    L,R,B=bars[l].high,bars[r].high,bars[b].low
    handle=bars[r+1:t]
    if not handle:return [dict(name='handle_sessions',value=0,minimum=s.handle_min,maximum=s.handle_max,passed=False,unit='sessions')]
    S=min(x.low for x in handle);P=max(x.high for x in bars[r:t])
    checks=[]
    def add(name,value,minimum=None,maximum=None,unit='ratio',strict=False):
        passed=(minimum is None or (value>minimum if strict else value>=minimum)) and (maximum is None or value<=maximum)
        checks.append(dict(name=name,value=value,minimum=minimum,maximum=maximum,passed=passed,unit=unit,strict_minimum=strict))
    add('cup_sessions',r-l+1,s.cup_min,s.cup_max,'sessions')
    add('handle_sessions',t-r-1,s.handle_min,s.handle_max,'sessions')
    add('bottom_internal',int(l<b<r),1,1,'boolean')
    add('rim_difference',abs(R-L)/L,0,s.rim_tolerance)
    add('cup_depth',(L-B)/L,s.depth_min,s.depth_max)
    add('prior_advance',L/bars[l-s.prior_advance_lookback].close-1,s.prior_advance)
    add('handle_above_midpoint',S-(B+s.handle_midpoint_fraction*(L-B)),0,None,'USD')
    add('handle_drop',(R-S)/R,0,s.handle_max_drop)
    add('breakout_extension',bars[t].close/P-1,s.breakout_buffer,s.max_breakout_extension,strict=True)
    add('target_headroom',P+s.target_multiple*(R-B)-bars[t].close,0,None,'USD',strict=True)
    return checks


def mean_true_range(bars,i,period=20):
    if i<period or i>=len(bars):
        raise ValueError('Volatility requires covered prior sessions')
    value=sum(max(bars[j].high-bars[j].low,abs(bars[j].high-bars[j-1].close),
                  abs(bars[j].low-bars[j-1].close)) for j in range(i-period+1,i+1))/period
    if value<=0:raise ValueError('Volatility unit must be positive')
    return value


def shortlist(bars,i,s,symbol):
    """Pure prefix-only geometry selection; no model anchors or future return ranking."""
    dates={b.date:j for j,b in enumerate(bars[:i+1])}
    pairs=feasible_anchors(bars,i,s)
    pairs.sort(key=lambda p:(abs(bars[dates[p['right_rim']]].high-bars[dates[p['left_rim']]].high)/bars[dates[p['left_rim']]].high,
                             -p['cup_sessions'],p['right_rim'],p['left_rim']))
    selected=[]
    for p in pairs:
        l,r,b=[dates[p[k]] for k in ['left_rim','right_rim','bottom']]
        duplicate=False
        for q in selected:
            ql,qr,qb=[dates[q[k]] for k in ['left_rim','right_rim','bottom']]
            overlap=max(0,min(r,qr)-max(l,ql)+1)/(max(r,qr)-min(l,ql)+1)
            if abs(b-qb)<=s.bottom_merge_sessions and overlap>=s.candidate_overlap:
                duplicate=True;break
        if duplicate:continue
        L,R,B=bars[l].high,bars[r].high,bars[b].low
        cup=bars[l:r+1];handle=bars[r+1:i]
        p=dict(p,volatility_unit=mean_true_range(bars,i,s.volatility_period),
               visible_start=bars[max(0,i-s.history_window+1)].date,
               handle_start=handle[0].date,handle_end=handle[-1].date,
               left_high=L,right_high=R,bottom_low=B,
               bottom_band_price=B+.25*(L-B),
               bottom_dwell_fraction=sum(x.low<=B+.25*(L-B) for x in cup)/len(cup),
               handle_retrace_of_cup=(R-p['stop'])/(R-B),
               handle_volume_ratio=(sum(x.volume for x in handle)/len(handle))/(sum(x.volume for x in cup)/len(cup)) if sum(x.volume for x in cup)>0 else None,
               numeric_checks=diagnose_anchors(bars,i,l,r,s))
        digest=hashlib.sha256(json.dumps([symbol,bars[i].date,p],sort_keys=True).encode()).hexdigest()[:12]
        p.update(candidate_id=f'{symbol}-{bars[i].date}-{digest}',rank=len(selected)+1)
        selected.append(p)
        if len(selected)>=s.max_candidates:break
    return selected


def validate_batch(batch,candidates,bars,i):
    expected={c['candidate_id'] for c in candidates}
    actual=[d.candidate_id for d in batch.assessments]
    if set(actual)!=expected or len(actual)!=len(expected):
        raise ValueError('Batch must cover each offered candidate exactly once')
    first=min(c['visible_start'] for c in candidates)
    visible={b.date for b in bars[:i+1] if b.date>=first}
    by_id={c['candidate_id']:c for c in candidates}
    for d in batch.assessments:
        c=by_id[d.candidate_id]
        for check in d.checks:
            if check.start_date not in visible or check.end_date not in visible or check.start_date>check.end_date:
                raise ValueError('Evidence dates outside visible window')
            start=c['handle_start'] if check.name=='handle' else c['left_rim']
            end=c['right_rim'] if check.name=='cup' else c['handle_end']
            if check.start_date<start or check.end_date>end:
                raise ValueError(f'Evidence must stay in the fixed {check.name} region for candidate {d.candidate_id}')
    verdicts={d.candidate_id:d.verdict for d in batch.assessments}
    accepted=next((c for c in candidates if verdicts[c['candidate_id']]=='pass'),None)
    return {'accepted':accepted is not None,'reason':'bound_candidate_pass' if accepted else 'no_model_pass','pattern':accepted}


def rank_symbols(data,indices,s):
    if s.entry_priority=='alphabetical':return sorted(data)
    def score(symbol):
        b=data[symbol];i=indices[symbol]
        if i < required_history(s):
            return 1, 0, symbol
        reference=b[max(0,i-s.priority_lookback)].close if s.entry_priority=='momentum' else max(x.high for x in b[max(0,i-s.breakout_lookback):i])
        return 0, -(b[i].close/reference-1),symbol
    return sorted(data,key=score)
