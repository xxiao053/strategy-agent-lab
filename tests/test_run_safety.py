import json
import os
import sqlite3
import httpx
import pytest

pytestmark = pytest.mark.market_data
from lab.contracts import RunConfig
from lab.runner import Runner
from lab.store import Store
from tests.test_workflow import ROOT
from tests.helpers import bound_reply


def test_baseline_replay_chain_uses_original_execution(tmp_path):
    s=Store(tmp_path/'lab.db'); r=Runner(ROOT,s)
    first=r.create(RunConfig(symbols=['AAPL'],start='2024-12-19',end='2024-12-23',approved=True))
    r.execute(first['id'])
    second=r.replay(first['id']);r.execute(second['id'])
    third=r.replay(second['id']);r.execute(third['id'])
    assert s.get(third['id'])['status']=='completed'
    assert s.get(third['id'])['state']==s.get(first['id'])['state']


def test_non_luna_models_require_confirmed_prices_and_capabilities(tmp_path, monkeypatch):
    monkeypatch.setenv('DASHSCOPE_API_KEY','offline')
    r=Runner(ROOT,Store(tmp_path/'lab.db'))
    c=RunConfig(provider='qwen',model='qwen-plus',mode='live',approved=True,paid_authorized=True)
    with pytest.raises(ValueError,match='pricing'):
        r.create(c)
    c=RunConfig(**{**c.model_dump(),'pricing_confirmed':True,'price_note':'User checked USD-equivalent prices'})
    with pytest.raises(ValueError,match='capabilit'):
        r.create(c)


def test_actual_request_and_tool_transcript_are_saved_without_auth(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','offline-secret')
    calls=[]
    def handler(req):
        payload=json.loads(req.content);calls.append(payload)
        ctx=json.loads(payload['input'][0]['content'][0]['text']);dates=[b['date'] for b in ctx['bars']]
        if len(calls)==1:
            out=[{'type':'function_call','call_id':'call1','name':'read_bars','arguments':json.dumps({'symbol':'AAPL','start_date':dates[-3],'end_date':dates[-1]})}]
        else:
            decision=bound_reply(ctx)
            out=[{'type':'message','content':[{'type':'output_text','text':json.dumps(decision)}]}]
        return httpx.Response(200,json={'status':'completed','output':out,'usage':{'input_tokens':100,'output_tokens':50}})
    store=Store(tmp_path/'lab.db');r=Runner(ROOT,store,client=httpx.Client(transport=httpx.MockTransport(handler)))
    run=r.create(RunConfig(symbols=['AAPL'],start='2024-12-19',end='2024-12-23',mode='live',approved=True,paid_authorized=True,review_enabled=False))
    r.execute(run['id'])
    receipts=store.requests(run['id'])
    assert len(receipts)==2
    assert receipts[0]['request']['body']==calls[0]
    assert receipts[1]['request']['body']==calls[1]
    assert 'function_call_output' in json.dumps(receipts[1]['request'])
    assert 'offline-secret' not in json.dumps(receipts)
    replay=r.replay(run['id']);r.execute(replay['id'])
    third=r.replay(replay['id']);r.execute(third['id'])
    assert store.get(third['id'])['status']=='completed'
    assert store.get(third['id'])['state']==store.get(run['id'])['state']
    assert len(calls)==2
