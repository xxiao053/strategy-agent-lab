import hashlib
import json
import sqlite3
import uuid
import math
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def encoded(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def fingerprint(obj):
    return hashlib.sha256(encoded(obj).encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, created TEXT NOT NULL, config_json TEXT NOT NULL,
                    data_json TEXT NOT NULL, data_id TEXT NOT NULL, strategy_id TEXT NOT NULL,
                    state_json TEXT, status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', stop INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, node TEXT NOT NULL, request_hash TEXT NOT NULL,
                    status TEXT NOT NULL, raw_json TEXT, usage_json TEXT, elapsed REAL DEFAULT 0,
                    reserved REAL NOT NULL, note TEXT DEFAULT '');
                CREATE INDEX IF NOT EXISTS request_run ON requests(run_id);
                CREATE TABLE IF NOT EXISTS budgets (id TEXT PRIMARY KEY, cap REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS budget_carryover (
                    scope TEXT PRIMARY KEY, estimated_usd REAL NOT NULL,
                    committed_usd REAL NOT NULL, requests INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS presentation (name TEXT PRIMARY KEY, value_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS output_recoveries (
                    run_id TEXT NOT NULL, node TEXT NOT NULL, record_json TEXT NOT NULL,
                    PRIMARY KEY (run_id,node));
            ''')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(requests)')}
            if 'request_json' not in columns:
                db.execute('ALTER TABLE requests ADD COLUMN request_json TEXT')
            if 'source_request_id' not in columns:
                db.execute('ALTER TABLE requests ADD COLUMN source_request_id TEXT')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, config, data, data_id):
        rid = uuid.uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO runs(id,created,config_json,data_json,data_id,strategy_id,status) VALUES(?,?,?,?,?,?,?)',
                       (rid, datetime.now(timezone.utc).isoformat(), encoded(config), encoded(data), data_id, fingerprint(config['strategy']), 'ready'))
        return self.get(rid)

    def get(self, rid, include_data=False):
        with self.db() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (rid,)).fetchone()
        if row is None:
            raise KeyError(rid)
        r = dict(row)
        r['config'] = json.loads(r.pop('config_json'))
        r['archived']=(r['config']['strategy'].get('version')!='cup-v2'
                       or 'target_multiple' not in r['config']['strategy'])
        r['archive_replay']=r['archived'] and r['config']['mode']=='replay'
        r['state'] = json.loads(r.pop('state_json') or 'null')
        raw_data = r.pop('data_json')
        if include_data:
            r['data'] = json.loads(raw_data)
        r['provenance'] = {'baseline':'numeric baseline · no LLM judgments', 'live':'provider inference · not independently quality-verified',
                           'replay':'replay of saved judgments · no new inference'}[r['config']['mode']]
        if r['archive_replay']:r['provenance']='archived state copy · not recomputed by current engine · no inference'
        r['summary'] = self.summary(r)
        return r

    def list(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM runs ORDER BY created DESC')]
        return [{k:v for k,v in self.get(rid).items() if k != 'state'} for rid in ids]

    def checkpoint(self, rid, state):
        with self.db() as db:
            db.execute('UPDATE runs SET state_json=? WHERE id=?', (encoded(state), rid))

    def status(self, rid, status, reason=''):
        with self.db() as db:
            db.execute('UPDATE runs SET status=?,reason=? WHERE id=?', (status, reason, rid))

    def stop(self, rid, value=True):
        with self.db() as db:
            db.execute('UPDATE runs SET stop=? WHERE id=?', (int(value), rid))

    def stopped(self, rid):
        with self.db() as db:
            return bool(db.execute('SELECT stop FROM runs WHERE id=?', (rid,)).fetchone()[0])

    def requests(self, rid, node=None):
        with self.db() as db:
            rows = db.execute('SELECT * FROM requests WHERE run_id=?'+(' AND node=?' if node else '')+' ORDER BY id',
                              (rid,node) if node else (rid,)).fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r['raw'] = json.loads(r.pop('raw_json') or 'null')
            r['usage'] = json.loads(r.pop('usage_json') or '{}')
            r['request'] = json.loads(r.pop('request_json') or 'null')
            result.append(r)
        return result

    def has_stage_requests(self, rid, node):
        with self.db() as db:
            return db.execute('SELECT 1 FROM requests WHERE run_id=? AND node=? LIMIT 1', (rid,node)).fetchone() is not None

    def output_recovery(self, rid, node):
        with self.db() as db:
            row = db.execute('SELECT record_json FROM output_recoveries WHERE run_id=? AND node=?', (rid,node)).fetchone()
        return json.loads(row[0]) if row else None

    def authorize_output_recovery(self, rid, node):
        """Explicit operator action, not an automatic retry or unknown-billing waiver."""
        existing = self.output_recovery(rid,node)
        if existing:
            return existing  # Never reset an exhausted recovery stage.
        run = self.get(rid, True)
        if run['status'] != 'paused' or run['reason'] != 'Invalid/incomplete model decision after one repair; saved responses retained':
            raise ValueError('Only a paused incomplete-output stage can be explicitly recovered')
        if run['config']['mode'] != 'live' or not run['config']['paid_authorized']:
            raise ValueError('Recovery requires existing live authorization')
        with self.db() as db:
            last = db.execute('SELECT node FROM requests WHERE run_id=? ORDER BY rowid DESC LIMIT 1',(rid,)).fetchone()
        sources = self.requests(rid,node)
        dates = sorted({b['date'] for rows in run['data'].values() for b in rows if run['config']['start'] <= b['date'] <= run['config']['end']})
        day = (run['state'] or {}).get('day',0)
        if not last or last[0] != node or node.count(':') != 2 or node.split(':')[-1] not in {'primary','review'} or day >= len(dates) or node[:10] != dates[day]:
            raise ValueError('Recovery must identify the failed stage at the current checkpoint')
        if len(sources) < 2 or any(r['status'] not in {'complete','reused'} or not r['raw'] for r in sources):
            raise ValueError('Recovery cannot bypass unknown billing or missing receipts')
        record = dict(version='required-candidate-keys-v1', node=node, recovery_node=node+':recovery-v1',
                      max_requests=3, source_receipt_ids=[r['id'] for r in sources],
                      source_receipts_hash=fingerprint(sources), checkpoint_hash=fingerprint(run['state']),
                      checkpoint_day=day, strategy_id=run['strategy_id'], data_id=run['data_id'],
                      authorized_at=datetime.now(timezone.utc).isoformat())
        with self.db() as db:
            db.execute('INSERT INTO output_recoveries(run_id,node,record_json) VALUES(?,?,?)',(rid,node,encoded(record)))
        return record

    def begin_request(self, rid, node, key, request_hash, reserved, request):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            config = json.loads(db.execute('SELECT config_json FROM runs WHERE id=?',(rid,)).fetchone()[0])
            if config.get('budget_scope'):
                budget = self._budget_status(db,config['budget_scope'])
                if budget['committed_usd']+reserved > budget['cap_usd']:
                    raise ValueError('Shared spending authorization exhausted before dispatch')
            db.execute('INSERT INTO requests(id,run_id,node,request_hash,status,reserved,request_json) VALUES(?,?,?,?,?,?,?)',
                       (key, rid, node, request_hash, 'sent', reserved, encoded(request)))

    def authorize_budget(self, scope, cap):
        if not math.isfinite(cap) or cap <= 0:
            raise ValueError('Budget cap must be finite and positive')
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO budgets(id,cap) VALUES(?,?)',(scope,cap))
            if db.execute('SELECT cap FROM budgets WHERE id=?',(scope,)).fetchone()[0] != cap:
                raise ValueError('An existing spending authorization cannot be increased or changed')

    def reuse_response(self,rid,node,key,request_hash,request,source):
        if source['status'] not in {'complete','reused'} or source['request_hash']!=request_hash or not source['raw']:
            raise ValueError('Only an exact saved response can be reused')
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO requests(id,run_id,node,request_hash,status,reserved,request_json,raw_json,usage_json,source_request_id) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (key,rid,node,request_hash,'reused',0,encoded(request),encoded(source['raw']),encoded(source['usage']),source.get('source_request_id') or source['id']))

    def _budget_status(self, db, scope):
        budget = db.execute('SELECT cap FROM budgets WHERE id=?',(scope,)).fetchone()
        if budget is None:
            raise ValueError('Shared budget scope has no explicit authorization')
        rows = db.execute('SELECT q.*,r.config_json FROM requests q JOIN runs r ON q.run_id=r.id WHERE json_extract(r.config_json,\'$.budget_scope\')=?',(scope,)).fetchall()
        carried = db.execute('SELECT * FROM budget_carryover WHERE scope=?',(scope,)).fetchone()
        measured = carried['estimated_usd'] if carried else 0
        committed = carried['committed_usd'] if carried else 0
        request_count = carried['requests'] if carried else 0
        for row in rows:
            if row['status']=='reused':continue
            cfg=json.loads(row['config_json']);u=json.loads(row['usage_json'] or '{}')
            if u.get('accounting_version')==2:
                measured+=u.get('usage_cost') or 0
                committed+=u['committed_cost']
                continue
            estimate=(u.get('input',0)*cfg['input_rate']+u.get('output',0)*cfg['output_rate'])/1e6
            measured+=estimate
            # Retain pre-v2 ledger values; this branch never prices new receipts.
            if row['status']!='complete' or u.get('reported') is False:
                committed+=row['reserved']
            elif cfg['provider']=='openai':
                committed+=(u.get('input',0)*cfg['input_rate']*2.75+u.get('output',0)*cfg['output_rate']*1.1)/1e6
            else:
                committed+=estimate*1.25
        return dict(id=scope,cap_usd=budget[0],committed_usd=committed,estimated_usd=measured,requests=request_count+sum(row['status']!='reused' for row in rows))

    def budget_status(self,scope):
        with self.db() as db:
            return self._budget_status(db,scope)

    def model_status(self):
        with self.db() as db:
            rows=db.execute("SELECT r.config_json,q.raw_json FROM requests q JOIN runs r ON q.run_id=r.id WHERE q.status='complete' AND q.raw_json IS NOT NULL").fetchall()
        result={}
        for row in rows:
            cfg=json.loads(row['config_json']);raw=json.loads(row['raw_json'])
            if not raw.get('id') or raw.get('model')!=cfg['model']:
                continue
            item=result.setdefault(cfg['provider'],{'models':[],'requests':0})
            if cfg['model'] not in item['models']:item['models'].append(cfg['model'])
            item['requests']+=1
        return result

    def set_showcase(self,report):
        run=self.get(report['run_id'])
        if run['status']!='completed' or run['config']['mode']!='live' or not run['summary']['requests'] or run['summary']['unresolved_reserve']:
            raise ValueError('Showcase must be a completed real model run')
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO presentation(name,value_json) VALUES('showcase',?)",(encoded({'run_id':run['id']}),))

    def showcase(self):
        with self.db() as db:
            row=db.execute("SELECT value_json FROM presentation WHERE name='showcase'").fetchone()
        if not row:return None
        report=json.loads(row[0]);run=self.get(report['run_id'])
        return dict(run_id=run['id'],summary=run['summary'],config=run['config'],data_id=run['data_id'],strategy_id=run['strategy_id'])

    def delete_runs(self, ids):
        """Delete explicit records, retaining spend without retaining their content."""
        ids = set(ids)
        if not ids:return 0
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT id,status,config_json FROM runs').fetchall()
            targets = [r for r in rows if r['id'] in ids]
            selected = db.execute("SELECT value_json FROM presentation WHERE name='showcase'").fetchone()
            if selected and json.loads(selected[0])['run_id'] in ids:
                raise ValueError('Cannot delete the selected showcase')
            if any(r['status']=='running' for r in targets):
                raise ValueError('Cannot delete a running research job')
            if any(r['id'] not in ids and any(json.loads(r['config_json']).get(key) in ids
                   for key in ('replay_of','reuse_responses_from')) for r in rows):
                raise ValueError('A retained replay or response-reuse source references this research record')
            if any(r['run_id'] in ids for r in db.execute("SELECT run_id FROM requests WHERE status IN ('sent','unknown')")):
                raise ValueError('Resolve unsettled requests before deleting research')
            # Retained reused receipts still need their original source for traceability.
            request_owners = {r['id']:r['run_id'] for r in db.execute('SELECT id,run_id FROM requests')}
            if any(r['run_id'] not in ids and request_owners.get(r['source_request_id']) in ids
                   for r in db.execute('SELECT run_id,source_request_id FROM requests WHERE source_request_id IS NOT NULL')):
                raise ValueError('A retained request references this research record')
            scopes = [r['id'] for r in db.execute('SELECT id FROM budgets')]
            before = {scope:self._budget_status(db,scope) for scope in scopes}
            for row in targets:
                for table in ('requests','output_recoveries'):
                    db.execute(f'DELETE FROM {table} WHERE run_id=?',(row['id'],))
                db.execute('DELETE FROM runs WHERE id=?',(row['id'],))
            for scope in scopes:
                after = self._budget_status(db,scope)
                delta = tuple(before[scope][k]-after[k] for k in ('estimated_usd','committed_usd','requests'))
                db.execute('INSERT INTO budget_carryover VALUES(?,?,?,?) ON CONFLICT(scope) DO UPDATE SET '
                           'estimated_usd=estimated_usd+excluded.estimated_usd, '
                           'committed_usd=committed_usd+excluded.committed_usd, requests=requests+excluded.requests',
                           (scope,*delta))
            return len(targets)

    def save_response(self, key, raw, usage, elapsed):
        with self.db() as db:
            db.execute("UPDATE requests SET raw_json=?,usage_json=?,elapsed=?,status='complete' WHERE id=?",
                       (encoded(raw), encoded(usage), elapsed, key))

    def request_status(self, key, status, note=''):
        with self.db() as db:
            db.execute('UPDATE requests SET status=?,note=? WHERE id=?', (status, note, key))

    def acknowledge(self, rid):
        # The user explicitly accepts possible double billing. Never pretend exactly-once provider inference.
        with self.db() as db:
            db.execute("UPDATE requests SET status='acknowledged',note='User accepted unknown outcome and possible duplicate billing' WHERE run_id=? AND status IN ('sent','unknown')", (rid,))

    def summary(self, run):
        account = (run['state'] or {}).get('account') or {}
        curve = account.get('curve', [])
        initial = run['config']['capital']
        equity = curve[-1]['equity'] if curve else initial
        peak, drawdown = initial, 0
        for point in curve:
            peak = max(peak, point['equity'])
            drawdown = min(drawdown, point['equity']/peak-1)
        all_responses = self.requests(run['id'])
        requests = [r for r in all_responses if r['status']!='reused']
        cfg = run['config']
        cost = sum((r['usage'].get('usage_cost') or 0) if r['usage'].get('accounting_version')==2 else
                   (r['usage'].get('input', 0)*cfg['input_rate'] + r['usage'].get('output', 0)*cfg['output_rate'])/1e6 for r in requests)
        unknown_reserve = sum(r['reserved'] for r in requests if r['status'] != 'complete' or r['usage'].get('reported') is False or
                              (r['usage'].get('accounting_version')==2 and r['usage'].get('cost_status')!='usage_priced'))
        trades = account.get('trades', [])
        exposures=[(p['equity']-p['cash'])/p['equity'] if p['equity'] else 0 for p in curve]
        orders=account.get('orders',[])
        return dict(equity=equity, total_return=equity/initial-1, max_drawdown=drawdown, trades=len(trades),
                    buy_fills=sum(o['side']=='buy' and o['status']=='filled' for o in orders),
                    sell_fills=sum(o['side']=='sell' and o['status']=='filled' for o in orders),
                    active_sessions=sum(p.get('positions',0)>0 for p in curve),
                    mean_exposure=sum(exposures)/len(exposures) if exposures else 0,
                    current_exposure=exposures[-1] if exposures else 0,
                    realized_pnl=round(sum(t['pnl'] for t in trades),2),
                    unrealized_pnl=round(sum(p['quantity']*p['last_close']-p['cost'] for p in account.get('positions', {}).values()),2),
                    requests=len(requests), reused_responses=len(all_responses)-len(requests), estimated_cost=cost, unresolved_reserve=unknown_reserve,
                    elapsed_model_seconds=sum(r['elapsed'] for r in requests),
                    fees=round(sum(o.get('fee',0) for o in account.get('orders',[])),2))
