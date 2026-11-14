"""SDK HTTP boundary: reserve before dispatch, durable receipt before interpretation."""
import asyncio
import json
import uuid
import httpx
from .providers import endpoint,normalize_usage
from .workspace_store import now
from .construction_limits import MAX_REQUEST_BYTES,MAX_OUTPUT_TOKENS,cost_estimate
from .billing import record_pricing,settlement,usage_reported
from .provider_io import validate_headers

MAX_CONSTRUCTION_REQUESTS=50
MAX_RESPONSE_BYTES=32*1024*1024
MAX_RESPONSE_SECONDS=240


def interruption_category(error):
    """Only fixed categories cross the boundary, never exception or proxy details."""
    for kind,category in (
        (asyncio.CancelledError,'cancelled'),
        (httpx.ConnectTimeout,'connection_timeout'),(httpx.ReadTimeout,'read_timeout'),
        (httpx.WriteTimeout,'write_timeout'),(httpx.PoolTimeout,'pool_timeout'),
        (httpx.ConnectError,'connection_error'),(httpx.ProxyError,'proxy_error'),
        (httpx.HTTPStatusError,'provider_http_error'),(httpx.HTTPError,'transport_error'),
    ):
        if isinstance(error,kind):return category
    return 'interrupted'


class BudgetTransport(httpx.AsyncBaseTransport):
    def __init__(self,store,connections,pid,cfg,key,budget,bid,*,transport=None,check_task=lambda:None):
        self.store,self.connections,self.pid,self.cfg,self.key,self.budget,self.bid=store,connections,pid,cfg,key,budget,bid
        self.transport=transport;self.client=None
        self.calls=0;self.failed=False;self.lock=asyncio.Lock()
        self.check_task=check_task

    async def aclose(self):
        if self.client is not None:await self.client.aclose()
        elif self.transport is not None:await self.transport.aclose()

    async def handle_async_request(self,request):
        async with self.lock:
            self.check_task()
            if self.failed or self.calls>=MAX_CONSTRUCTION_REQUESTS:raise ValueError('Construction request limit reached; no retry.')
            if str(request.url)!=endpoint('openai')+'/responses' or request.method!='POST':raise ValueError('Unsupported SDK model destination.')
            content=await request.aread()
            if len(content)>MAX_REQUEST_BYTES:
                raise ValueError(f'Construction request blocked locally: raw request is {len(content)} bytes; limit is {MAX_REQUEST_BYTES} bytes. No provider request sent.')
            body=json.loads(content)
            if body.get('stream') or any(t.get('type') not in {'function','custom'} for t in body.get('tools',[])):
                raise ValueError('Unsupported construction request capability.')
            body.update(model=self.cfg['model'],max_output_tokens=MAX_OUTPUT_TOKENS,store=False,stream=False,service_tier='default')
            for field in ('previous_response_id','conversation','prompt_cache_retention'):body.pop(field,None)
            wire=json.dumps(body,ensure_ascii=False).encode()
            if len(wire)>MAX_REQUEST_BYTES:
                raise ValueError(f'Construction request blocked locally: normalized request is {len(wire)} bytes; limit is {MAX_REQUEST_BYTES} bytes. No provider request sent.')
            reserve=cost_estimate(self.cfg,len(wire)+8000,MAX_OUTPUT_TOKENS)
            rid=uuid.uuid4().hex
            def begin(p):
                self.connections.assert_generation(self.cfg)
                if p['model_roles']['builder'] not in (None,self.cfg['id']):raise ValueError('Builder role changed.')
                if sum(r['committed_cost'] for r in p['records'])+reserve>self.budget:raise ValueError('Project budget exhausted; no request sent.')
                p['records'].append(dict(id=rid,kind='construction',build_id=self.bid,status='running',created=now(),role='builder',
                    connection_id=self.cfg['id'],credential_generation=self.cfg.get('generation',1),model=self.cfg['model'],provider='openai',
                    committed_cost=reserve,reserved_cost=reserve,budget=self.budget,input_price=self.cfg['input_price'],output_price=self.cfg['output_price'],usage=None,error=None,**record_pricing(self.cfg)))
            self.store.mutate(self.pid,begin);self.calls+=1
            try:
                if self.client is None:
                    # HTTPX owns proxy/NO_PROXY/TLS environment routing. Its default
                    # transports make zero retries; supplying one here bypasses routing.
                    self.client=httpx.AsyncClient(transport=self.transport,timeout=120,follow_redirects=False,trust_env=True)
                outbound=httpx.Request('POST',request.url,headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json','Accept-Encoding':'identity'},content=wire,extensions=request.extensions)
                async with asyncio.timeout(MAX_RESPONSE_SECONDS):
                    response=await self.client.send(outbound,stream=True,auth=None)
                    try:
                        validate_headers(response,MAX_RESPONSE_BYTES)
                        raw=bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw)+len(chunk)>MAX_RESPONSE_BYTES:raise ValueError('Provider response exceeds limit.')
                            raw.extend(chunk)
                    finally:await response.aclose()
                folder=self.store.path.parent/'workspace-receipts';folder.mkdir(exist_ok=True)
                (folder/f'{rid}.json').write_bytes(raw)
                if response.status_code!=200:raise httpx.HTTPStatusError('Provider request failed; response retained privately.',request=outbound,response=response)
                data=json.loads(raw);usage=normalize_usage('openai',data.get('usage') or {})
                cost=settlement(self.cfg,usage if usage_reported('openai',data) else None,reserve=reserve)
                def finish(p):next(r for r in p['records'] if r['id']==rid).update(status='completed',usage=usage,**cost)
                self.store.mutate(self.pid,finish)
                return httpx.Response(200,headers={'Content-Type':'application/json'},content=bytes(raw))
            except BaseException as error:
                self.failed=True;diagnostic=interruption_category(error)
                def fail(p):next(r for r in p['records'] if r['id']==rid).update(status='unknown',diagnostic=diagnostic,error='Construction outcome unknown; reservation retained. No automatic retry.')
                self.store.mutate(self.pid,fail)
                if isinstance(error,asyncio.CancelledError):raise
                raise ValueError(f'Construction request interrupted ({diagnostic}); reservation retained. No automatic retry.') from None
