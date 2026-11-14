import json
from fastapi import APIRouter,Request
from .connections import Connections
from .providers import PROVIDERS
from .workspace_agent import WorkspaceAgent
from .workspace_store import WorkspaceStore
from .build_runtime import Builder
from .project_runs import ProjectRuns


def workspace_router(root,db_path,*,data_root=None):
    store=WorkspaceStore(db_path)
    connections=Connections(store)
    agent=WorkspaceAgent(store,connections,data_root=data_root or root)
    builder=Builder(store,connections)
    runs=ProjectRuns(data_root or root,store,connections)
    from .data_preparation import DataPreparation
    preparation=DataPreparation(data_root or root,store)
    router=APIRouter(prefix='/api/workspace')
    from .materials import Materials
    materials=Materials(data_root or root,store)
    router.materials=materials

    @router.get('/projects/{pid}/materials')
    def material_list(pid:str):return materials.list(pid)

    @router.get('/projects/{pid}/materials/{mid}')
    def material_content(pid:str,mid:str):return materials.get(pid,mid)

    @router.get('/projects/{pid}/materials/{mid}/images/{sha256}')
    def material_image(pid:str,mid:str,sha256:str):
        from fastapi.responses import Response
        return Response(materials.image(pid,mid,sha256),media_type='image/png',headers={'ETag':'"'+sha256+'"','X-Content-Type-Options':'nosniff'})

    @router.post('/projects/{pid}/materials')
    async def material_upload(pid:str,request:Request):
        from urllib.parse import unquote
        from starlette.concurrency import run_in_threadpool
        raw=await request.body()
        return await run_in_threadpool(materials.upload,pid,unquote(request.headers.get('x-material-name','')),request.headers.get('content-type',''),raw)

    @router.get('/projects')
    def projects(): return store.list()

    @router.post('/examples/{example_id}/copy')
    def copy_example(example_id:str,body:dict):
        from .example_copy import ExampleCopies
        return ExampleCopies(root,store).create(example_id,body)

    @router.post('/projects')
    def create(body:dict):
        if not isinstance(body.get('title'),str): raise ValueError('Enter a project name.')
        title=body.get('title','').strip()
        locale=body.get('locale','zh-CN')
        if not 1<=len(title)<=100 or locale not in {'en','zh-CN'}:
            raise ValueError('Enter a project name up to 100 characters.')
        return store.create(title,locale)

    @router.get('/projects/{pid}')
    def project(pid:str): return store.get(pid)

    @router.post('/projects/{pid}/messages')
    def message(pid:str,body:dict): return agent.message(pid,body)

    @router.post('/projects/{pid}/models')
    def models(pid:str,body:dict): return connections.assign_roles(pid,body)

    @router.post('/projects/{pid}/approve')
    def approve(pid:str,body:dict): return store.approve(pid,body.get('revision'))

    @router.post('/projects/{pid}/build')
    def build(pid:str,body:dict): return builder.start(pid,body)

    @router.get('/demo')
    def demo():
        folder=root/'examples/cup-handle'
        return dict(result=json.loads((folder/'result.json').read_text(encoding='utf-8')),
                    config=json.loads((folder/'config.json').read_text(encoding='utf-8')))

    @router.get('/projects/{pid}/runs')
    def list_runs(pid:str):return runs.list(pid)

    @router.get('/execution-catalog')
    def execution_catalog():
        from .universe import SYMBOLS
        from .market import PRICE_BASIS_NOTE
        return dict(symbols=SYMBOLS,price_basis=PRICE_BASIS_NOTE)

    @router.post('/projects/{pid}/prepare-data')
    def prepare_data(pid:str,body:dict):return preparation.start(pid,body)

    @router.get('/projects/{pid}/prepare-data')
    def preparation_status(pid:str):return store.get(pid).get('data_preparation')

    @router.post('/projects/{pid}/runs')
    def start_run(pid:str,body:dict):return runs.start(pid,body)

    @router.get('/projects/{pid}/runs/{rid}')
    def run_detail(pid:str,rid:str):
        r=runs.get(pid,rid)
        return {k:v for k,v in r.items() if k!='market'}

    @router.get('/projects/{pid}/runs/{rid}/status')
    def run_status(pid:str,rid:str):return runs.summary(runs.get(pid,rid))

    @router.get('/projects/{pid}/runs/{rid}/images/{sha256}')
    def run_image(pid:str,rid:str,sha256:str):
        from fastapi.responses import Response
        from .project_charts import read_chart
        return Response(read_chart(store,pid,rid,sha256,runs.get(pid,rid)),media_type='image/png',headers={'ETag':'"'+sha256+'"','X-Content-Type-Options':'nosniff'})

    @router.post('/projects/{pid}/runs/{rid}/cancel')
    def cancel_run(pid:str,rid:str):return runs.cancel(pid,rid)

    @router.get('/providers')
    def providers():
        return [dict(id=k,label=p['label'],environment_available=bool(__import__('os').getenv(p['env'])),
                     protocol=p['protocol']) for k,p in PROVIDERS.items()]

    @router.get('/connections')
    def list_connections(): return connections.list()

    @router.get('/credential-capability')
    def credential_capability(): return connections.capability()

    @router.get('/runtime-status')
    def runtime_status():
        import os,shutil
        from .docker_runtime import backend,connect,WORKER_IMAGE
        selected=backend()
        if selected=='mxc':
            available=os.name=='nt' and bool(shutil.which('codex'))
            return dict(backend='mxc',available=available,detail='Windows MXC and Codex required. Every task probes isolation before execution.')
        client=None
        try:
            client=connect();client.images.get(WORKER_IMAGE)
            return dict(backend='docker',available=True,detail='Engine and worker image available. Every task verifies isolation before execution; this status is not a security acceptance result.')
        except Exception as exc:
            return dict(backend='docker',available=False,detail=str(exc) if isinstance(exc,ValueError) else 'Worker image unavailable. Run the maintained Docker launch script.')
        finally:
            if client:client.close()

    @router.post('/connections/{cid}/credentials')
    def renew_credentials(cid:str,body:dict):return connections.renew(cid,body)

    @router.post('/connections/{cid}/images')
    def image_policy(cid:str,body:dict):return connections.configure_images(cid,body)

    @router.post('/connections')
    def connection(body:dict): return connections.create(body)

    @router.delete('/connections/{cid}')
    def remove(cid:str): connections.delete(cid);return {'ok':True}

    @router.post('/connections/catalog')
    def catalog(body:dict): return connections.catalog(body)

    @router.post('/connections/{cid}/check')
    def check(cid:str): return connections.check(cid)

    return router
