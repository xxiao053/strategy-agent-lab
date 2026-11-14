"""Local project records, independent of frozen execution research."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def model_roles(project):
    """Legacy documents have explicit unset roles; never infer from other projects."""
    roles=project.get('model_roles') or {}
    return {role:roles.get(role) if isinstance(roles.get(role),str) else None
            for role in ('builder','execution')}


class WorkspaceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, document TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY, document TEXT NOT NULL, secret TEXT);
            ''')
            # Interrupted requests are not silently restarted or refunded.
            for row in db.execute('SELECT id,document FROM projects').fetchall():
                p = json.loads(row[1])
                if p.get('busy'):
                    p['busy'] = False
                    if p.get('data_preparation',{}).get('status')=='running':
                        p['data_preparation'].update(status='interrupted',error='Server restarted; saved snapshots retained. Prepare data again to continue.')
                    for b in p.get('builds',[]):
                        if b['status']=='running':b.update(status='interrupted',error='Server restarted. Saved artifacts and request records are retained; no automatic restart.')
                    for r in p['records']:
                        if r['status'] == 'running':
                            r.update(status='unknown', error='Interrupted; request may have been billed. No automatic retry.')
                    db.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(p), p['id']))

    def connect(self):
        return sqlite3.connect(self.path, timeout=20)

    def list(self):
        with self.connect() as db:
            rows = [json.loads(r[0]) for r in db.execute('SELECT document FROM projects')]
        return [self.summary(p) for p in sorted(rows, key=lambda p:p['updated'], reverse=True)]

    @staticmethod
    def summary(p):
        return dict({k:p[k] for k in ['id','title','locale','updated','revision','busy']},model_roles=model_roles(p))

    def get(self, pid):
        with self.connect() as db:
            row = db.execute('SELECT document FROM projects WHERE id=?',(pid,)).fetchone()
        if row is None:
            raise KeyError(pid)
        p=json.loads(row[0]);p['model_roles']=model_roles(p)
        return p

    def create(self, title, locale, *, initial=None):
        welcome = ('你好，我会帮你把投资方法整理成可以运行、检查和修改的项目。你可以先讲一次具体的买卖，也可以贴一段笔记，不用一次说完整。我们会逐步明确关注的市场、决策依据、退出和仓位。还没想好的地方先留作问题。\n\n先说说你最想实现的那部分吧。' if locale == 'zh-CN' else
                   'Hello. I’ll help turn your investment method into a project you can run, inspect and revise. Start with a concrete trade example or a note; you don’t need a complete specification. We’ll clarify the market, decisions, exits and sizing as we go. Anything undecided can remain an open question.\n\nWhat would you like to build first?')
        p = dict(id=uuid.uuid4().hex, title=title, locale=locale, updated=now(), revision=0,
                 messages=[dict(id=uuid.uuid4().hex,role='assistant',text=welcome,kind='welcome',created=now())],
                 draft=None, versions=[], records=[], busy=False,model_roles={'builder':None,'execution':None})
        if initial:
            if set(initial)-{'revision','draft','materials','example_sources','starter_files','example_origin'}:
                raise ValueError('Invalid initial project fields.')
            p.update(initial)
        with self.connect() as db:
            db.execute('INSERT INTO projects VALUES(?,?)',(p['id'],json.dumps(p)))
        return p

    def mutate(self, pid, fn):
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT document FROM projects WHERE id=?',(pid,)).fetchone()
            if row is None: raise KeyError(pid)
            p=json.loads(row[0])
            p['model_roles']=model_roles(p)
            fn(p)
            p['updated']=now()
            db.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(p),pid))
        return p

    def approve(self, pid, revision):
        def apply(p):
            if p['busy'] or p['revision'] != revision:
                raise ValueError('Project changed. Refresh before approving.')
            if not p['draft'] or not p['draft']['rules']:
                raise ValueError('No method draft to approve.')
            if any(q['blocking'] for q in p['draft']['questions']):
                raise ValueError('Resolve the execution-critical questions before approval.')
            if any('material_refs' in rule for rule in p['draft']['rules']):
                from .material_citations import validate_material_citations
                validate_material_citations(p['draft']['rules'],p['draft'].get('material_sources',[]))
            if p['versions'] and p['versions'][-1]['revision'] == revision:
                raise ValueError('This revision is already approved.')
            p['versions'].append(dict(version=len(p['versions'])+1,revision=revision,
                                      method=p['draft'],created=now()))
        return self.mutate(pid,apply)
