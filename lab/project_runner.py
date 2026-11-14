"""Generic historical orchestration; trusted account and cutoff-bound decisions."""
import copy
from .execution_contract import canonical, digest, validate_decision
from .project_account import Account
from .project_limits import MAX_SYMBOLS,MAX_SESSIONS,RESULT_BYTES
from .project_history import compact_context


RESULT_LIMIT=12000000
TERMINAL_HEADROOM=65536


def reserve_day(result,visible,pending,manifest,*,compact_inputs=False):
    """Reserve worst-case bounded output before fills, strategy execution or inference.

    Two copies of bars cover inputs plus per-symbol decision evidence. Per-proposal
    overhead covers the 64 KB decision envelope, account/order/fill metadata and
    duplicated explanations. A model verdict plus two bounded tool payloads fits
    512 KB per proposal (64 KB tool arguments, 120 bars, 3,000-char reason).
    Prior order observations can occur once in input and once per proposal.
    """
    count=len(visible)
    growth=2*len(canonical(visible).encode())+count*65536+(count+2)*len(canonical(pending).encode())+32768
    if manifest.judgment:growth+=count*512000
    return len(canonical(result).encode())+growth+TERMINAL_HEADROOM<=(RESULT_BYTES if compact_inputs else RESULT_LIMIT)


def validate_data(data,manifest,config):
    if not 1<=len(data)<=MAX_SYMBOLS:raise ValueError(f'Choose 1–{MAX_SYMBOLS} available symbols.')
    sessions=None
    for symbol,bars in data.items():
        dates=[b.date for b in bars]
        if dates!=sorted(set(dates)):raise ValueError('Invalid market session ordering.')
        selected=[d for d in dates if config['start']<=d<=config['end']]
        if not selected or selected[0]!=config['start'] or selected[-1]!=config['end']:
            raise ValueError('Missing requested market sessions/data.')
        if dates.index(config['start'])<manifest.warmup_bars:raise ValueError('Insufficient history for declared warmup.')
        if sessions is not None and sessions!=selected:raise ValueError('Symbols have unaligned market sessions.')
        sessions=selected
    if len(sessions)>MAX_SESSIONS:raise ValueError(f'At most {MAX_SESSIONS} decision sessions per run.')
    return sessions


def simulate(data,manifest,evaluator,config,*,judge=None,on_progress=lambda r:None,cancelled=lambda:False,compact_inputs=False):
    if manifest.account:
        from .project_managed import simulate_managed
        return simulate_managed(data,manifest,evaluator,config,judge=judge,on_progress=on_progress,cancelled=cancelled,compact_inputs=compact_inputs)
    sessions=validate_data(data,manifest,config)
    account=Account(config['initial_cash'],config['fee_rate'])
    result=dict(status='running',curve=[],trades=[],orders=[],decisions=[],inputs={},positions={},state={},completed_sessions=0,total_sessions=len(sessions))
    pending=[];indices={s:{b.date:i for i,b in enumerate(bars)} for s,bars in data.items()}
    for day in sessions:
        if cancelled():result['status']='cancelled';break
        visible={s:[b.model_dump() for b in bars[max(0,indices[s][day]-manifest.history_bars+1):indices[s][day]+1]] for s,bars in data.items()}
        if not reserve_day(result,visible,pending,manifest,compact_inputs=compact_inputs):
            for order in pending:order.update(status='cancelled',reason='evidence_limit')
            result['status']='failed'
            on_progress(copy.deepcopy(result))
            raise ValueError('Run evidence capacity reached before the next session; no new fill, decision or model request executed.')
        opens={s:rows[-1]['open'] for s,rows in visible.items()};closes={s:rows[-1]['close'] for s,rows in visible.items()}
        account.fill(pending,opens,day)
        fills=copy.deepcopy(pending);pending=[]
        result['trades']=[dict(o) for o in result['orders'] if o['status']=='filled']
        context=dict(schema='strategy-v1',cutoff=day,bars=visible,account=account.snapshot(closes),
                     state=copy.deepcopy(result['state']),previous_orders=fills)
        result['inputs'][day]=compact_context(context,manifest.history_bars) if compact_inputs else copy.deepcopy(context)
        reserved_cash=0
        try:
            output=validate_decision(evaluator.decide(context),manifest,list(data))
            result['state']=copy.deepcopy(output['state'])
            for i,p in enumerate(output['proposals']):
                did=f'{day}-{i+1}'
                d=dict(id=did,cutoff=day,proposal=p,status='hold' if p['action']=='hold' else 'proposed',
                       input_hash=digest(context),evidence={p['symbol']:visible[p['symbol']]},account=account.snapshot(closes),
                       previous_orders=fills,rule=p['explanation'],model=None)
                result['decisions'].append(d)
                if p['action']=='hold':continue
                if not account.eligible(p,closes,reserved_cash):d['status']='sizing_rejected';continue
                if day==sessions[-1]:
                    o=account.order(p,did,day);o.update(status='unfilled',reason='no_next_session')
                    result['orders'].append(o);d['status']='unfilled';continue
                if p['judgment']:
                    if judge is None:raise ValueError('Execution model judgment is required but unavailable.')
                    try:d['model']=judge(d,context,p)
                    except ValueError as exc:
                        kind=str(exc).split(':')[0]
                        d['status']=kind if kind in {'infrastructure_failure','invalid_response','missing_evidence','cancelled'} else 'judgment_blocked'
                        d['error']=str(exc)
                        raise
                    verdict=d['model']['verdict'];d['status']=verdict
                    if verdict=='insufficient_evidence' and manifest.judgment.uncertainty=='stop':
                        raise ValueError('Model evidence insufficient; method requires stopping.')
                    if verdict!='pass':continue
                if cancelled():result['status']='cancelled';break
                o=account.order(p,did,day);result['orders'].append(o);pending.append(o);d['status']='ordered'
                if p['action']=='buy':reserved_cash+=sum(account.amounts(closes[p['symbol']],p['sizing']['shares']))
        except Exception:
            for order in pending:order.update(status='cancelled',reason='execution_failed')
            result['curve'].append(dict(date=day,**account.snapshot(closes)))
            result.update(status='failed',positions=dict(account.positions))
            on_progress(copy.deepcopy(result));raise
        snapshot=account.snapshot(closes)
        result['curve'].append(dict(date=day,**snapshot));result['positions']=snapshot['positions']
        result['completed_sessions']+=1
        on_progress(copy.deepcopy(result))
        if result['status']=='cancelled':break
    for order in pending:
        order.update(status='unfilled',reason='cancelled' if result['status']=='cancelled' else 'no_next_session')
    if result['status']=='running':result['status']='completed'
    return result
