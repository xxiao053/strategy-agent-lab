from datetime import date as Date
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .universe import SYMBOLS


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


def iso(value: str) -> str:
    if Date.fromisoformat(value).isoformat() != value:
        raise ValueError('Use YYYY-MM-DD')
    return value


class Bar(Strict):
    date: str
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)
    _date = field_validator('date')(iso)

    @model_validator(mode='after')
    def prices(self):
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError('Invalid OHLC ordering')
        return self


DEFAULT_RUBRIC = ('Judge only this approved cup-with-handle method. Cup: decline, rounded bottom or '
                 'consolidation and recovery, not mainly a sharp V. Handle: a smaller shallow consolidation '
                 'near the recovered upper rim. Coherence: one connected cup and handle, not unrelated '
                 'segments. Cite dated evidence. If unclear, return insufficient_evidence. Never invent a strategy.')


class Strategy(Strict):
    version: Literal['cup-v2'] = 'cup-v2'
    name: str = Field(default='Cup & Handle · demo balanced', min_length=1, max_length=120)
    method: str = Field(default=DEFAULT_RUBRIC, min_length=20, max_length=8000)
    volume_multiple: float = Field(default=1.2, ge=0.1, le=10)
    cup_min: int = Field(default=25, ge=10, le=100)
    cup_max: int = Field(default=120, ge=10, le=250)
    handle_min: int = Field(default=3, ge=1, le=20)
    handle_max: int = Field(default=40, ge=1, le=80)
    depth_min: float = Field(default=.06, ge=.01, le=.5)
    depth_max: float = Field(default=.4, ge=.01, le=.6)
    prior_advance: float = Field(default=.05, ge=-.5, le=2)
    risk_fraction: float = Field(default=.05, gt=0, le=1)
    max_weight: float = Field(default=.2, gt=0, le=1)
    max_positions: int = Field(default=5, ge=1, le=40)
    history_window: int = Field(default=160, ge=100, le=300)
    trend_period: int = Field(default=50, ge=10, le=100)
    trend_slope_sessions: int = Field(default=10, ge=1, le=40)
    trend_buffer: float = Field(default=0.0, ge=-.2, le=.2)
    trend_slope_min: float = Field(default=0.0, ge=-.1, le=.2)
    breakout_buffer: float = Field(default=0.0, ge=-.1, le=.2)
    breakout_lookback: int = Field(default=20, ge=5, le=80)
    volume_lookback: int = Field(default=20, ge=5, le=80)
    prior_advance_lookback: int = Field(default=20, ge=5, le=80)
    rim_tolerance: float = Field(default=.1, ge=0, le=.5)
    handle_midpoint_fraction: float = Field(default=.5, ge=0, le=1)
    handle_max_drop: float = Field(default=.15, ge=.01, le=.5)
    max_breakout_extension: float = Field(default=.05, gt=0, le=.3)
    entry_gap_limit: float = Field(default=.03, ge=0, le=.2)
    target_multiple: float = Field(default=3.0, gt=0, le=100)
    max_candidates: int = Field(default=3, ge=1, le=3)
    candidate_overlap: float = Field(default=.75, ge=.5, le=1)
    bottom_merge_sessions: int = Field(default=3, ge=0, le=10)
    volatility_period: int = Field(default=20, ge=5, le=100)
    progress_units: float = Field(default=1.0, gt=0, le=10)
    stagnation_sessions: int = Field(default=15, ge=0, le=1000)
    trailing_stop_units: float = Field(default=0.0, ge=0, le=30)
    entry_priority: Literal['alphabetical','momentum','breakout_strength'] = 'alphabetical'
    priority_lookback: int = Field(default=60, ge=5, le=250)
    commission: float = Field(default=.0005, ge=0, le=.02)
    slippage: float = Field(default=.0005, ge=0, le=.02)

    @model_validator(mode='after')
    def bounds(self):
        if self.cup_min > self.cup_max or self.handle_min > self.handle_max or self.depth_min > self.depth_max:
            raise ValueError('Minimum must not exceed maximum')
        if self.breakout_buffer >= self.max_breakout_extension:
            raise ValueError('Breakout buffer must be below allowed extension')
        return self


