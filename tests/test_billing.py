"""Reservations and measured token pricing must never become provider invoices."""
import pytest
from lab.billing import reserve_cost,settlement,record_pricing,usage_reported

CFG={'provider':'openai','model':'gpt-6-luna','input_price':.1,'output_price':.5}

def test_reservation_uses_one_point_five_but_completed_usage_has_no_safety_factor():
    assert reserve_cost(CFG,1000,200)==pytest.approx(.0003)
    value=settlement(CFG,{'input':1000,'output':200,'cached':0},reserve=.0003)
    assert value['usage_cost']==pytest.approx(.0002)
    assert value['committed_cost']==pytest.approx(.0002)
    assert value['billed_cost'] is None

def test_cached_usage_is_priced_separately_and_real_long_context_tariff_is_not_a_safety_factor():
    value=settlement(CFG,{'input':1000,'output':200,'cached':800},reserve=.01)
    assert value['usage_cost']==pytest.approx(.000128)
    long=settlement(CFG,{'input':300000,'output':1000,'cached':200000},reserve=1)
    assert long['usage_cost']==pytest.approx(.02475)

@pytest.mark.parametrize('usage',[None,{}, {'input':-1,'output':0}, {'input':100,'output':1,'cached':101}, {'input':True,'output':1}])
def test_unavailable_or_invalid_usage_never_becomes_zero_spend(usage):
    value=settlement(CFG,usage,reserve=.05)
    assert value['usage_cost'] is None and value['billed_cost'] is None
    assert value['committed_cost']==.05 and value['cost_status']=='usage_unpriced'

def test_unknown_cache_rate_is_not_silently_treated_as_full_price_or_free():
    cfg={**CFG,'provider':'anthropic','model':'operator-model'}
    value=settlement(cfg,{'input':1000,'output':100,'cached':500},reserve=.1)
    assert value['usage_cost'] is None and value['committed_cost']==.1
    cfg.update(cached_input_price=.02,cache_write_price=.125)
    value=settlement(cfg,{'input':1000,'output':100,'cached':500,'cache_write':100},reserve=.1)
    assert value['usage_cost']==pytest.approx(.0001125)

def test_new_record_freezes_price_basis_and_does_not_claim_a_bill():
    value=record_pricing(CFG)
    assert value['reservation_multiplier']==1.5 and value['billed_cost'] is None
    assert value['pricing']['cached_input_price']==.01
    CFG_copy=dict(CFG);value=record_pricing(CFG_copy);CFG_copy['input_price']=999
    assert value['pricing']['input_price']==.1


def test_connection_can_snapshot_explicit_cache_prices(tmp_path):
    from lab.connections import Connections
    from lab.workspace_store import WorkspaceStore
    connections=Connections(WorkspaceStore(tmp_path/'state.sqlite3'))
    cfg=connections.create(dict(name='Custom pricing',provider='anthropic',model='custom',key='private-test-key',
        input_price=.1,output_price=.5,cached_input_price=.02,cache_write_price=.125))
    saved,_=connections.get(cfg['id'])
    assert saved['cached_input_price']==.02 and saved['cache_write_price']==.125


def test_partial_provider_usage_does_not_price_missing_output_as_free(tmp_path):
    import asyncio,httpx
    from lab.sdk_budget import BudgetTransport
    from tests.test_distribution_credentials import connection
    store,connections,cfg=connection(tmp_path);pid=store.create('P','en')['id']
    async def run():
        transport=BudgetTransport(store,connections,pid,cfg,'old-key-123',1,'build',
            transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'usage':{'input_tokens':10},'output':[]})))
        async with httpx.AsyncClient(transport=transport) as client:
            await client.post('https://api.openai.com/v1/responses',json={'input':'hello'})
    asyncio.run(run());record=store.get(pid)['records'][0]
    assert record['usage_cost'] is None and record['committed_cost']==record['reserved_cost']


