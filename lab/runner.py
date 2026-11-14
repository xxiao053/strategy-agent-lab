import json
import os
import threading
from pathlib import Path
from pydantic import ValidationError
from .contracts import Bar, CandidateBatch, RunConfig
from .market import load_snapshot, snapshot_id
from .strategy import screen, feasible_anchors, shortlist, validate_batch, rank_symbols, required_history
from .account import Account
from .store import fingerprint
from .providers import Adapter, PROVIDERS, ProviderError, normalize_usage
from .billing import reserve_cost,record_pricing,settlement,usage_reported
from .prompts import make_context, tool_result

ENGINE_VERSION = 'bound-cup-account-v2'


class Paused(RuntimeError):
    pass


class Runner:
    def __init__(self, root: Path, store, client=None):
        self.root, self.store, self.client = root, store, client
        self.lock = threading.Lock()
        self.active = set()

    def preflight(self, config):
        data = load_snapshot(self.root, config.symbols, config.start, config.end,
                             required_warmup=required_history(config.strategy))
        rows = []
        for symbol, bars in data.items():
            for i, bar in enumerate(bars):
                if config.start <= bar.date < config.end and screen(bars, i, config.strategy)['pass']:
                    pairs = feasible_anchors(bars, i, config.strategy)
                    rows.append(dict(symbol=symbol, date=bar.date, pairs=len(pairs), anchors=shortlist(bars,i,config.strategy,symbol) if pairs else []))
        return dict(candidates=len(rows), numeric_dates=sum(bool(r['pairs']) for r in rows),
                    data_id=snapshot_id(data), rows=rows,
                    caveat='Always-flat opportunities, not trades or requests. Holdings reduce nodes; tools/retries add requests.')

    def create(self, config):
        if not config.approved:
            raise ValueError('Confirm and approve the supported method before running')
        if config.mode == 'live':
            if config.budget_scope:
                self.store.budget_status(config.budget_scope)
            if not os.getenv(PROVIDERS[config.provider]['env']):
                raise ValueError(f'Configure {PROVIDERS[config.provider]["env"]} server-side first')
            if config.provider != 'openai' and config.model == 'gpt-6-luna':
                raise ValueError('Enter this provider’s actual model/deployment ID and USD-equivalent token rates')
            default_model = config.provider == 'openai' and config.model == 'gpt-6-luna'
            if not default_model and not config.pricing_confirmed:
                raise ValueError('Confirm model-specific pricing and USD-equivalent rate source before live inference')
            if not default_model and not config.capabilities_confirmed:
                raise ValueError('Confirm selected-model capabilities for images/tools before live inference')
            if config.use_images and not PROVIDERS[config.provider]['images']:
                raise ValueError('Select a vision-capable provider or explicitly disable images for a text-only experiment')
        data = load_snapshot(self.root, config.symbols, config.start, config.end,
                             required_warmup=required_history(config.strategy))
        return self.store.create(config.model_dump(), {s: [b.model_dump() for b in bars] for s,bars in data.items()}, snapshot_id(data))

    def replay(self, rid):
        source = self.store.get(rid, True)
        if source['status'] != 'completed':
            raise ValueError('Only a completed run can be replayed')
        # Freeze the root response/execution source, not a replay with no receipts of its own.
        visited = set()
        while source['config']['mode'] == 'replay':
            if source['id'] in visited:
                raise ValueError('Replay source cycle')
            visited.add(source['id'])
            source = self.store.get(source['config']['replay_of'], True)
        if source['archived']:
            # Exact archival view, NOT running old decisions through new trading rules.
            cfg=json.loads(json.dumps(source['config']))
            cfg.update(mode='replay',replay_of=source['id'],paid_authorized=False)
            archived=self.store.create(cfg,source['data'],source['data_id'])
            self.store.checkpoint(archived['id'],source['state'])
            self.store.status(archived['id'],'completed','Archived state copy; not recalculated by the current engine')
            return self.store.get(archived['id'])
        cfg=RunConfig.model_validate(source['config'])
        cfg.mode, cfg.replay_of, cfg.paid_authorized = 'replay', source['id'], False
        return self.store.create(cfg.model_dump(), source['data'], source['data_id'])

    def launch(self, rid):
        with self.lock:
            if rid in self.active:
                return
            if self.active:
                raise ValueError('One local run at a time; pause the current run first')
            self.active.add(rid)
        self.store.stop(rid, False)
        def work():
            try:
                self.execute(rid)
            finally:
                with self.lock:
                    self.active.discard(rid)
        threading.Thread(target=work, name='research-worker', daemon=True).start()

    def execute(self, rid):
        run = self.store.get(rid, True)
        if run['status'] == 'completed':
            return
        if run['archived']:
            self.store.status(rid,'paused','Archived engine/configuration; create a new v2 research run')
            return
        config = RunConfig.model_validate(run['config'])
        bars = {s: [Bar.model_validate(b) for b in rows] for s,rows in run['data'].items()}
        days = [b.date for b in next(iter(bars.values())) if config.start <= b.date <= config.end]
        lookups = {s: {b.date:i for i,b in enumerate(rows)} for s,rows in bars.items()}
        state = run['state'] or dict(engine=ENGINE_VERSION, day=0, account=Account(config.capital).dump(), decisions=[], benchmark=[])
        if state['engine'] != ENGINE_VERSION:
            self.store.status(rid, 'paused', 'Engine version changed; create a new experiment')
            return
        self.store.status(rid, 'running')
        try:
            for day_n in range(state['day'], len(days)):
                if self.store.stopped(rid):
                    raise Paused('Paused by user at a safe checkpoint')
                day = days[day_n]
                a = Account(config.capital, json.loads(json.dumps(state['account'])))
                decisions = list(state['decisions'])
                indices = {s:lookups[s][day] for s in bars}
                a.open_day(day, {s:bars[s][i].open for s,i in indices.items()}, config.strategy)
                a.close_day(day, {s:bars[s][i].close for s,i in indices.items()}, config.strategy)
                if day != config.end:
                    for symbol in rank_symbols(bars,indices,config.strategy):
                        if self.store.stopped(rid):
                            raise Paused('Paused by user; current day will resume from saved responses')
                        if symbol in a.positions or any(o['symbol']==symbol and o['status']=='pending' for o in a.orders):
                            continue
                        i, series = indices[symbol], bars[symbol]
                        candidate = screen(series, i, config.strategy)
                        if not candidate['pass']:
                            continue
                        pairs = feasible_anchors(series, i, config.strategy)
                        candidates=shortlist(series,i,config.strategy,symbol) if pairs else []
                        event = dict(id=f'{day}:{symbol}', date=day, symbol=symbol, screen=candidate,
                                     feasible_pairs=len(pairs), source='numeric_baseline' if config.mode=='baseline' else 'model',
                                     candidates=candidates,primary_evaluations=[],review_evaluations=[],evaluations=[],
                                     decision=None, validation={'accepted':False,'reason':'no_numeric_anchors'}, order_id=None)
                        if candidates:
                            if config.mode == 'baseline' or (config.mode=='replay' and self.store.get(config.replay_of)['config']['mode']=='baseline'):
                                event['source']='numeric_baseline'
                                event['validation']=dict(accepted=True, reason='code-only first ranked fixed candidate; no semantic LLM check', pattern=candidates[0])
                            else:
                                source_id = config.replay_of if config.mode == 'replay' else rid
                                checks = {c['candidate_id']:a.entry_check(symbol,series[i].close,config.strategy,c) for c in candidates}
                                # Preserve already-paid historical judgments on resume/replay. New
                                # judgments cannot affect orders when every candidate is unexecutable.
                                if not any(c['eligible'] for c in checks.values()) and not self.store.has_stage_requests(source_id,event['id']+':primary'):
                                    event['execution_precheck'] = dict(eligible=False,available_cash=a.available,candidates=checks)
                                    event['validation'] = dict(accepted=False,reason='not_executable',
                                        execution_note='Skipped before model: no candidate fits available cash, sizing or position slots.')
                                    decisions.append(event)
                                    continue
                                ctx = make_context(symbol,series,i,config,candidates=candidates)
                                primary=self.judge(rid,event['id']+':primary',config,ctx,series[max(0,i-config.strategy.history_window+1):i+1],symbol)
                                event['primary_evaluations']=[d.model_dump() for d in primary.assessments]
                                final={d.candidate_id:d for d in primary.assessments}
                                review_ids={d.candidate_id for d in primary.assessments if d.verdict!='pass'}
                                if config.review_enabled and review_ids:
                                    scope=[c for c in candidates if c['candidate_id'] in review_ids]
                                    prior=[d for d in event['primary_evaluations'] if d['candidate_id'] in review_ids]
                                    ctx=make_context(symbol,series,i,config,candidates=scope,stage='review',prior_assessments=prior)
                                    review=self.judge(rid,event['id']+':review',config,ctx,series[max(0,i-config.strategy.history_window+1):i+1],symbol)
                                    event['review_evaluations']=[d.model_dump() for d in review.assessments]
                                    final.update({d.candidate_id:d for d in review.assessments})
                                batch=CandidateBatch(assessments=[final[c['candidate_id']] for c in candidates])
                                event['evaluations']=[d.model_dump() for d in batch.assessments]
                                event['validation']=validate_batch(batch,candidates,series,i)
                                selected=event['validation']['pattern'] or candidates[0]
                                event['decision']=final[selected['candidate_id']].model_dump()
                            if event['validation']['accepted']:
                                made = a.enter(symbol,day,series[i].close,event['validation']['pattern']['stop'],config.strategy,pattern=event['validation']['pattern'])
                                event['order_id'] = f'{day}:{symbol}:buy' if made else None
                                if not made:
                                    event['validation']['execution_note']='Slot/cash/risk constraint; no order'
                        decisions.append(event)
                benchmark = list(state['benchmark'])
                value = sum(bars[s][indices[s]].close / bars[s][lookups[s][days[0]]].close for s in bars)/len(bars)*config.capital
                benchmark.append(dict(date=day, equity=round(value,2)))
                state = dict(engine=ENGINE_VERSION, day=day_n+1, account=a.dump(), decisions=decisions, benchmark=benchmark)
                self.store.checkpoint(rid, state)
            self.store.status(rid, 'completed')
        except (Paused, ProviderError, ValueError, KeyError):
            # These messages are controlled, except validation errors: never expose submitted secrets or full inputs.
            import sys
            error = sys.exception()
            if isinstance(error, (Paused, ProviderError)):
                reason = str(error)
            else:
                reason = 'Validation/execution error; no progress beyond last safe checkpoint. Inspect saved records.'
            self.store.status(rid, 'paused', reason)
        except Exception:
            self.store.status(rid, 'paused', 'Unexpected local error; last checkpoint preserved. No automatic retry.')

    def judge(self, rid, node, config, context, visible, symbol):
        adapter = Adapter(config.provider, self.client)
        source_id = config.replay_of if config.mode=='replay' else rid
        recovery = self.store.output_recovery(source_id,node)
        if recovery:
            if fingerprint(self.store.requests(source_id,node)) != recovery['source_receipts_hash']:
                raise Paused('Recovery source receipts changed; inspect before inference')
            node = recovery['recovery_node']
        receipts = self.store.requests(source_id,node)
        if receipts:
            # Select an archived wire schema only when the entire original
            # initial payload matches, across every provider's native encoding.
            legacy = dict(context, schema=CandidateBatch.model_json_schema())
            old_url, old_payload = adapter.build(config, legacy, [], allow_tools=True)
            if fingerprint(dict(url=old_url,payload=old_payload,engine=ENGINE_VERSION)) == receipts[0]['request_hash']:
                context = legacy
        history, used_tool, repaired = [], False, False
        for attempt in range(3):
            url, payload = adapter.build(config, context, history, allow_tools=not used_tool)
            request_hash = fingerprint(dict(url=url, payload=payload, engine=ENGINE_VERSION))
            key = f'{source_id}:{node}:{attempt}'
            saved = next((r for r in self.store.requests(source_id,node) if r['id']==key), None)
            if not saved and config.mode=='live' and config.reuse_responses_from:
                source=next((r for r in self.store.requests(config.reuse_responses_from) if r['status'] in {'complete','reused'} and r['request_hash']==request_hash),None)
                if source:
                    self.store.reuse_response(rid,node,key,request_hash,dict(url=url,body=payload),source)
                    saved=next(r for r in self.store.requests(rid) if r['id']==key)
            if saved:
                if saved['request_hash'] != request_hash:
                    raise Paused('Saved request differs from current prompt/configuration; create a new run')
                if saved['status'] in {'sent','unknown'}:
                    raise Paused('Previous request outcome unknown. Acknowledge possible duplicate billing before retrying.')
                if saved['status'] in {'acknowledged','failed'}:
                    repaired = True
                    continue
                raw = saved['raw']
            else:
                if config.mode == 'replay':
                    raise Paused('Replay source has no matching saved response; no live fallback')
                summary = self.store.get(rid)['summary']
                # Conservative reservation, not a provider billing guarantee. UTF-8 bytes bound text tokens;
                # image allocation is deliberately generous and disclosed. Request count is strictly enforced.
                input_bound = len(json.dumps(payload, ensure_ascii=False).encode()) + (20000 if config.use_images else 0)
                pricing_cfg=dict(provider=config.provider,model=config.model,input_price=config.input_rate,output_price=config.output_rate)
                reserved = reserve_cost(pricing_cfg,input_bound,config.max_output_tokens)
                if summary['requests'] >= config.max_requests or summary['estimated_cost']+summary['unresolved_reserve']+reserved > config.budget_usd:
                    raise Paused('Request limit or conservative estimated budget exhausted before dispatch')
                if config.budget_scope:
                    shared=self.store.budget_status(config.budget_scope)
                    if shared['committed_usd']+reserved>shared['cap_usd']:
                        raise Paused('Shared spending authorization exhausted before dispatch')
                try:
                    self.store.begin_request(rid, node, key, request_hash, reserved, dict(url=url, body=payload,billing=record_pricing(pricing_cfg)))
                except ValueError as error:
                    raise Paused(str(error)) from None
                def save(raw, elapsed):
                    reported = raw.get('usageMetadata' if config.provider=='gemini' else 'usage') or {}
                    usage = normalize_usage(config.provider, reported)
                    usage['reported'] = usage_reported(config.provider,raw)
                    usage.update(accounting_version=2,**settlement(pricing_cfg,usage if usage['reported'] else None,reserve=reserved))
                    self.store.save_response(key, raw, usage, elapsed)
                try:
                    reply = adapter.send(config, context, history, os.getenv(PROVIDERS[config.provider]['env'], ''),
                                         allow_tools=not used_tool, save_raw=save)
                    raw = reply.raw
                except ProviderError as error:
                    if not next(r for r in self.store.requests(rid) if r['id']==key)['raw']:
                        self.store.request_status(key, 'unknown' if error.ambiguous else 'failed', str(error))
                    raise
            try:
                reply = adapter.parse(raw)
                if reply.tool_calls:
                    if not config.use_tools:
                        raise ValueError('Tools disabled for this research run')
                    if used_tool or len(reply.tool_calls) != 1:
                        raise ValueError('Tool budget exceeded')
                    used_tool = True
                    result = tool_result(reply.tool_calls[0],symbol,visible,candidates=context['candidates'])
                    if not config.use_images:result.pop('_image',None)
                    history += adapter.followup(reply, [result])
                    continue
                decision = CandidateBatch.parse_reply(reply.text)
                validate_batch(decision,context['candidates'],visible,len(visible)-1)
                return decision
            except (ValueError, ValidationError, ProviderError, KeyError) as error:
                if repaired:
                    raise Paused('Invalid/incomplete model decision after one repair; saved responses retained')
                repaired = True
                if 'reply' in locals() and reply.raw is raw:
                    if reply.tool_calls:
                        history+=adapter.followup(reply,[{'error':'Tool budget exceeded; no additional tools executed'} for _ in reply.tool_calls])
                    else:
                        history+=adapter.assistant_items(reply)
                detail=json.dumps(error.errors(include_input=False,include_url=False),default=str) if isinstance(error,ValidationError) else str(error)
                if context['schema']['properties']['assessments'].get('type') == 'object':
                    expected = [c['candidate_id'] for c in context['candidates']]
                    actual = []
                    try:
                        actual = [d.candidate_id for d in CandidateBatch.parse_reply(reply.text).assessments]
                    except (ValueError, TypeError, AttributeError):
                        pass
                    detail += f' Missing IDs: {sorted(set(expected)-set(actual))}; unexpected IDs: {sorted(set(actual)-set(expected))}. Return assessments as an object keyed by every required candidate ID.'
                history.append(adapter.correction(f'Decision close is {visible[-1].date}. Validation error: {detail[:2500]}. Correct the previous batch once. Cover each offered candidate ID exactly once; never provide alternate anchors. Each overall verdict must equal its rubric aggregation: any fail => fail; otherwise any insufficient_evidence => insufficient_evidence; otherwise pass. A handle completed before breakout is expected. Use only visible ISO dates. Return complete JSON. No further tools.'))
                used_tool = True
        raise Paused('Per-candidate request limit reached; inspect saved responses')
