"""Durable project-local historical runs, separated from ordinary project polling."""
import json
import threading
import uuid
from pathlib import Path
from pydantic import Field, field_validator, model_validator
from .contracts import iso, Bar
from .execution_contract import Strict, canonical, digest, resolve_build
from .market import select_source, snapshot_id, PRICE_BASIS_NOTE
from .universe import SYMBOLS
from .workspace_store import now
from .project_evaluator import IsolatedEvaluator
from .project_judgment import BoundedJudgment
from .project_runner import simulate, validate_data
from .project_limits import MAX_SYMBOLS,MAX_SESSIONS,MAX_MODEL_REQUESTS,STORED_RUN_BYTES,FROZEN_INPUT_BYTES


class RunOptions(Strict):
    build_id: str=Field(min_length=1,max_length=100)
    symbols: list[str]=Field(min_length=1,max_length=MAX_SYMBOLS)
    start: str
    end: str
    initial_cash: float=Field(gt=0,le=100000000)
    fee_rate: float=Field(ge=0,le=.05)
    authorized: bool=False
    budget: float=Field(default=0,ge=0,le=100)
    connection_id: str | None=None
    _dates=field_validator('start','end')(iso)

    @model_validator(mode='after')
    def check(self):
        if self.start>self.end:raise ValueError('Start must precede end.')
        if len(set(self.symbols))!=len(self.symbols) or not set(self.symbols)<=set(SYMBOLS):
            raise ValueError('Select unique symbols from the current US stock/ETF catalog.')
        return self


