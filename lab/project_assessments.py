"""Method-neutral fixed-candidate rubric validation, review and ranked selection."""
import copy
from .execution_contract import canonical


def aggregate(verdicts):
    return 'fail' if 'fail' in verdicts else ('insufficient_evidence' if 'insufficient_evidence' in verdicts else 'pass')


def schema_for(candidates,rubric):
    from .project_judgment import Verdict
    item=Verdict.model_json_schema();definitions=item.pop('$defs',{})
    checks=dict(type='object',properties={name:copy.deepcopy(item) for name in rubric},required=list(rubric),additionalProperties=False)
    assessments=dict(type='object',properties={c['candidate_id']:copy.deepcopy(checks) for c in candidates},
                     required=[c['candidate_id'] for c in candidates],additionalProperties=False)
    return dict(type='object',properties={'assessments':assessments},required=['assessments'],additionalProperties=False,**{'$defs':definitions})


def parse_assessments(value,candidates,rubric,symbol,context):
    from .project_judgment import Verdict
    if not isinstance(value,dict) or set(value)!={'assessments'} or not isinstance(value['assessments'],dict):
        raise ValueError('Return exactly the required candidate assessments.')
    raw=value['assessments'];expected={c['candidate_id'] for c in candidates}
    if set(raw)!=expected:raise ValueError('Missing or unknown candidate assessment.')
    visible={b['date'] for b in context['bars'][symbol]};assessments=[];evidence=[]
    for c in candidates:
        checks=raw[c['candidate_id']]
        if not isinstance(checks,dict) or set(checks)!=set(rubric):raise ValueError('Missing or unknown rubric check.')
        parsed={}
        for name,rule in rubric.items():
            verdict=Verdict.model_validate(checks[name]);start=c['dates'][rule.start_anchor];end=c['dates'][rule.end_anchor]
            if not verdict.evidence:raise ValueError('missing_evidence')
            if any(e.symbol!=symbol or e.date not in visible or not start<=e.date<=end for e in verdict.evidence):
                raise ValueError('Evidence outside the fixed candidate rubric region.')
            parsed[name]=verdict.model_dump();evidence.extend(e.model_dump() for e in verdict.evidence)
        assessments.append(dict(candidate_id=c['candidate_id'],checks=parsed,verdict=aggregate([v['verdict'] for v in parsed.values()])))
    return summarize(assessments,evidence)


def summarize(assessments,evidence=None):
    passed=[a for a in assessments if a['verdict']=='pass']
    if evidence is None:evidence=[e for a in assessments for check in a['checks'].values() for e in check['evidence']]
    unique=list({(e['symbol'],e['date']):e for e in evidence}.values())
    verdict='pass' if passed else ('insufficient_evidence' if any(a['verdict']=='insufficient_evidence' for a in assessments) else 'fail')
    return dict(verdict=verdict,reason='; '.join(a['candidate_id']+': '+a['verdict'] for a in assessments),
                selected_candidate_id=passed[0]['candidate_id'] if passed else None,evidence=unique,assessments=assessments)


def assess(judge,decision,context,proposal):
    rubric=judge.manifest.judgment.rubric;candidates=proposal['candidates'];symbol=proposal['symbol']
    if not rubric:raise ValueError('Fixed candidate judgments require an approved rubric.')
    history=judge.manifest.judgment.history_bars or judge.manifest.history_bars
    scoped=dict(context,bars={symbol:context['bars'][symbol][-history:]})
    visible={b['date'] for b in scoped['bars'][symbol]}
    for c in candidates:
        for rule in rubric.values():
            start=c['dates'].get(rule.start_anchor);end=c['dates'].get(rule.end_anchor)
            if start not in visible or end not in visible or start>end:raise ValueError('Invalid fixed rubric date region.')

    def stage(offered,name,prior=None):
        instructions='Assess every offered candidate ID exactly once using each named rubric. Dates and regions are fixed by code; do not move anchors. '+canonical({k:v.model_dump() for k,v in rubric.items()})
        if name=='review':instructions+=' Reconsider only these non-pass IDs against their fixed regions and prior reasons; do not force acceptance.'
        return judge._one(decision,scoped,dict(proposal,candidates=offered),
            schema=schema_for(offered,rubric),parser=lambda value:parse_assessments(value,offered,rubric,symbol,scoped),
            instructions=instructions,stage=name,prior=prior)

    primary=stage(candidates,'primary');final={a['candidate_id']:a for a in primary['assessments']};review=None
    pending=[c for c in candidates if final[c['candidate_id']]['verdict']!='pass']
    if judge.manifest.judgment.review_nonpass and pending:
        review=stage(pending,'review',[final[c['candidate_id']] for c in pending]);final.update({a['candidate_id']:a for a in review['assessments']})
    value=summarize([final[c['candidate_id']] for c in candidates])
    return dict(value,primary=primary,review=review,
                request_ids=primary['request_ids']+(review['request_ids'] if review else []),
                tools=primary['tools']+(review['tools'] if review else []))
