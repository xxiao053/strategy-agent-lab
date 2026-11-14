"""Trusted strategy-v1 contract. Parsing artifacts never executes generated code."""
import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator,field_validator
from .contracts import iso


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)


class Responsibilities(Strict):
    code: str=Field(min_length=1,max_length=4000)
    model: str | None=Field(max_length=4000)


class RubricItem(Strict):
    description: str=Field(min_length=1,max_length=2000)
    start_anchor: str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,39}$')
    end_anchor: str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,39}$')


class Judgment(Strict):
    criteria: str=Field(min_length=1,max_length=6000)
    trigger: str=Field(min_length=1,max_length=2000)
    tools: list[Literal['read_bars','price_facts']]=Field(max_length=2)
    uncertainty: Literal['skip','stop']
    input_mode: Literal['text_only','chart_and_text']='text_only'
    rubric: dict[str,RubricItem]=Field(default_factory=dict,max_length=5)
    review_nonpass: bool=False
    repair_once: bool=False
    chart_history: Literal['recent','declared']='recent'
    history_bars: int | None=Field(default=None,ge=1,le=501)

    @field_validator('rubric')
    @classmethod
    def rubric_names(cls,value):
        if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}',name) for name in value):raise ValueError('Invalid rubric name.')
        return value


class ManagedPolicy(Strict):
    mode: Literal['risk-managed']
    risk_fraction: float=Field(gt=0,le=1)
    max_weight: float=Field(gt=0,le=1)
    max_positions: int=Field(ge=1,le=100)
    entry_gap_limit: float=Field(ge=0,le=.5)
    commission: float=Field(ge=0,le=.05)
    slippage: float=Field(ge=0,le=.05)
    progress_units: float=Field(gt=0,le=100)
    stagnation_sessions: int=Field(ge=0,le=1000)
    trailing_stop_units: float=Field(ge=0,le=100)


class EntryCandidate(Strict):
    candidate_id: str=Field(pattern=r'^[A-Za-z0-9_.:-]{1,100}$')
    stop: float=Field(gt=0)
    target: float=Field(gt=0)
    volatility_unit: float=Field(gt=0)
    dates: dict[str,str]=Field(min_length=1,max_length=20)
    facts: dict

    @field_validator('dates')
    @classmethod
    def valid_dates(cls,value):
        for day in value.values():iso(day)
        return value

    @model_validator(mode='after')
    def bounds(self):
        if self.target<=self.stop:raise ValueError('Candidate target must exceed its stop.')
        validate_state(self.facts)
        return self


class Manifest(Strict):
    schema_version: Literal['strategy-v1']=Field(alias='schema')
    entrypoint: Literal['strategy.py:decide']
    warmup_bars: int=Field(ge=0,le=500)
    history_bars: int=Field(ge=1,le=501)
    responsibilities: Responsibilities
    judgment: Judgment | None
    account: ManagedPolicy | None=None

    @model_validator(mode='after')
    def coherent(self):
        if self.history_bars<=self.warmup_bars:
            raise ValueError('history_bars must include warmup and the current bar.')
        if bool(self.responsibilities.model)!=bool(self.judgment):
            raise ValueError('Model responsibilities require a matching judgment contract.')
        if self.judgment and len(set(self.judgment.tools))!=len(self.judgment.tools):
            raise ValueError('Duplicate tools.')
        if self.judgment and self.judgment.history_bars and self.judgment.history_bars>self.history_bars:
            raise ValueError('Model history cannot exceed the strategy calculation history.')
        return self


class Sizing(Strict):
    shares: int=Field(ge=0,le=10000000)


class Proposal(Strict):
    symbol: str=Field(pattern=r'^[A-Z][A-Z0-9.-]{0,9}$')
    action: Literal['buy','sell','hold']
    explanation: str=Field(min_length=1,max_length=2000)
    sizing: Sizing
    judgment: str | None=Field(min_length=1,max_length=2000)
    candidates: list[EntryCandidate]=Field(default_factory=list,max_length=10)
    priority: float=0

    @model_validator(mode='after')
    def size(self):
        if self.candidates:
            if self.action!='buy' or self.sizing.shares!=0:raise ValueError('Managed entries delegate sizing to the account.')
            ids=[c.candidate_id for c in self.candidates]
            if len(ids)!=len(set(ids)):raise ValueError('Duplicate candidate IDs.')
            return self
        if (self.action=='hold')!=(self.sizing.shares==0):
            raise ValueError('Hold needs zero shares; buy/sell need positive shares.')
        if self.action=='hold' and self.judgment:
            raise ValueError('Hold cannot trigger a paid judgment.')
        return self


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def parse_output(text):
    if not isinstance(text,str) or len(text.encode())>65536:raise ValueError('Decision output exceeds 64 KB.')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('Duplicate JSON keys.')
            result[k]=v
        return result
    def nonfinite(_):raise ValueError('Non-finite JSON.')
    try:return json.loads(text,object_pairs_hook=pairs,parse_constant=nonfinite)
    except (TypeError,RecursionError,json.JSONDecodeError):raise ValueError('Decision must be one JSON document.') from None


