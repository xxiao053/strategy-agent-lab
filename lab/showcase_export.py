"""Explicit, reviewable saved-example projection. Never exports a workspace wholesale."""
import hashlib
import json
import re
from .execution_contract import artifact_map, seal_build, EntryCandidate

INTERNAL_FILES={'BUILD-CONTEXT.json','EXECUTION-CONTRACT.md','MATERIAL-REFERENCES.json',
                'MATERIAL-INDEX.json','METHOD-VIEW.json','BLOCKED.md'}
PUBLIC_FILES={'execution.json','method.json','README.md','result.json'}
HASH=re.compile(r'[a-f0-9]{64}')
PRIVATE=re.compile(r'(?i)(?:\b[a-z]:[\\/]|/(?:Users|home)/|\bsk-(?:proj-)?[a-z0-9_-]{20,}|\b[a-f0-9]{32}\b)')


def export_example(project,runs,*,build_ids,message_ids,slug,title):
    """Selections are explicit; prose still needs human/content and exact-secret review.

    Generated source is returned as inert text. No provider requests, file writes,
    source execution, database access or changes to original objects occur here.
    """
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug):raise ValueError('Invalid public example ID.')
    if not 1<=len(build_ids)<=10 or len(set(build_ids))!=len(build_ids):raise ValueError('Select unique builds.')
    if not 1<=len(message_ids)<=100 or len(set(message_ids))!=len(message_ids):raise ValueError('Select unique messages.')
    messages=project['messages'];source_builds={b['id']:b for b in project.get('builds',[])}
    if not set(build_ids)<=source_builds.keys() or not set(message_ids)<={m['id'] for m in messages}:raise ValueError('Unknown selection.')
    selected=[source_builds[bid] for bid in build_ids]
    selected_versions={b['version'] for b in selected}
    versions=[v for v in project['versions'] if v['version'] in selected_versions]
    if {v['version'] for v in versions}!=selected_versions:raise ValueError('Missing approved version.')
    identifiers={m['id']:f'message-{i+1}' for i,m in enumerate(messages)}
    identifiers.update({b['id']:f'build-v{b["version"]}-{i+1}' for i,b in enumerate(selected)})
    materials={}
    for v in versions:
        for source in v['method'].get('material_sources',[]):
            if source['id'] in materials and materials[source['id']]!=source:raise ValueError('Material identity changed.')
            materials[source['id']]=source
    identifiers.update({mid:f'material-{i+1}' for i,mid in enumerate(materials)})

    def text(value,limit=500000):
        if not isinstance(value,str) or len(value)>limit:raise ValueError('Invalid or excessive example text.')
        for private,public in identifiers.items():value=value.replace(private,public)
        if PRIVATE.search(value):raise ValueError('Private identifier/path or credential-shaped text requires review.')
        return value

    def digest(value):
        if not isinstance(value,str) or not HASH.fullmatch(value):raise ValueError('Missing provenance hash.')
        return value

    def reference(ref):
        if ref['id'] not in materials or materials[ref['id']]['sha256']!=ref['sha256']:raise ValueError('Invalid material citation.')
        return {'id':identifiers[ref['id']],'sha256':digest(ref['sha256']),'start':text(ref['start'],30),'end':text(ref['end'],30)}

    def verdict_view(value):
        from .project_judgment import Verdict
        checked=Verdict.model_validate({k:value[k] for k in ('verdict','reason','evidence')}).model_dump()
        return checked

    def assessments_view(items):
        if not isinstance(items,list) or len(items)>10:raise ValueError('Invalid saved assessments.')
        result=[]
        for item in items:
            checks=item['checks']
            if not isinstance(checks,dict) or not 1<=len(checks)<=5:raise ValueError('Invalid saved rubric checks.')
            if item['verdict'] not in {'pass','fail','insufficient_evidence'}:raise ValueError('Invalid saved verdict.')
            result.append({'candidate_id':text(item['candidate_id'],100),'verdict':item['verdict'],
                           'checks':{text(name,40):verdict_view(value) for name,value in checks.items()}})
        return result

    def stage_view(value):
        return None if value is None else {'verdict':text(value['verdict'],40),'reason':text(value['reason']),
                                          'assessments':assessments_view(value['assessments'])}

    def model_view(value):
        if not value:return None
        public={'verdict':text(value['verdict'],40),'reason':text(value['reason']),
                'evidence':[{'symbol':text(e['symbol'],20),'date':text(e['date'],10)} for e in value.get('evidence',[])],
                'tool_names':[text(t['name'],60) for t in value.get('tools',[])]}
        if 'assessments' in value:
            public.update(assessments=assessments_view(value['assessments']),primary=stage_view(value.get('primary')),
                          review=stage_view(value.get('review')),selected_candidate_id=value.get('selected_candidate_id'))
        return public

    result={'schema':'saved-builder-example-v1','id':slug,'title':text(title,160),
        'selection':'reviewed_subset_not_first_attempt_or_total_cost',
        'messages':[{'id':identifiers[m['id']],'role':m['role'],'text':text(m['text'])} for m in messages if m['id'] in message_ids],
        'materials':[{'id':identifiers[mid],'name':text(s['name'],160),'sha256':digest(s['sha256']),
                      'units':[{'location':text(u['location'],30),'text':text(u['text'])} for u in s['units']]} for mid,s in materials.items()],
        'versions':[{'number':v['version'],'scope':text(v['method'].get('scope','')),
                     'rules':[{'topic':text(r['topic'],200),'rule':text(r['rule']),'source':text(r.get('source','')),
                               'material_refs':[reference(x) for x in r.get('material_refs',[])]} for r in v['method']['rules']]} for v in versions],
        'builds':[],'runs':[]}
    if any(m['role'] not in {'user','assistant'} for m in result['messages']):raise ValueError('Unsupported public message role.')
    for build in selected:
        method=next(v['method'] for v in versions if v['version']==build['version'])
        original_hash=seal_build(build['artifacts'],method)
        if build.get('execution_hash')!=original_hash or build['status']!='completed':raise ValueError('Only sealed completed builds can be shown as validated.')
        files=[]
        for name,original in artifact_map(build['artifacts']).items():
            if name in INTERNAL_FILES or re.fullmatch(r'MATERIAL-\d{3}\.txt',name):continue
            if not (name in PUBLIC_FILES or name.endswith('.py')):raise ValueError('Artifact needs an explicit distribution review.')
            clean=text(original)
            files.append({'name':name,'text':clean,'sha256':hashlib.sha256(clean.encode()).hexdigest(),
                          'original_sha256':hashlib.sha256(original.encode()).hexdigest()})
        validation=build.get('validation') or {}
        result['builds'].append({'id':identifiers[build['id']],'version':build['version'],'status':build['status'],
           'original_build_hash':digest(original_hash),'verification_only':build.get('verification_only') is True,
           'files':files,'validation':{'tests_passed':validation.get('tests_passed') is True,'test_evidence':'generated_self_report',
               'test_output':text(validation.get('test_output','')),'demo_output':text(validation.get('demo_output','')),
               'demo_error':text(validation.get('demo_error',''))}})
    for ordinal,run in enumerate(runs,1):
        if run['build_id'] not in build_ids:raise ValueError('Run does not belong to selected build.')
        build=source_builds[run['build_id']];frozen=run['frozen'];assumptions=frozen['assumptions']
        if frozen['build_hash']!=build['execution_hash'] or run['version']!=build['version']:raise ValueError('Run/build identity mismatch.')
        if run['status'] not in {'completed','failed','cancelled','interrupted'}:raise ValueError('Do not export an active run.')
        decisions=[]
        for decision in run['decisions']:
            p=decision['proposal'];model=decision.get('model')
            images=[]
            for image in decision.get('images',[]):
                s=image['source']
                images.append({'sha256':digest(image['sha256']),'symbol':text(s['symbol'],20),'cutoff':text(s['cutoff'],10),
                      'start':text(s['start'],10),'end':text(s['end'],10),'bar_count':int(s['bar_count']),
                      'visible_bar_count':int(s['visible_bar_count'])})
            decisions.append({'id':text(decision['id'],80),'cutoff':text(decision['cutoff'],10),'status':text(decision['status'],50),
                'symbol':text(p['symbol'],20),'action':text(p['action'],10),'shares':int(p['sizing']['shares']),
                'explanation':text(p['explanation']),'judgment':text(p.get('judgment') or ''),
                'candidates':[EntryCandidate.model_validate(c).model_dump() for c in p.get('candidates',[])],
                'selected_candidate_id':decision.get('selected_candidate_id'),
                'input_hash':digest(decision['input_hash']),'images':images,
                'model':model_view(model)})
        manifest=frozen.get('manifest') or {}
        judgment=manifest.get('judgment') or {}
        account=manifest.get('account') or {}
        result['runs'].append({'id':f'run-v{run["version"]}-{ordinal}','build_id':identifiers[run['build_id']],
           'version':run['version'],'status':run['status'],'completed_sessions':run['completed_sessions'],'total_sessions':run['total_sessions'],
           'original_run_hash':digest(frozen['run_hash']),'market_hash':digest(frozen['market_hash']),
           'price_basis':text(frozen['price_basis']),
           'judgment':{k:judgment[k] for k in ('criteria','trigger','tools','uncertainty','input_mode','rubric','review_nonpass','repair_once','chart_history','history_bars') if k in judgment},
           'account_policy':{k:account[k] for k in ('mode','risk_fraction','max_weight','max_positions','entry_gap_limit','commission','slippage','progress_units','stagnation_sessions','trailing_stop_units') if k in account},
           'assumptions':{key:assumptions[key] for key in ('start','end','symbols','initial_cash','fee_rate')},
           'curve':[{'date':text(p['date'],10),'cash':p['cash'],'equity':p['equity']} for p in run['curve']],
           'trades':[{key:t[key] for key in ('date','signal_date','symbol','action','quantity','price','fee','gross','decision_id','reason')} for t in run['trades']],
           'positions':[{'symbol':symbol,'quantity':quantity} for symbol,quantity in run['positions'].items()],
           'decisions':decisions})
    # Scan actual strings, not JSON escape sequences ("x:\\n" is not a drive path).
    def clean(value):
        if isinstance(value,str):return text(value)
        if isinstance(value,list):return [clean(x) for x in value]
        if isinstance(value,dict):return {text(k):clean(v) for k,v in value.items()}
        return value
    result=clean(result)
    if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>2000000:raise ValueError('Public example exceeds 2 MB.')
    return result
