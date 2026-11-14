"""User-selected connections. Secrets never appear in public connection documents."""
import base64
import ctypes
import json
import math
import os
import re
import time
import uuid
import httpx
from .providers import PROVIDERS, ProviderError, endpoint
from .provider_io import chunks as bounded_chunks


def protect(value, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Persistent credentials require Windows DPAPI on this release.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    data=base64.b64decode(value) if decrypt else value.encode()
    buf=ctypes.create_string_buffer(data)
    src=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)))
    dst=Blob()
    # UI_FORBIDDEN: no hidden system dialog; fails closed on failure.
    fn=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(src),None,None,None,None,1,ctypes.byref(dst)):
        raise ValueError('Local credential protection unavailable.')
    try:
        out=ctypes.string_at(dst.data,dst.size)
        return out.decode() if decrypt else base64.b64encode(out).decode()
    finally:
        ctypes.windll.kernel32.LocalFree(dst.data)


class Connections:
    def __init__(self, store):
        self.store=store
        self.session={}
        self.active_checks={}

    def list(self):
        with self.store.connect() as db:
            rows=db.execute('SELECT id,document,secret FROM connections').fetchall()
        return [dict(json.loads(d),configured=bool(self._key(i,s))) for i,d,s in rows]

    def _key(self,cid,secret):
        try:return protect(secret,True) if secret else self.session.get(cid)
        except (RuntimeError,ValueError,OSError):return None

    @staticmethod
    def capability():
        persistent=False
        if os.name=='nt':
            try:persistent=protect(protect('non-secret-storage-probe'),True)=='non-secret-storage-probe'
            except (ValueError,RuntimeError,OSError):pass
        return dict(persistent=persistent,storage='windows-dpapi' if persistent else 'session-only')

    def get(self,cid):
        if not isinstance(cid,str):raise ValueError('Select a configured model connection.')
        with self.store.connect() as db:
            row=db.execute('SELECT document,secret FROM connections WHERE id=?',(cid,)).fetchone()
        if not row: raise ValueError('Select a configured model connection.')
        config=json.loads(row[0])
        config.setdefault('generation',1)
        key=self._key(cid,row[1])
        if not key: raise ValueError('Re-enter the API key for this connection.')
        return config,key

    def assert_generation(self,cfg):
        current,key=self.get(cfg['id'])
        if current.get('generation',1)!=cfg.get('generation',1):
            raise ValueError('Connection credentials were renewed. Refresh and authorize again.')
        return current,key

    def _assert_idle(self,db,cid):
        if self.active_checks.get(cid):
            raise ValueError('Connection has an active catalog check. Wait before changing it.')
        for row in db.execute('SELECT document FROM projects'):
            p=json.loads(row[0])
            if p.get('busy') and (cid in (p.get('model_roles') or {}).values() or
                any(r.get('connection_id')==cid and r.get('status')=='running' for r in p.get('records',[])+p.get('builds',[]))):
                raise ValueError('Connection is in use by an active project. Wait before changing it.')

    def renew(self,cid,body):
        if set(body)-{'key','remember','use_environment'}:raise ValueError('Only credential fields may be renewed.')
        with self.store.lock,self.store.connect() as db:
            self._assert_idle(db,cid)
            row=db.execute('SELECT document FROM connections WHERE id=?',(cid,)).fetchone()
            if not row:raise ValueError('Select a saved connection.')
            cfg=json.loads(row[0]);_,key=self.credentials(dict(body,provider=cfg['provider']))
            persistent=body.get('remember') is True
            if persistent and not self.capability()['persistent']:raise ValueError('Persistent credentials unavailable. Use session-only storage.')
            secret=protect(key) if persistent else None
            for field in ('catalog_status','selected_listed','construction'):cfg.pop(field,None)
            cfg['image_observation']='not_observed'
            cfg.update(generation=cfg.get('generation',1)+1,verification='not_tested',storage='os-protected' if persistent else 'session')
            db.execute('UPDATE connections SET document=?,secret=? WHERE id=?',(json.dumps(cfg),secret,cid))
            self.session.pop(cid,None)
            if not persistent:self.session[cid]=key
        return dict(cfg,configured=True)

    def configure_images(self,cid,body):
        from .image_policy import TOKEN_ADAPTERS
        if set(body)!={'enabled','billing_profile'} or type(body['enabled']) is not bool:
            raise ValueError('Set the selected model image input policy explicitly.')
        enabled=body['enabled']
        if body['billing_profile']!=('token-v1' if enabled else None):
            raise ValueError('Only explicitly confirmed token-v1 image billing is supported.')
        with self.store.lock,self.store.connect() as db:
            self._assert_idle(db,cid)
            row=db.execute('SELECT document FROM connections WHERE id=?',(cid,)).fetchone()
            if not row:raise ValueError('Select a saved connection.')
            cfg=json.loads(row[0])
            if enabled and cfg['provider'] not in TOKEN_ADAPTERS:
                raise ValueError('This adapter has no supported image billing profile; choose OpenAI, Anthropic or Gemini token billing.')
            cfg.update(image_inputs=enabled,image_billing_profile=body['billing_profile'],image_observation='not_observed',generation=cfg.get('generation',1)+1)
            db.execute('UPDATE connections SET document=? WHERE id=?',(json.dumps(cfg),cid))
        return dict(cfg,configured=any(c['id']==cid and c['configured'] for c in self.list()))

    def vision_observed(self,cid,*,generation):
        self._observed(cid,generation=generation,image_observation='image_response_observed')

    @staticmethod
    def credentials(body):
        provider=body.get('provider')
        if not isinstance(provider,str) or provider not in PROVIDERS:
            raise ValueError('Choose a supported provider.')
        key=body.get('key','')
        if body.get('use_environment') is True:
            key=os.getenv(PROVIDERS[provider]['env'],'')
        if not isinstance(key,str) or not 8<=len(key.strip())<=4096:
            raise ValueError('API key is missing or invalid. Nothing was sent.')
        key=key.strip()
        if any(ord(c)<32 for c in key):raise ValueError('Invalid API key.')
        return provider,key

    def assign_roles(self,pid,body):
        if set(body)!={'builder','execution'} or any(v is not None and (not isinstance(v,str) or not v) for v in body.values()):
            raise ValueError('Set builder and execution to saved connection IDs or null.')
        with self.store.lock:
            def assign(p):
                if p['busy']:raise ValueError('Project already has an active task. Wait before changing model roles.')
                for cid in body.values():
                    if cid is not None:self.get(cid)
                p['model_roles']=dict(body)
            return self.store.mutate(pid,assign)

    def builder(self,project,body):
        bound=project['model_roles']['builder']
        requested=body.get('connection_id')
        if bound is not None and requested is not None and requested!=bound:
            raise ValueError('Request cannot override the project builder model. Update project model roles first.')
        # Legacy direct requests remain supported only for explicitly unset roles.
        return self.get(bound if bound is not None else requested)

    def create(self, body):
        provider=body.get('provider')
        if not all(isinstance(body.get(k,''),str) for k in ('provider','model','name')):
            raise ValueError('Choose a provider, connection name and supported model ID.')
        model=body.get('model','').strip()
        name=body.get('name','').strip()
        if provider not in PROVIDERS or not 1<=len(name)<=80 or not re.fullmatch(r'[\w./:\-]{1,100}',model):
            raise ValueError('Choose a provider, connection name and supported model ID.')
        prices={}
        for key in ['input_price','output_price']:
            try: value=float(body.get(key,0))
            except (ValueError,TypeError): raise ValueError('Enter current USD prices per million tokens.') from None
            if not math.isfinite(value) or not 0 < value <= 10000:
                raise ValueError('Enter positive USD prices per million tokens.')
            prices[key]=value
        for key in ('cached_input_price','cache_write_price'):
            supplied=body.get(key)
            if supplied in (None,''):continue
            try:value=float(supplied)
            except (ValueError,TypeError):raise ValueError('Enter valid cache token prices.') from None
            if isinstance(supplied,bool) or not math.isfinite(value) or not 0<=value<=10000:
                raise ValueError('Enter cache token prices from $0 to $10,000 per million tokens.')
            prices[key]=value
        _,key=self.credentials(body)
        if key in name or key in model:raise ValueError('Keep credentials out of connection names and model IDs.')
        cid=uuid.uuid4().hex
        persistent=body.get('remember',False) is True
        if persistent and not self.capability()['persistent']:raise ValueError('Persistent credentials unavailable. Use session-only storage.')
        effort=body.get('reasoning_effort','')
        if effort not in {'','none','minimal','low','medium','high','xhigh'}:
            raise ValueError('Unsupported reasoning setting.')
        secret=protect(key) if persistent else None
        cfg=dict(id=cid,name=name,provider=provider,model=model,reasoning_effort=effort,**prices,
                 storage='os-protected' if persistent else 'session',verification='not_tested',generation=1)
        with self.store.connect() as db:
            db.execute('INSERT INTO connections VALUES(?,?,?)',(cid,json.dumps(cfg),secret))
        if not persistent: self.session[cid]=key
        return dict(cfg,configured=True)

    def delete(self,cid):
        with self.store.lock, self.store.connect() as db:
            for row in db.execute('SELECT document FROM projects'):
                p=json.loads(row[0])
                if p.get('busy') and (cid in (p.get('model_roles') or {}).values() or
                    any(r.get('connection_id')==cid and r.get('status')=='running' for r in p.get('records',[])+p.get('builds',[]))):
                    raise ValueError('Connection is in use by an active project. Wait before removing it.')
            db.execute('DELETE FROM connections WHERE id=?',(cid,))
            self.session.pop(cid,None)

    def check(self,cid):
        cfg,key=self.get(cid)
        with self.store.lock:
            self.assert_generation(cfg)
            self.active_checks[cid]=self.active_checks.get(cid,0)+1
        try:
            result=self._catalog(cfg['provider'],key)
            listed=cfg['model'] in result['models']
            with self.store.lock:
                self.assert_generation(cfg)
                self._observed(cid,catalog_status='catalog_available',selected_listed=listed)
            return dict(result,selected_listed=listed)
        finally:
            with self.store.lock:
                self.active_checks[cid]-=1
                if not self.active_checks[cid]:del self.active_checks[cid]

    def catalog(self,body):
        return self._catalog(*self.credentials(body))

    @staticmethod
    def _catalog(provider,key):
        headers={'Authorization':'Bearer '+key}
        if provider=='anthropic': headers={'x-api-key':key,'anthropic-version':'2023-06-01'}
        if provider=='gemini': headers={'x-goog-api-key':key}
        headers['Accept-Encoding']='identity'
        deadline=time.monotonic()+30
        try:
            with httpx.Client(timeout=20,follow_redirects=False) as client:
                with client.stream('GET',endpoint(provider)+'/models',headers=headers) as response:
                    if response.status_code>=300:
                        raise ValueError(f'Model catalog HTTP {response.status_code}. No inference requested; enter a model ID manually.')
                    raw=bytearray()
                    for chunk in bounded_chunks(response,limit=1000000,deadline=deadline):raw.extend(chunk)
            data=json.loads(raw)
            rows=data.get('models',[]) if provider=='gemini' else data.get('data',[])
            if not isinstance(rows,list) or len(rows)>10000:raise ValueError('Invalid catalog shape.')
            models=sorted({r.get('id',r.get('name','')).removeprefix('models/') for r in rows
                           if isinstance(r,dict) and isinstance(r.get('id',r.get('name')),str)
                           and re.fullmatch(r'[\w./:\-]{1,100}',r.get('id',r.get('name','')).removeprefix('models/'))
                           and key not in r.get('id',r.get('name',''))})[:2000]
            return dict(models=models,status='catalog_available')
        except (httpx.HTTPError,httpx.InvalidURL,ProviderError,ValueError,TypeError,AttributeError):
            raise ValueError('Model catalog unavailable. No inference requested; enter a model ID manually.') from None

    def _observed(self,cid,*,generation=None,**changes):
        with self.store.lock,self.store.connect() as db:
            row=db.execute('SELECT document FROM connections WHERE id=?',(cid,)).fetchone()
            if row:
                cfg=json.loads(row[0])
                if generation is not None and cfg.get('generation',1)!=generation:return
                cfg.update(changes)
                db.execute('UPDATE connections SET document=? WHERE id=?',(json.dumps(cfg),cid))

    def verified(self,cid,*,generation=None):
        self._observed(cid,generation=generation,verification='structured_response_observed')

    def construction_observed(self,cid,*,generation=None):
        self._observed(cid,generation=generation,construction='code_construction_observed')
