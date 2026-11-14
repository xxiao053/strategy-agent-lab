import json
import httpx
import pytest
from lab.execution_contract import Manifest
from tests.test_project_judgment import setup
from tests.test_managed_execution import policy,candidate,entry
from tests.test_project_execution import manifest


def assessment_manifest(**changes):
    m=manifest(True)
    m['account']=policy()
    m['judgment'].update(rubric={
        'base':{'description':'A sustained base, not an immediate reversal.','start_anchor':'left','end_anchor':'right'},
        'continuation':{'description':'An attached upper consolidation.','start_anchor':'right','end_anchor':'end'}},
        review_nonpass=True,repair_once=True,chart_history='declared')
    m['judgment'].update(changes)
    return Manifest.model_validate(m)


def proposals():
    return {**entry(),'judgment':'Check both criteria for each fixed candidate.',
            'candidates':[{**candidate(name),'dates':{'left':'2024-01-02','right':'2024-01-02','end':'2024-01-02'}} for name in ['one','two','three']]}


def reply(verdicts):
    raw={'assessments':{cid:{label:{'verdict':verdict,'reason':'Observed fixed region','evidence':[{'symbol':'SPY','date':'2024-01-02'}]}
                                for label in ['base','continuation']} for cid,verdict in verdicts.items()}}
    return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(raw)}]}],
            'usage':{'input_tokens':100,'output_tokens':100}}


def test_nonpass_review_is_scoped_even_when_another_candidate_passes(tmp_path,monkeypatch):
    calls=[]
    def transport(request):
        wire=json.loads(request.content);calls.append(wire)
        return httpx.Response(200,json=reply({'one':'pass','two':'fail','three':'insufficient_evidence'} if len(calls)==1 else {'two':'pass','three':'fail'}))
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport);judge.manifest=assessment_manifest()
    context['bars']['QQQ']=[{'date':'2024-01-03','open':999,'high':1000,'low':998,'close':999,'volume':1}]
    result=judge({'id':'d1'},context,proposals())
    assert len(calls)==2 and result['selected_candidate_id']=='one' and result['verdict']=='pass'
    schemas=[c['text']['format']['schema']['properties']['assessments']['properties'] for c in calls]
    assert list(schemas[0])==['one','two','three'] and list(schemas[1])==['two','three']
    assert 'QQQ' not in json.dumps(calls)
    assert [a['verdict'] for a in result['assessments']]==['pass','pass','fail']
    assert len(result['primary']['assessments'])==3 and len(result['review']['assessments'])==2
    assert [r['stage'] for r in store.get(pid)['records']]==['primary','review']
    assert len(result['request_ids'])==2 and len(list((tmp_path/'workspace-receipts').iterdir()))==2


def test_earliest_final_passing_candidate_wins_after_review(tmp_path,monkeypatch):
    count=[]
    def transport(request):
        count.append(1)
        return httpx.Response(200,json=reply({'one':'fail','two':'pass','three':'pass'} if len(count)==1 else {'one':'pass'}))
    _,_,judge,context=setup(tmp_path,monkeypatch,transport);judge.manifest=assessment_manifest()
    assert judge({'id':'d1'},context,proposals())['selected_candidate_id']=='one'


def test_invalid_key_or_outside_region_gets_only_one_saved_format_repair(tmp_path,monkeypatch):
    count=[]
    def transport(request):
        count.append(1)
        raw=reply({'one':'pass','two':'pass','three':'pass'})
        if len(count)==1:
            value=json.loads(raw['output'][0]['content'][0]['text'])
            value['assessments']['one']['base']['evidence'][0]['date']='2024-01-03'
            raw['output'][0]['content'][0]['text']=json.dumps(value)
        return httpx.Response(200,json=raw)
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport);judge.manifest=assessment_manifest()
    result=judge({'id':'d1'},context,proposals())
    assert len(count)==2 and result['verdict']=='pass'
    assert [r['status'] for r in store.get(pid)['records']]==['invalid_response','completed']


def test_persistent_malformed_assessments_stop_after_one_repair(tmp_path,monkeypatch):
    count=[]
    def transport(request):count.append(1);return httpx.Response(200,json=reply({'foreign':'pass'}))
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport);judge.manifest=assessment_manifest()
    with pytest.raises(ValueError,match='invalid_response'):judge({'id':'d1'},context,proposals())
    assert len(count)==2 and len(store.get(pid)['records'])==2
    assert all(r['status']=='invalid_response' for r in store.get(pid)['records'])


def test_unknown_outcome_never_uses_format_repair_or_conditional_review(tmp_path,monkeypatch):
    calls=[]
    def transport(request):calls.append(1);raise httpx.ReadTimeout('offline unknown')
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport);judge.manifest=assessment_manifest()
    with pytest.raises(ValueError,match='infrastructure_failure'):judge({'id':'d1'},context,proposals())
    records=store.get(pid)['records']
    assert len(calls)==1 and len(records)==1 and records[0]['status']=='unknown' and records[0]['committed_cost']>0


def test_rubric_aggregation_cannot_turn_one_failed_check_into_pass(tmp_path,monkeypatch):
    raw=reply({'one':'pass','two':'pass','three':'pass'})
    value=json.loads(raw['output'][0]['content'][0]['text'])
    for checks in value['assessments'].values():checks['base']['verdict']='fail'
    raw['output'][0]['content'][0]['text']=json.dumps(value)
    _,_,judge,context=setup(tmp_path,monkeypatch,lambda request:httpx.Response(200,json=raw))
    judge.manifest=assessment_manifest(review_nonpass=False)
    result=judge({'id':'d1'},context,proposals())
    assert result['verdict']=='fail' and result['selected_candidate_id'] is None


