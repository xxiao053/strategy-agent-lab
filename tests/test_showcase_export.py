"""Public projection must not turn a private workspace into a database export."""
import copy
import hashlib
import json
import pytest


def fixture():
    mid='a'*32;bid='b'*32;cid='c'*32;material='d'*32
    method={'scope':'Daily fixture','rules':[{'topic':'entry','rule':'Buy three shares','source':'message '+mid,
         'material_refs':[{'id':material,'sha256':'e'*64,'start':'L1','end':'L1'}]}],'questions':[],
         'material_sources':[{'id':material,'name':'notes.md','sha256':'e'*64,'units':[{'location':'L1','text':'Buy three shares'}]}]}
    files=[{'name':'strategy.py','text':'def decide(c): return {"proposals":[],"state":{}}'},
           {'name':'execution.json','text':json.dumps({'schema':'strategy-v1','entrypoint':'strategy.py:decide','warmup_bars':0,'history_bars':1,'responsibilities':{'code':'Rule','model':None},'judgment':None})},
           {'name':'method.json','text':json.dumps(method)},
           {'name':'BUILD-CONTEXT.json','text':'private context'},
           {'name':'README.md','text':'<script>alert(1)</script> is inert example text.'}]
    from lab.execution_contract import seal_build
    build={'id':bid,'version':1,'status':'completed','artifacts':files,'execution_hash':seal_build(files,method),
           'connection_id':cid,'validation':{'tests_passed':True,'test_output':'LAB_TEST_RESULT:{"executed":1,"passed":true}',
                 'demo_output':'{"synthetic":true}','demo_error':'','execution_contract':'strategy-v1'},'verification_only':True}
    project={'id':'f'*32,'title':'Private title','versions':[{'version':1,'method':method}],'builds':[build],
          'messages':[{'id':mid,'role':'user','text':'Buy three shares','created':'2026-01-01'}],
          'records':[{'secret':'NEVER_EXPORT','committed_cost':4}],'model_roles':{'builder':cid}}
    run={'id':'9'*32,'build_id':bid,'version':1,'status':'completed','completed_sessions':1,'total_sessions':1,
         'frozen':{'build_hash':build['execution_hash'],'market_hash':'8'*64,'run_hash':'7'*64,
           'price_basis':'Fixture only','model':{'id':cid,'key':'NEVER_EXPORT'},
           'assumptions':{'start':'2024-01-02','end':'2024-01-02','symbols':['SPY'],'initial_cash':100,'fee_rate':0,'budget':4}},
         'curve':[{'date':'2024-01-02','equity':100,'cash':100,'positions':{}}],
         'trades':[],'decisions':[],'positions':{},'market':{'PRIVATE_BARS':[]},'inputs':{'PRIVATE_INPUT':1}}
    return project,[run],bid,mid


def export():
    from lab.showcase_export import export_example
    p,r,b,m=fixture()
    return export_example(p,r,build_ids=[b],message_ids=[m],slug='fixture',title='Reviewed fixture')


def test_public_projection_remaps_identity_omits_private_fields_and_keeps_real_evidence():
    result=export();text=json.dumps(result)
    assert not any(x in text for x in ['NEVER_EXPORT','PRIVATE_BARS','PRIVATE_INPUT','committed_cost','BUILD-CONTEXT','a'*32,'b'*32,'c'*32,'d'*32])
    assert result['messages'][0]['text']=='Buy three shares'
    assert result['versions'][0]['rules'][0]['source']=='message message-1'
    assert result['versions'][0]['rules'][0]['material_refs'][0]['id']=='material-1'
    assert result['runs'][0]['build_id']==result['builds'][0]['id']
    assert result['builds'][0]['verification_only'] is True
    assert result['builds'][0]['validation']['test_evidence']=='generated_self_report'
    assert result['selection']=='reviewed_subset_not_first_attempt_or_total_cost'
    f=next(f for f in result['builds'][0]['files'] if f['name']=='strategy.py')
    assert f['sha256']==hashlib.sha256(f['text'].encode()).hexdigest()


@pytest.mark.parametrize('bad',['../escape.py','/abs.py','x\\y.py','a.py:secret','evil.html'])
def test_unsafe_or_unreviewed_artifacts_cannot_leak(bad):
    from lab.showcase_export import export_example
    p,r,b,m=fixture();p['builds'][0]['artifacts'].append({'name':bad,'text':'NEVER_EXPORT'})
    with pytest.raises(ValueError):export_example(p,r,build_ids=[b],message_ids=[m],slug='fixture',title='Reviewed fixture')


