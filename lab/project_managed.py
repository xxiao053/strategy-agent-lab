"""Generic approved risk policy over the shared account; no method-specific screening."""
import copy
from .account import Account,money
from .execution_contract import digest,validate_decision
from .project_history import compact_context


def snapshot(account,closes):
    return dict(cash=account.cash,equity=account.equity(closes),available_cash=account.available,
                positions={s:p['quantity'] for s,p in account.positions.items()},position_details=copy.deepcopy(account.positions))


def orders(account):
    result=[]
    for source in account.orders:
        o=dict(source,action=source['side'])
        o['reason']=source.get('reason') or ('cancelled_gap' if source['status']=='cancelled_gap' else 'next_session_open')
        o['explanation']=source.get('explanation','Approved account exit: '+o['reason'])
        if source['status']=='cancelled_gap':o['status']='cancelled'
        if source['status']=='filled':o.update(date=source['fill_date'],price=source['fill_price'],gross=money(source['quantity']*source['fill_price']))
        result.append(o)
    return result


def simulate_managed(data,manifest,evaluator,config,*,judge,on_progress,cancelled,compact_inputs):
    from .project_runner import validate_data,reserve_day
    sessions=validate_data(data,manifest,config);policy=manifest.account
    if config['fee_rate']!=policy.commission:raise ValueError('Run fee must match the approved account commission.')
    account=Account(config['initial_cash'])
    result=dict(status='running',curve=[],trades=[],orders=[],decisions=[],inputs={},positions={},state={},completed_sessions=0,total_sessions=len(sessions))
    indices={s:{b.date:i for i,b in enumerate(rows)} for s,rows in data.items()}

    def sync():
        result['orders']=orders(account);result['trades']=[o for o in result['orders'] if o['status']=='filled']
        result['positions']={s:p['quantity'] for s,p in account.positions.items()}

    def stop_pending(reason,status='cancelled',preserve_reason=False):
        for order in account.orders:
            if order['status']=='pending':
                if preserve_reason and order.get('reason'):order.update(status=status,unfilled_reason=reason)
                else:order.update(status=status,reason=reason)
                d=next((d for d in result['decisions'] if d['id']==order.get('decision_id')),None)
                if d:d['status']=status

    for day in sessions:
        if cancelled():result['status']='cancelled';break
        visible={s:[b.model_dump() for b in rows[max(0,indices[s][day]-manifest.history_bars+1):indices[s][day]+1]] for s,rows in data.items()}
        pending=[o for o in account.orders if o['status']=='pending']
        if not reserve_day(result,visible,pending,manifest,compact_inputs=compact_inputs):
            stop_pending('evidence_limit');result['status']='failed';sync();on_progress(copy.deepcopy(result))
            raise ValueError('Run evidence capacity reached before the next session; no new fill, decision or model request executed.')
        opens={s:rows[-1]['open'] for s,rows in visible.items()};closes={s:rows[-1]['close'] for s,rows in visible.items()}
        account.open_day(day,opens,policy);fills=copy.deepcopy([o for o in orders(account) if o.get('fill_date')==day])
        account.close_day(day,closes,policy)
        context=dict(schema='strategy-v1',cutoff=day,bars=visible,account=snapshot(account,closes),
                     state=copy.deepcopy(result['state']),previous_orders=fills)
        result['inputs'][day]=compact_context(context,manifest.history_bars) if compact_inputs else copy.deepcopy(context)
        input_hash=digest(context)

        def decision(p,ident,status):
            value=dict(id=ident,cutoff=day,proposal=p,status=status,input_hash=input_hash,evidence={p['symbol']:visible[p['symbol']]},
                       account=snapshot(account,closes),previous_orders=fills,rule=p['explanation'],model=None)
            result['decisions'].append(value);return value

        def accepts_judgment(d,p):
            if not p['judgment']:return True
            if judge is None:raise ValueError('Execution model judgment is required but unavailable.')
            try:d['model']=judge(d,context,p)
            except ValueError as exc:
                d.update(status=str(exc).split(':')[0],error=str(exc));raise
            verdict=d['model']['verdict'];d['status']=verdict
            if verdict=='insufficient_evidence' and manifest.judgment.uncertainty=='stop':
                raise ValueError('Model evidence insufficient; method requires stopping.')
            return verdict=='pass'

        for order in account.orders:
            if order['signal_date']==day and order['side']=='sell' and 'decision_id' not in order:
                order['decision_id']=f'{day}-exit-{order["symbol"]}'
                decision(dict(symbol=order['symbol'],action='sell',sizing={'shares':order['quantity']},judgment=None,
                              explanation='Approved account exit: '+order['reason']),order['decision_id'],'ordered')
        try:
            output=validate_decision(evaluator.decide(context),manifest,list(data));result['state']=copy.deepcopy(output['state'])
            for i,p in enumerate(sorted(output['proposals'],key=lambda p:(-p['priority'],p['symbol']))):
                if cancelled():result['status']='cancelled';break
                d=decision(p,f'{day}-{i+1}','hold' if p['action']=='hold' else 'proposed')
                if p['action']=='hold':continue
                if p['action']=='sell':
                    position=account.positions.get(p['symbol'])
                    if not position or position['quantity']!=p['sizing']['shares'] or any(o['symbol']==p['symbol'] and o['status']=='pending' for o in account.orders):
                        d['status']='sizing_rejected';continue
                    if day==sessions[-1]:d['status']='unfilled';d['reason']='no_next_session';continue
                    if not accepts_judgment(d,p):continue
                    if cancelled():result['status']='cancelled';break
                    account.orders.append(dict(id=d['id']+'-order',decision_id=d['id'],symbol=p['symbol'],side='sell',
                        quantity=position['quantity'],signal_date=day,status='pending',reason='strategy_exit',explanation=p['explanation']))
                    d['status']='ordered';continue
                dates={b['date'] for b in visible[p['symbol']]};close=closes[p['symbol']]
                for c in p['candidates']:
                    if not set(c['dates'].values())<=dates:raise ValueError('Candidate date outside visible cutoff history.')
                    if not c['stop']<close<c['target']:raise ValueError('Candidate must bracket the signal close.')
                checks={c['candidate_id']:account.entry_check(p['symbol'],close,policy,c) for c in p['candidates']}
                d['execution_precheck']=checks
                if not any(c['eligible'] for c in checks.values()):d['status']='sizing_rejected';continue
                if day==sessions[-1]:d['status']='unfilled';d['reason']='no_next_session';continue
                selected=p['candidates'][0]
                if p['judgment']:
                    if not accepts_judgment(d,p):continue
                    selected=next((c for c in p['candidates'] if c['candidate_id']==d['model'].get('selected_candidate_id')),None)
                    if selected is None:raise ValueError('Model selected an unknown candidate.')
                if cancelled():result['status']='cancelled';break
                if account.enter(p['symbol'],day,close,selected['stop'],policy,pattern=selected):
                    account.orders[-1].update(decision_id=d['id'],explanation=p['explanation']);d.update(status='ordered',selected_candidate_id=selected['candidate_id'])
                else:d['status']='sizing_rejected'
        except Exception:
            stop_pending('execution_failed');result['status']='failed'
            result['curve'].append(dict(date=day,**snapshot(account,closes)));sync();on_progress(copy.deepcopy(result));raise
        result['curve'].append(dict(date=day,**snapshot(account,closes)));result['completed_sessions']+=1
        sync();on_progress(copy.deepcopy(result))
        if result['status']=='cancelled':break
    stop_pending('cancelled' if result['status']=='cancelled' else 'no_next_session',status='unfilled',preserve_reason=True)
    sync()
    if result['status']=='running':result['status']='completed'
    return result