def validate_state(value):
    def check(item,depth=0):
        if depth>8:raise ValueError('Strategy state exceeds depth limit.')
        if isinstance(item,dict):
            if any(not isinstance(k,str) for k in item):raise ValueError('State keys must be strings.')
            for v in item.values():check(v,depth+1)
        elif isinstance(item,list):
            for v in item:check(v,depth+1)
        elif item is not None and type(item) not in {str,int,float,bool}:raise ValueError('State must be JSON.')
    if not isinstance(value,dict):raise ValueError('Strategy state must be a JSON object.')
    check(value)
    if len(canonical(value).encode())>16384:raise ValueError('Strategy state exceeds 16 KB.')
    return value


def validate_proposals(value,manifest,symbols):
    if not isinstance(value,list) or len(value)>len(symbols):raise ValueError('Invalid proposal count.')
    result=[];seen=set()
    for item in value:
        p=Proposal.model_validate(item)
        if p.symbol not in symbols or p.symbol in seen:raise ValueError('Unknown or duplicate proposal symbol.')
        if p.judgment and not manifest.judgment:raise ValueError('Manifest does not authorize model judgments.')
        if p.candidates and not manifest.account:raise ValueError('Candidates require an approved managed account policy.')
        if manifest.account and p.action=='buy' and not p.candidates:raise ValueError('Managed entries require fixed candidates.')
        seen.add(p.symbol);result.append(p.model_dump())
    return result


def validate_decision(value,manifest,symbols):
    if not isinstance(value,dict) or set(value)!={'proposals','state'}:
        raise ValueError('decide must return exactly proposals and state.')
    return dict(proposals=validate_proposals(value['proposals'],manifest,symbols),state=validate_state(value['state']))


def artifact_map(artifacts):
    result={};total=0
    if not isinstance(artifacts,list) or len(artifacts)>80:raise ValueError('Invalid build artifacts.')
    for item in artifacts:
        name=item.get('name');text=item.get('text')
        if (not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,160}',name)
            or any(p in {'','..','.'} for p in name.split('/')) or PurePosixPath(name).is_absolute()
            or name in result or not isinstance(text,str)):
            raise ValueError('Unsafe or duplicate artifact path.')
        size=len(text.encode());total+=size
        if size>256000 or total>1000000:raise ValueError('Build artifact size limit exceeded.')
        result[name]=text
    return result


def seal_build(artifacts,method):
    files=artifact_map(artifacts)
    if not {'strategy.py','execution.json','method.json'}<=files.keys():
        raise ValueError('Rebuild this approved version to generate strategy.py and execution.json (strategy-v1).')
    try:
        Manifest.model_validate(parse_output(files['execution.json']))
        if parse_output(files['method.json'])!=method:raise ValueError('Approved method changed.')
        if not method.get('rules') or any(q.get('blocking') for q in method.get('questions',[])):
            raise ValueError('Missing executable method decisions; clarify before rebuilding.')
    except ValueError as exc:
        raise ValueError('Invalid execution contract or approved method. Clarify missing decisions and rebuild.') from exc
    return digest({'method':method,'files':files})


def resolve_build(project,bid):
    build=next((b for b in project.get('builds',[]) if b['id']==bid),None)
    if not build or build['status']!='completed':raise ValueError('Choose a completed build from this project.')
    version=next((v for v in project['versions'] if v['version']==build['version']),None)
    if not version:raise ValueError('Build has no approved method version.')
    if not build.get('execution_hash'):raise ValueError('Rebuild this approved version for the strategy-v1 execution contract; old results remain available.')
    actual=seal_build(build['artifacts'],version['method'])
    if actual!=build['execution_hash']:raise ValueError('Build hash changed; rebuild before execution.')
    manifest=Manifest.model_validate(parse_output(artifact_map(build['artifacts'])['execution.json']))
    return build,version,manifest


def verify_execution_contract(work,method,isolated):
    """Host-selected smoke inputs/validation; generated tests cannot redefine these checks."""
    import sys
    from datetime import date,timedelta
    from .build_runtime import collect_artifacts
    files=collect_artifacts(work);before=seal_build(files,method)
    manifest=Manifest.model_validate(parse_output(artifact_map(files)['execution.json']))
    history=[];day=date(2020,1,1)
    while len(history)<manifest.history_bars+1:
        if day.weekday()<5:
            n=len(history)
            history.append(dict(date=day.isoformat(),open=100+n/10,high=102+n/10,low=99+n/10,close=101+n/10,volume=1000000))
        day+=timedelta(days=1)
    state={}
    for offset in [0,1]:
        rows=history[offset:manifest.history_bars+offset]
        context=dict(schema='strategy-v1',cutoff=rows[-1]['date'],bars={'SPY':rows},
                     account=dict(cash=10000.0,equity=10000.0,positions={}),previous_orders=[],state=state)
        if manifest.account:
            from .project_managed import Account,snapshot
            context['account']=snapshot(Account(10000.0),{})
        script=('import sys,json,runpy,os;sys.dont_write_bytecode=True;sys.path.insert(0,os.getcwd());'
                'context=json.loads('+repr(canonical(context))+');'
                'strategy=runpy.run_path("strategy.py");'
                "print(json.dumps(strategy['decide'](context),allow_nan=False))")
        response=isolated([sys.executable,'-I','-B','-c',script])
        if seal_build(collect_artifacts(work),method)!=before:raise ValueError('Independent decision checks changed protected project files.')
        if response.returncode:raise ValueError('Independent strategy-v1 decision execution failed. Rebuild to repair the contract.')
        output=validate_decision(parse_output(response.stdout.strip()),manifest,['SPY']);state=output['state']
    return dict(execution_contract='strategy-v1',independent_decisions=2,execution_hash=before)
