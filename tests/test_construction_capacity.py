"""Roomy construction transport limits do not change spend or tool authority."""
import json
import httpx
import pytest
from tests.test_builder_runtime import setup_project


@pytest.mark.parametrize('request_bytes',[256_000,1_900_000])
def test_native_accepts_large_context_and_reserves_long_context_cost(tmp_path,request_bytes):
    from lab.build_runtime import BudgetRelay
    store,connections,pid,cfg=setup_project(tmp_path);sent=[]
    def provider(request):
        body=json.loads(request.content);sent.append(body)
        upper=len(json.dumps(body,ensure_ascii=False).encode())+8000
        output_multiplier=1.5 if upper>272000 else 1
        input_multiplier=2 if upper>272000 else 1
        record=store.get(pid)['records'][0]
        assert record['reserved_cost']==pytest.approx((upper*cfg['input_price']*input_multiplier+6000*cfg['output_price']*output_multiplier)*1.5/1e6)
        raw={'type':'response.completed','response':{'id':'fixture','usage':{'input_tokens':200000 if request_bytes<300000 else 300000,'output_tokens':5000}}}
        return httpx.Response(200,headers={'Content-Type':'text/event-stream'},text='data: '+json.dumps(raw)+'\n\n')
    with BudgetRelay(store,pid,cfg,'private-real-test-key',10,'fixture',transport=httpx.MockTransport(provider)) as relay:
        with httpx.Client(trust_env=False) as local:
            response=local.post(relay.url+'/responses',headers={'Authorization':'Bearer '+relay.token},json={'input':'x'*request_bytes,'max_output_tokens':99999})
            assert response.status_code==200
    assert len(sent)==1 and sent[0]['input']=='x'*request_bytes and sent[0]['max_output_tokens']==6000
    record=store.get(pid)['records'][0]
    input_tokens=200000 if request_bytes<300000 else 300000
    output_multiplier=1 if input_tokens<=272000 else 1.5
    input_multiplier=1 if input_tokens<=272000 else 2
    assert record['committed_cost']==pytest.approx((input_tokens*cfg['input_price']*input_multiplier+5000*cfg['output_price']*output_multiplier)/1e6)
    assert record['usage_cost']==record['committed_cost'] and record['billed_cost'] is None
    assert record['committed_cost']<record['reserved_cost']


def test_construction_capacity_has_shared_bound_and_long_context_threshold():
    from lab.construction_limits import MAX_REQUEST_BYTES,cost_estimate
    assert MAX_REQUEST_BYTES==2*1024*1024
    cfg={'provider':'openai','model':'gpt-6-luna','input_price':1,'output_price':2}
    assert cost_estimate(cfg,272000,6000)==pytest.approx(.426)
    assert cost_estimate(cfg,272001,6000)==pytest.approx(.843003)