def test_full_history_judgment_can_make_request_49_within_approved_spend(tmp_path,monkeypatch):
    _,_,judge,context=setup(tmp_path,monkeypatch,lambda request:httpx.Response(200,json=reply({'one':'pass','two':'pass','three':'pass'})))
    judge.manifest=assessment_manifest();judge.calls=48
    assert judge({'id':'next'},context,proposals())['verdict']=='pass'
    assert judge.calls==49


def test_declared_chart_history_includes_160_bars_and_fixed_candidate_markers():
    from tests.test_project_scale import full_scope
    from lab.project_charts import render_chart,chart_source
    data,_,config=full_scope();rows=[b.model_dump() for b in data['SPY'][1:161]]
    context={'cutoff':rows[-1]['date'],'bars':{'SPY':rows}}
    fixed={**candidate(),'dates':{'left':rows[5]['date'],'right':rows[130]['date'],'end':rows[-2]['date']}}
    image=render_chart(context,'SPY',history_bars=160,candidate=fixed)
    assert image['source']['bar_count']==160 and image['source']['omitted_earlier_bars']==0
    assert image['source']['candidate']['candidate_id']=='one' and image['source']['candidate']['dates']==fixed['dates']
    assert image['source']['renderer']=='ohlcv-v2'
    assert chart_source(context,'SPY')[1]['bar_count']==120
    with pytest.raises(ValueError):render_chart(context,'SPY',history_bars=160,candidate={**fixed,'dates':{'future':'2030-01-01'}})


def test_three_candidate_chart_request_preserves_each_png_and_checks_billing(tmp_path,monkeypatch):
    calls=[]
    def transport(request):calls.append(json.loads(request.content));return httpx.Response(200,json=reply({'one':'pass','two':'pass','three':'pass'}))
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport)
    judge.manifest=assessment_manifest(input_mode='chart_and_text')
    store.mutate(pid,lambda p:p.update(busy=False))
    judge.cfg=judge.connections.configure_images(judge.cfg['id'],{'enabled':True,'billing_profile':'token-v1'})
    judge.budget=10
    store.mutate(pid,lambda p:p.update(busy=True))
    decision={'id':'pictures'}
    result=judge(decision,context,proposals())
    assert result['verdict']=='pass' and len(decision['images'])==3
    assert {im['source']['candidate']['candidate_id'] for im in decision['images']}=={'one','two','three'}
    assert store.get(pid)['records'][0]['image_input']['count']==3


def test_candidate_judgment_uses_160_model_bars_from_170_calculation_bars(tmp_path,monkeypatch):
    from tests.test_project_scale import full_scope
    captured=[]
    def transport(request):captured.append(json.loads(request.content));return httpx.Response(200,json=reply({'one':'pass','two':'pass','three':'pass'}))
    _,_,judge,context=setup(tmp_path,monkeypatch,transport)
    m=assessment_manifest().model_dump(by_alias=True);m.update(history_bars=170,warmup_bars=169);m['judgment']['history_bars']=160
    judge.manifest=Manifest.model_validate(m)
    data,_,_=full_scope();rows=[b.model_dump() for b in data['SPY'][:170]]
    context.update(cutoff=rows[-1]['date'],bars={'SPY':rows})
    p=proposals()
    for c in p['candidates']:c['dates']={k:rows[10]['date'] for k in c['dates']}
    # A stopped invalid response still exposes the actual outbound cutoff scope.
    with pytest.raises(ValueError):judge({'id':'scope'},context,p)
    facts=json.loads(captured[0]['input'][0]['content'][0]['text'])
    assert len(facts['bars']['SPY'])==160 and facts['bars']['SPY'][0]['date']==rows[10]['date']


def test_simple_declared_history_chart_roundtrips_without_false_tamper_error(tmp_path,monkeypatch):
    from tests.test_project_scale import full_scope
    from tests.test_project_judgment import response
    from tests.test_project_execution import proposal
    from lab.execution_contract import digest
    from lab.project_charts import verify_chart_source
    calls=[]
    market,_,_=full_scope();rows=[b.model_dump() for b in market['SPY'][:170]]
    def transport(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json=response(evidence=[{'symbol':'SPY','date':rows[-1]['date']}]))
    store,pid,judge,context=setup(tmp_path,monkeypatch,transport)
    value=manifest(True);value.update(history_bars=170,warmup_bars=169)
    value['judgment'].update(input_mode='chart_and_text',chart_history='declared',history_bars=160)
    judge.manifest=Manifest.model_validate(value)
    store.mutate(pid,lambda p:p.update(busy=False))
    judge.cfg=judge.connections.configure_images(judge.cfg['id'],{'enabled':True,'billing_profile':'token-v1'})
    store.mutate(pid,lambda p:p.update(busy=True));judge.budget=10
    context.update(cutoff=rows[-1]['date'],bars={'SPY':rows})
    decision={'id':'chart','cutoff':context['cutoff'],'input_hash':digest(context),'proposal':proposal(judgment='Check shape')}
    judge(decision,context,decision['proposal'])
    saved={'inputs':{context['cutoff']:context},'frozen':{'manifest':value}}
    verify_chart_source(saved,decision,decision['images'][0])
    facts=json.loads(calls[0]['input'][0]['content'][0]['text'])
    assert len(facts['bars']['SPY'])==160