@pytest.mark.parametrize('text',['C:\\Users\\Owner\\secret.txt','/Users/owner/private','sk-proj-'+'x'*40,'x'*500001],ids=['windows-path','unix-path','key-shape','oversize'])
def test_unsafe_or_overlarge_text_rejected_instead_of_silently_redacted(text):
    from lab.showcase_export import export_example
    p,r,b,m=fixture();p['messages'][0]['text']=text
    with pytest.raises(ValueError):export_example(p,r,build_ids=[b],message_ids=[m],slug='fixture',title='Reviewed fixture')


def test_foreign_or_tampered_run_cannot_be_associated_with_selected_build():
    from lab.showcase_export import export_example
    p,r,b,m=fixture();r[0]['frozen']['build_hash']='0'*64
    with pytest.raises(ValueError):export_example(p,r,build_ids=[b],message_ids=[m],slug='fixture',title='Reviewed fixture')


def test_export_never_changes_original_private_records():
    from lab.showcase_export import export_example
    p,r,b,m=fixture();before=copy.deepcopy((p,r))
    export_example(p,r,build_ids=[b],message_ids=[m],slug='fixture',title='Reviewed fixture')
    assert (p,r)==before


def test_export_keeps_integer_positions_from_shared_runner():
    from lab.showcase_export import export_example
    p,r,b,m=fixture();r[0]['positions']={'SPY':3}
    result=export_example(p,r,build_ids=[b],message_ids=[m],slug='fixture',title='Reviewed fixture')
    assert result['runs'][0]['positions']==[{'symbol':'SPY','quantity':3}]


def test_plain_text_condition_newline_is_not_a_windows_path_after_json_escaping():
    from lab.showcase_export import export_example
    p,r,b,m=fixture();p['messages'][0]['text']='If x:\n    inspect the evidence.'
    result=export_example(p,r,build_ids=[b],message_ids=[m],slug='fixture',title='Reviewed fixture')
    assert result['messages'][0]['text']=='If x:\n    inspect the evidence.'


def test_managed_export_preserves_candidate_regions_and_primary_review_explanations():
    from lab.showcase_export import export_example
    p,r,b,m=fixture()
    checks={'cup':{'verdict':'pass','reason':'A sustained dated base','evidence':[{'symbol':'SPY','date':'2024-01-02'}]}}
    final={'candidate_id':'SPY-fixed','verdict':'pass','checks':checks}
    primary={'assessments':[{**final,'verdict':'fail','checks':{'cup':{**checks['cup'],'verdict':'fail','reason':'Initial V concern'}}}],
             'request_ids':['5'*32],'tools':[],'verdict':'fail','reason':'initial'}
    review={'assessments':[final],'request_ids':['6'*32],'tools':[],'verdict':'pass','reason':'Dated base resolves concern'}
    r[0]['decisions']=[dict(id='2024-01-02-1',cutoff='2024-01-02',status='ordered',input_hash='3'*64,
        proposal={'symbol':'SPY','action':'buy','sizing':{'shares':0},'explanation':'Managed candidate',
            'judgment':'Assess shape','candidates':[{'candidate_id':'SPY-fixed','stop':90.,'target':130.,'volatility_unit':2.,
                'dates':{'left_rim':'2024-01-02','right_rim':'2024-01-02'},'facts':{'cup_sessions':25}}]},
        model={'verdict':'pass','reason':'SPY-fixed: pass','evidence':checks['cup']['evidence'],'tools':[],
            'assessments':[final],'primary':primary,'review':review,'selected_candidate_id':'SPY-fixed'},
        selected_candidate_id='SPY-fixed')]
    r[0]['frozen']['manifest']={'judgment':{'criteria':'Original confirmed shape criteria'},'account':{'mode':'risk-managed','risk_fraction':.25}}
    result=export_example(p,r,build_ids=[b],message_ids=[m],slug='fixture',title='Reviewed fixture')
    decision=result['runs'][0]['decisions'][0]
    assert decision['candidates']==r[0]['decisions'][0]['proposal']['candidates']
    assert decision['model']['primary']['assessments'][0]['checks']['cup']['reason']=='Initial V concern'
    assert decision['model']['review']['assessments'][0]['checks']['cup']['reason']=='A sustained dated base'
    assert decision['model']['selected_candidate_id']=='SPY-fixed'
    assert result['runs'][0]['judgment']['criteria']=='Original confirmed shape criteria'
    assert result['runs'][0]['account_policy']['risk_fraction']==.25
    assert '5'*32 not in json.dumps(result) and '6'*32 not in json.dumps(result)
