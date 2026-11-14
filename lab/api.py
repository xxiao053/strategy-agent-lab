import os
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from .contracts import RunConfig
from .providers import PROVIDERS
from .store import Store
from .runner import Runner
from .prompts import make_context, chart_png
from .contracts import Bar
from .strategy import diagnose_anchors
from .references import reference_pack
from .universe import UNIVERSE
from .workspace_api import workspace_router


def create_app(root=None, db_path=None):
    root = Path(root or Path(__file__).resolve().parents[1])
    load_dotenv(root/'.env', override=False)
    data_root=Path(os.environ.get('LAB_DATA_ROOT',str(root))).resolve()
    store = Store(db_path or data_root/'runs/lab.sqlite3')
    runner = Runner(data_root, store)
    app = FastAPI(title='Strategy Agent Lab', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runner, app.state.store = runner, store
    workspace_db = Path(db_path).parent/'workspace.sqlite3' if db_path else data_root/'runs/workspace.sqlite3'
    workspace=workspace_router(root, workspace_db,data_root=data_root)
    app.include_router(workspace)

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        host = request.url.hostname
        if host not in {'127.0.0.1', 'localhost', '::1'}:
            return JSONResponse({'detail':'Localhost only'}, status_code=400)
        origin = request.headers.get('origin')
        if origin and (urlparse(origin).hostname != host or urlparse(origin).scheme != request.url.scheme or urlparse(origin).port != request.url.port):
            return JSONResponse({'detail':'Cross-origin access denied'}, status_code=403)
        if '/images/' in request.url.path and request.headers.get('sec-fetch-site') in {'cross-site','same-site'}:
            return JSONResponse({'detail':'Same-origin image access required'},status_code=403)
        if request.method not in {'GET', 'HEAD'} and request.headers.get('x-lab-request') != '1':
            return JSONResponse({'detail':'Local request header required'}, status_code=403)
        limit=100000
        upload=re.fullmatch(r'/api/workspace/projects/([a-f0-9]{32})/materials',request.url.path)
        if upload and request.method=='POST':
            try:workspace.materials.store.get(upload[1])
            except KeyError:return JSONResponse({'detail':'Record not found'},status_code=404)
            from .materials import upload_limit,validate_upload_header
            from urllib.parse import unquote
            name=unquote(request.headers.get('x-material-name',''))
            try:extension=validate_upload_header(name,request.headers.get('content-type',''))
            except ValueError as exc:return JSONResponse({'detail':str(exc)},status_code=400)
            limit=upload_limit(extension)
        try:size=int(request.headers.get('content-length','0'))
        except ValueError:return JSONResponse({'detail':'Invalid request length'},status_code=400)
        if size<0 or request.headers.get('content-encoding'):
            return JSONResponse({'detail':'Unsupported request encoding or length'},status_code=400)
        if size > limit:
            return JSONResponse({'detail':'Request too large'}, status_code=413)
        # Bound actual bytes as well as declarations, including chunked requests.
        content=bytearray()
        async for chunk in request.stream():
            if len(content)+len(chunk)>limit:return JSONResponse({'detail':'Request too large'},status_code=413)
            content.extend(chunk)
        request._body=bytes(content)
        response = await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cross-Origin-Resource-Policy']='same-origin'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail':'Record not found'}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail':str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def invalid_shape(request, exc):
        # FastAPI's default includes submitted values, including credentials.
        return JSONResponse({'detail':'Invalid request format. Submitted values are not echoed.'},status_code=422)

    @app.get('/api/bootstrap')
    def bootstrap():
        observed=store.model_status()
        demo=store.showcase()
        defaults=dict(demo['config'],approved=False,paid_authorized=False,budget_scope=None,replay_of=None,mode='baseline') if demo else RunConfig().model_dump()
        return dict(defaults=defaults, universe=[dict(symbol=s,**info) for s,info in UNIVERSE.items()],providers=[dict(id=k, label=p['label'], env=p['env'],
                    configured=bool(os.getenv(p['env'])), images=p['images'], protocol=p['protocol'],
                    observed_models=observed.get(k,{}).get('models',[]),
                    verification='observed provider responses; quality not implied' if k in observed else 'offline contract tests only; no live request verified') for k,p in PROVIDERS.items()],
                    runs=store.list(), showcase=demo, references=reference_pack(), local_only=True)

    @app.get('/api/showcase')
    def showcase():
        return store.showcase()

    @app.post('/api/preflight')
    def preflight(config: RunConfig):
        return runner.preflight(config)

    @app.post('/api/runs')
    def create(config: RunConfig):
        run = runner.create(config)
        runner.launch(run['id'])
        return run

    @app.get('/api/runs')
    def runs():
        return store.list()

    @app.get('/api/runs/{rid}')
    def get_run(rid: str):
        return store.get(rid)

    @app.post('/api/runs/{rid}/pause')
    def pause(rid: str):
        store.get(rid)
        store.stop(rid)
        return {'ok':True}

    @app.post('/api/runs/{rid}/resume')
    def resume(rid: str):
        if store.get(rid)['archived']:
            raise ValueError('Archived engine/configuration; create a new v2 research run')
        runner.launch(rid)
        return {'ok':True}

    @app.post('/api/runs/{rid}/acknowledge-unknown')
    def acknowledge(rid: str):
        store.get(rid)
        store.acknowledge(rid)
        return {'ok':True}

    @app.post('/api/runs/{rid}/replay')
    def replay(rid: str):
        run = runner.replay(rid)
        runner.launch(run['id'])
        return run

    @app.get('/api/runs/{rid}/requests')
    def requests(rid: str):
        run=store.get(rid)
        source=run['config'].get('replay_of') if run['config']['mode']=='replay' else rid
        return [dict(r,source_run_id=source) for r in store.requests(source)]

    def visible_context(rid, symbol, day):
        run = store.get(rid, True)
        if symbol not in run['data']:
            raise KeyError(symbol)
        if not run['config']['start'] <= day <= run['config']['end']:
            raise ValueError('Date outside run')
        series = [Bar.model_validate(b) for b in run['data'][symbol]]
        try:
            i = [b.date for b in series].index(day)
        except ValueError:
            raise ValueError('Not a trading date') from None
        return run, series, i

    @app.get('/api/runs/{rid}/context/{symbol}/{day}')
    def context(rid: str, symbol: str, day: str):
        run, bars, i = visible_context(rid, symbol, day)
        event=next((d for d in (run['state'] or {}).get('decisions',[]) if d['id']==f'{day}:{symbol}'),{})
        candidates=event.get('candidates',[])
        window=run['config']['strategy'].get('history_window',160)
        source=run['config'].get('replay_of') if run['config']['mode']=='replay' else rid
        receipts=[q for q in store.requests(source) if q['node'] in {f'{day}:{symbol}',f'{day}:{symbol}:primary'}]
        receipt=next((q for q in receipts if q.get('request')),None)
        ctx={'system':'','text':''}
        if receipt:
            body=receipt['request'].get('body',{})
            # Show saved input, never retrospectively claim a new prompt was the original.
            if run['config']['provider']=='openai':
                ctx={'system':body.get('instructions',''), 'text':'\n'.join(
                    c.get('text','') for item in body.get('input',[]) if item.get('role')=='user'
                    for c in item.get('content',[]) if isinstance(c,dict) and c.get('type')=='input_text')}
            else:
                ctx={'system':'Saved provider request; inspect receipts for native structure.', 'text':json.dumps(body,ensure_ascii=False)}
        elif not run['archived'] and candidates:
            cfg=RunConfig.model_validate(run['config']).model_copy(update={'use_images':False})
            ctx=make_context(symbol,bars,i,cfg,candidates=candidates)
        elif run['archived']:
            ctx['text']='Archived record without a saved request for this date. No current-engine prompt reconstructed.'
        pattern=event.get('validation',{}).get('pattern') or (candidates[0] if candidates else {})
        return dict(system=ctx['system'],text=ctx['text'],original_request=bool(receipt),archived=run['archived'],
                    bars=[b.model_dump() for b in bars[max(0,i-window+1):i+1]],candidates=candidates,
                    numeric_checks=pattern.get('numeric_checks',[]),references=reference_pack(),
                    primary_evaluations=event.get('primary_evaluations',[]),review_evaluations=event.get('review_evaluations',[]),
                    evaluations=event.get('evaluations',[]))

    @app.get('/api/runs/{rid}/chart/{symbol}/{day}')
    def chart(rid: str, symbol: str, day: str, candidate_id: str | None=None):
        run, bars, i = visible_context(rid, symbol, day)
        pattern=None
        if candidate_id:
            event=next((d for d in (run['state'] or {}).get('decisions',[]) if d['id']==f'{day}:{symbol}'),{})
            pattern=next((c for c in event.get('candidates',[]) if c['candidate_id']==candidate_id),None)
            if pattern is None:raise ValueError('Candidate not offered for this run/symbol/date')
        window=run['config']['strategy'].get('history_window',160)
        return Response(chart_png(symbol,bars[max(0,i-window+1):i+1],pattern), media_type='image/png')

    assets = root/'web/dist/assets'
    if assets.exists():
        app.mount('/assets', StaticFiles(directory=assets), name='assets')

    @app.get('/')
    def index():
        path = root/'web/dist/index.html'
        if not path.exists():
            return JSONResponse({'detail':'Build frontend first with start.ps1'}, status_code=503)
        return FileResponse(path)

    return app
