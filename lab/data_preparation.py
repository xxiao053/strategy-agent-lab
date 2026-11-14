"""Explicit trusted market fetch, separate from generated historical execution."""
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from datetime import date
from .execution_contract import resolve_build
from .project_runs import RunOptions
from .market import market_calendar
from .workspace_store import now
from scripts.freeze_market import freeze_symbol

_fetch_lock=threading.Lock()


class DataPreparation:
    def __init__(self,root,store,*,fetch=freeze_symbol):self.root,self.store,self.fetch=Path(root),store,fetch

    def start(self,pid,body):
        if set(body)!={'build_id','symbols','start','end'}:raise ValueError('Choose a build, symbols and dates for data preparation.')
        options=RunOptions.model_validate(dict(body,initial_cash=1,fee_rate=0))
        if options.end>date.today().isoformat() or (date.fromisoformat(options.end)-date.fromisoformat(options.start)).days>1200:
            raise ValueError('Unsupported date scope: choose past trading dates within 1,200 calendar days and 756 sessions.')
        p=self.store.get(pid);build,_,manifest=resolve_build(p,options.build_id)
        calendar=market_calendar(options.start,options.end)
        if not calendar.is_session(options.start) or not calendar.is_session(options.end) or len(calendar.sessions_in_range(options.start,options.end))>756:
            raise ValueError('Choose trading-session dates covering at most 756 sessions.')
        if not _fetch_lock.acquire(blocking=False):raise ValueError('Another data preparation is active. Wait before retrying.')
        ident=uuid.uuid4().hex
        state=dict(id=ident,status='running',created=now(),completed=0,total=len(options.symbols),results={},error=None,scope=body)
        try:
            def begin(current):
                if current['busy'] or resolve_build(current,options.build_id)[0]['execution_hash']!=build['execution_hash']:raise ValueError('Project changed or already has an active task.')
                current.update(busy=True,data_preparation=state)
            self.store.mutate(pid,begin)
            threading.Thread(target=self.execute,args=(pid,ident,body,manifest.warmup_bars),daemon=True).start()
        except BaseException as exc:
            def fail(current):
                if current.get('data_preparation',{}).get('id')==ident:
                    current['busy']=False;current['data_preparation'].update(status='failed',error='Data preparation could not start. No automatic retry.')
            self.store.mutate(pid,fail);_fetch_lock.release()
            if isinstance(exc,ValueError):raise
            raise ValueError('Data preparation could not start. No automatic retry.') from None
        return state

    def execute(self,pid,ident,body,warmup):
        results={}
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures={pool.submit(self.fetch,self.root,symbol,start=body['start'],end=body['end'],required_warmup=warmup,retries=1):symbol for symbol in body['symbols']}
                for future in as_completed(futures):
                    symbol=futures[future]
                    try:results[symbol]=dict(status='completed',receipt=future.result())
                    except Exception:results[symbol]=dict(status='failed',error='Market data unavailable or snapshot validation failed. Existing snapshots were not overwritten.')
                    self.store.mutate(pid,lambda p:p['data_preparation'].update(completed=len(results),results=dict(results)))
            failed=any(r['status']=='failed' for r in results.values())
            self.store.mutate(pid,lambda p:p['data_preparation'].update(status='failed' if failed else 'completed'))
        except Exception:
            self.store.mutate(pid,lambda p:p['data_preparation'].update(status='failed',error='Data preparation interrupted. Saved snapshots retained.'))
        finally:
            self.store.mutate(pid,lambda p:p.update(busy=False))
            _fetch_lock.release()