def test_original_runner_future_requests_use_same_one_point_five_reservation(tmp_path,monkeypatch):
    import json,httpx
    from lab.contracts import RunConfig
    from lab.providers import ProviderError
    from lab.runner import Runner
    from lab.store import Store
    monkeypatch.setenv('OPENAI_API_KEY','offline-billing-fixture')
    cfg=RunConfig(mode='live',approved=True,paid_authorized=True,use_images=False,input_rate=.1,output_rate=.5)
    store=Store(tmp_path/'original.sqlite3');run=store.create(cfg.model_dump(),{},'offline-fixture')
    def reject(request):return httpx.Response(400,json={'error':{'type':'fixture'}})
    with httpx.Client(transport=httpx.MockTransport(reject)) as client:
        runner=Runner(tmp_path,store,client)
        with pytest.raises(ProviderError):runner.judge(run['id'],'fixture',cfg,{'system':'','text':'hello','images':[]},[],'SPY')
    receipt=store.requests(run['id'])[0]
    wire_bytes=len(json.dumps(receipt['request']['body'],ensure_ascii=False).encode())
    assert receipt['reserved']==pytest.approx((wire_bytes*.1+4096*.5)*1.5/1e6)


@pytest.mark.parametrize('cached,write,expected',[(1,None,.0015),(None,2,.003)])
def test_reservation_covers_explicit_cache_prices_above_uncached_rate(cached,write,expected):
    cfg={**CFG,'cached_input_price':cached,'cache_write_price':write}
    assert reserve_cost(cfg,1000,0)==pytest.approx(expected)


@pytest.mark.parametrize('raw',[
    {'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':100,'thoughtsTokenCount':-99}},
    {'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':100,'cachedContentTokenCount':101}},
    {'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':100,'thoughtsTokenCount':True}},
])
def test_malformed_usage_components_rejected_before_normalization(raw):
    assert usage_reported('gemini',raw) is False


@pytest.mark.parametrize('reported,expected',[
    ({'input_tokens':1000,'output_tokens':200,'input_tokens_details':{'cached_tokens':800}},.000128),
    ({'input_tokens':1000},None),
])
def test_original_runner_new_receipts_price_usage_without_margin_and_keep_legacy(tmp_path,reported,expected,monkeypatch):
    import json,httpx
    from lab.contracts import RunConfig
    from lab.providers import ProviderError
    from lab.runner import Runner
    from lab.store import Store
    monkeypatch.setenv('OPENAI_API_KEY','offline-billing-fixture')
    cfg=RunConfig(mode='live',approved=True,paid_authorized=True,use_images=False,budget_scope='offline')
    store=Store(tmp_path/'original.sqlite3');store.authorize_budget('offline',1)
    old=store.create(cfg.model_dump(),{},'old');store.begin_request(old['id'],'old','old','old',.01,{'body':{}})
    store.save_response('old',{'usage':{}},{'input':1000,'output':200,'reported':True},0)
    preserved=store.requests(old['id'])[0];baseline=store.budget_status('offline')
    run=store.create(cfg.model_dump(),{},'new')
    raw={'status':'incomplete','usage':reported}
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=raw))) as client:
        with pytest.raises(ProviderError):Runner(tmp_path,store,client).judge(run['id'],'fixture',cfg,{'system':'','text':'hello','images':[]},[],'SPY')
    receipt=store.requests(run['id'])[0];usage=receipt['usage']
    assert receipt['request']['billing']['reservation_multiplier']==1.5
    assert usage['accounting_version']==2 and usage['billed_cost'] is None
    if expected is None:assert usage['usage_cost'] is None
    else:assert usage['usage_cost']==pytest.approx(expected)
    occupied=expected if expected is not None else receipt['reserved']
    status=store.budget_status('offline')
    assert status['committed_usd']-baseline['committed_usd']==pytest.approx(occupied)
    summary=store.get(run['id'])['summary']
    assert summary['estimated_cost']==pytest.approx(expected or 0)
    assert summary['unresolved_reserve']==pytest.approx(0 if expected is not None else receipt['reserved'])
    assert store.requests(old['id'])[0]==preserved
    store.delete_runs([run['id']]);assert store.budget_status('offline')==status