class RunConfig(Strict):
    symbols: list[str] = Field(default_factory=lambda: ['AAPL', 'MSFT', 'AMZN', 'QQQ', 'SPY'], min_length=1, max_length=60)
    start: str = '2024-01-02'
    end: str = '2026-11-10'
    capital: float = Field(default=100000, ge=100, le=1e9)
    strategy: Strategy = Field(default_factory=Strategy)
    approved: bool = False
    mode: Literal['baseline', 'live', 'replay'] = 'baseline'
    provider: Literal['openai', 'anthropic', 'gemini', 'deepseek', 'qwen', 'kimi', 'glm', 'doubao'] = 'openai'
    model: str = Field(default='gpt-6-luna', min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9._:/-]+$')
    use_images: bool = True
    use_tools: bool = True
    review_enabled: bool = True
    max_requests: int = Field(default=150, ge=1, le=1000)
    max_output_tokens: int = Field(default=4096, ge=512, le=16384)
    budget_usd: float = Field(default=2, gt=0, le=100)
    input_rate: float = Field(default=.1, ge=0, le=1000)
    output_rate: float = Field(default=.5, ge=0, le=1000)
    price_note: str = Field(default='OpenAI Luna Standard estimate 2026-11; excludes regional premiums; conservative no cache discount', max_length=500)
    paid_authorized: bool = False
    pricing_confirmed: bool = False
    capabilities_confirmed: bool = False
    budget_scope: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    reuse_responses_from: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    replay_of: str | None = None
    _dates = field_validator('start', 'end')(iso)

    @field_validator('symbols')
    @classmethod
    def supported(cls, v):
        if len(set(v)) != len(v) or not set(v) <= set(SYMBOLS):
            raise ValueError('Select distinct instruments from the frozen basket')
        return sorted(v)

    @model_validator(mode='after')
    def interval(self):
        if self.start > self.end:
            raise ValueError('Start must not be after end')
        if self.mode == 'live' and (not self.approved or not self.paid_authorized):
            raise ValueError('Live inference requires explicit method and cost approval')
        if self.mode == 'replay' and not self.replay_of:
            raise ValueError('Replay source required')
        return self


Verdict = Literal['pass', 'fail', 'insufficient_evidence']


class Check(Strict):
    name: Literal['cup', 'handle', 'coherence']
    verdict: Verdict
    reason: str = Field(min_length=1, max_length=1500)
    start_date: str
    end_date: str
    _dates = field_validator('start_date', 'end_date')(iso)


class Anchors(Strict):
    left_rim: str
    right_rim: str
    _dates = field_validator('left_rim', 'right_rim')(iso)


class Decision(Strict):
    """Historical v1 receipt reader; new inference uses CandidateBatch only."""
    verdict: Verdict
    checks: list[Check] = Field(min_length=3, max_length=3)
    anchors: Anchors | None
    evidence: str = Field(min_length=1, max_length=3000)

    @model_validator(mode='after')
    def consistent(self):
        if {c.name for c in self.checks} != {'cup', 'handle', 'coherence'}:
            raise ValueError('Exactly one check per rubric item required')
        verdicts = [c.verdict for c in self.checks]
        expected = 'fail' if 'fail' in verdicts else ('insufficient_evidence' if 'insufficient_evidence' in verdicts else 'pass')
        if self.verdict != expected or (self.verdict == 'pass' and self.anchors is None):
            raise ValueError('Overall verdict inconsistent with checks/anchors')
        return self


class CandidateDecision(Strict):
    candidate_id: str = Field(min_length=1, max_length=80)
    verdict: Verdict
    checks: list[Check] = Field(min_length=3, max_length=3)
    evidence: str = Field(min_length=1, max_length=3000)
    missing_information: list[str] = Field(max_length=5)

    @model_validator(mode='after')
    def consistent(self):
        if {c.name for c in self.checks} != {'cup','handle','coherence'}:
            raise ValueError('Exactly one check per rubric item required')
        values=[c.verdict for c in self.checks]
        expected='fail' if 'fail' in values else ('insufficient_evidence' if 'insufficient_evidence' in values else 'pass')
        if self.verdict!=expected:
            raise ValueError('Overall verdict inconsistent with checks')
        return self


class CandidateBatch(Strict):
    assessments: list[CandidateDecision] = Field(min_length=1,max_length=3)

    @classmethod
    def parse_reply(cls, text):
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f'Duplicate JSON key: {key}')
                result[key] = value
            return result
        obj = json.loads(text, object_pairs_hook=unique_object)
        if isinstance(obj, dict) and isinstance(obj.get('assessments'), dict):
            for key, value in obj['assessments'].items():
                if not isinstance(value, dict) or value.get('candidate_id') != key:
                    raise ValueError(f'Assessment key/ID mismatch: {key}')
            obj['assessments'] = list(obj['assessments'].values())
        # Archived array receipts remain readable; new wire schemas require keyed objects.
        return cls.model_validate(obj)