class ProjectRuns:
    evaluator_factory=IsolatedEvaluator

    def __init__(self,root,store,connections):
        self.root,self.store,self.connections=Path(root),store,connections
        with store.lock,store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS project_runs(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, document TEXT NOT NULL)')
            rows=db.execute('SELECT id,project_id,document FROM project_runs').fetchall()
            interrupted=[]
            for rid,pid,text in rows:
                r=json.loads(text)
                if r['status']=='running':
                    r.update(status='interrupted',error='Server restarted; evidence and spend retained. No automatic resume.',updated=now())
                    db.execute('UPDATE project_runs SET document=? WHERE id=?',(canonical(r),rid));interrupted.append(pid)
        for pid in interrupted:store.mutate(pid,lambda p:p.update(busy=False))

    @staticmethod
    def summary(r):
        return {k:r.get(k) for k in ['id','build_id','version','created','updated','status','error','completed_sessions','total_sessions','cancel_requested']}

    def list(self,pid):
        self.store.get(pid)
        with self.store.connect() as db:
            return [self.summary(json.loads(row[0])) for row in db.execute('SELECT document FROM project_runs WHERE project_id=? ORDER BY rowid DESC',(pid,))]

    def get(self,pid,rid):
        with self.store.connect() as db:
            row=db.execute('SELECT document FROM project_runs WHERE project_id=? AND id=?',(pid,rid)).fetchone()
        if row is None:raise KeyError(rid)
        return json.loads(row[0])

    def update(self,pid,rid,**changes):
        with self.store.lock,self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT document FROM project_runs WHERE project_id=? AND id=?',(pid,rid)).fetchone()
            if row is None:raise KeyError(rid)
            r=json.loads(row[0]);r.update(changes,updated=now())
            if len(canonical(r).encode())>STORED_RUN_BYTES:raise ValueError('Stored run exceeds 160 MiB limit.')
            db.execute('UPDATE project_runs SET document=? WHERE id=?',(canonical(r),rid))
        return r

    def load_market(self,symbols,start,end,warmup):
        data={};refs={}
        for symbol in symbols:
            path,receipt,bars,validation=select_source(self.root,symbol,start,end,required_warmup=warmup)
            data[symbol]=bars;refs[symbol]=dict(source=path.relative_to(self.root).as_posix(),receipt=receipt,validation=validation)
        return data,refs

    def start(self,pid,body):
        try:options=RunOptions.model_validate(body)
        except ValueError:raise ValueError('Invalid run configuration. Choose catalog symbols, ISO dates, positive cash and fees between 0 and 5%.') from None
        project=self.store.get(pid)
        if project['busy']:raise ValueError('Project already has an active task.')
        build,version,manifest=resolve_build(project,options.build_id)
        if manifest.account and options.fee_rate!=manifest.account.commission:
            raise ValueError('Run fee must match the approved account commission.')
        cfg=None
        if manifest.judgment:
            if not options.authorized or options.budget<=0:raise ValueError('Authorize execution-model spending within the shared project budget.')
            cid=project['model_roles']['execution']
            if cid is None or options.connection_id!=cid:raise ValueError('Save and select the project execution connection; no builder fallback.')
            cfg,_=self.connections.get(cid)
            if manifest.judgment.input_mode=='chart_and_text':
                from .image_policy import require_connection
                require_connection(cfg)
        data,refs=self.load_market(options.symbols,options.start,options.end,manifest.warmup_bars)
        assumptions=options.model_dump(exclude={'authorized','connection_id'})
        sessions=validate_data(data,manifest,assumptions)
        frozen=dict(method=version['method'],build_hash=build['execution_hash'],artifacts=build['artifacts'],
                    manifest=manifest.model_dump(by_alias=True),market_hash=snapshot_id(data),market_sources=refs,
                    model=cfg,assumptions=assumptions,price_basis=PRICE_BASIS_NOTE,
                    platform=dict(fill='next_session_open',long_only=True,integer_shares=True,max_sessions=MAX_SESSIONS,max_symbols=MAX_SYMBOLS,
                                  compact_inputs=len(options.symbols)>10 or len(sessions)>100,
                                  max_requests=MAX_MODEL_REQUESTS,max_model_roundtrips=3 if manifest.judgment and manifest.judgment.repair_once else 2,
                                  max_output_tokens=4096 if manifest.judgment and manifest.judgment.rubric else 1500,final_liquidation=False))
        if manifest.judgment and manifest.judgment.input_mode=='chart_and_text':
            from .image_policy import POLICY,NORMALIZATION,RATE_MULTIPLIERS,MIN_IMAGE_TOKENS
            frozen['image_policy']=dict(policy=POLICY,billing_profile='token-v1',rate_multipliers=dict(RATE_MULTIPLIERS),minimum_image_input_tokens=MIN_IMAGE_TOKENS,normalization=NORMALIZATION,renderer='ohlcv-v1',max_images=2,max_wire_bytes=1600000,max_chart_bars=120)
            if manifest.judgment.rubric:
                frozen['image_policy'].update(renderer='ohlcv-v2',max_images=10,max_wire_bytes=8*1024*1024)
            if manifest.judgment.chart_history=='declared':
                frozen['image_policy'].update(renderer='ohlcv-v2',max_chart_bars=manifest.judgment.history_bars or manifest.history_bars)
        frozen['run_hash']=digest(frozen)
        rid=uuid.uuid4().hex
        r=dict(id=rid,build_id=build['id'],version=version['version'],created=now(),updated=now(),status='running',error=None,
               completed_sessions=0,total_sessions=len(sessions),cancel_requested=False,frozen=frozen,
               market={s:[b.model_dump() for b in rows] for s,rows in data.items()},curve=[],trades=[],orders=[],decisions=[],positions={},state={})
        if len(canonical(r).encode())>FROZEN_INPUT_BYTES:raise ValueError('Frozen run input exceeds 16 MiB; reduce interval/symbols.')
        with self.store.lock:
            current=self.store.get(pid)
            if current['busy'] or current['model_roles']!=project['model_roles'] or resolve_build(current,options.build_id)[0]['execution_hash']!=build['execution_hash']:
                raise ValueError('Project changed before start. Refresh and retry.')
            if cfg:self.connections.assert_generation(cfg)
            if len(self.list(pid))>=100:raise ValueError('Project has reached the 100-run storage limit.')
            # Run creation and busy flag share one SQLite transaction.
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE');current['busy']=True;current['updated']=now()
                db.execute('INSERT INTO project_runs VALUES(?,?,?)',(rid,pid,canonical(r)))
                db.execute('UPDATE projects SET document=? WHERE id=?',(canonical(current),pid))
        threading.Thread(target=self.execute,args=(pid,rid),daemon=True).start()
        return self.summary(r)

    def cancel(self,pid,rid):
        with self.store.lock:
            r=self.get(pid,rid)
            if r['status']=='running':r=self.update(pid,rid,cancel_requested=True)
        return self.summary(r)

    def execute(self,pid,rid):
        r=self.get(pid,rid)
        if r['status']!='running':return
        try:
            if r['cancel_requested']:self.update(pid,rid,status='cancelled');return
            frozen=r['frozen'];frozen_hash=frozen['run_hash']
            if digest({k:v for k,v in frozen.items() if k!='run_hash'})!=frozen_hash:raise ValueError('Frozen run hash changed.')
            from .execution_contract import Manifest, seal_build
            if seal_build(frozen['artifacts'],frozen['method'])!=frozen['build_hash']:raise ValueError('Frozen build changed.')
            data={s:[Bar.model_validate(b) for b in rows] for s,rows in r['market'].items()}
            if snapshot_id(data)!=frozen['market_hash']:raise ValueError('Frozen market data changed.')
            manifest=Manifest.model_validate(frozen['manifest'])
            cancelled=lambda:self.get(pid,rid)['cancel_requested']
            judge=None
            if frozen['model']:
                cfg=frozen['model'];current,key=self.connections.get(cfg['id'])
                if current!=cfg:raise ValueError('Execution connection changed; start a new explicitly authorized run.')
                judge=BoundedJudgment(self.store,self.connections,pid,rid,manifest,cfg,key,frozen['assumptions']['budget'],cancelled=cancelled)
            evaluator=self.evaluator_factory(self.store.path.parent/'project-runs'/pid/rid,frozen['artifacts'])
            result=simulate(data,manifest,evaluator,frozen['assumptions'],judge=judge,
                            compact_inputs=frozen['platform'].get('compact_inputs',False),
                            on_progress=lambda result:self.update(pid,rid,**result),cancelled=cancelled)
            self.update(pid,rid,**result)
        except Exception as exc:
            error=str(exc) if isinstance(exc,ValueError) and not hasattr(exc,'errors') else 'Historical execution failed; saved evidence retained. No automatic retry.'
            self.update(pid,rid,status='cancelled' if self.get(pid,rid)['cancel_requested'] else 'failed',error=error)
        finally:self.store.mutate(pid,lambda p:p.update(busy=False))
