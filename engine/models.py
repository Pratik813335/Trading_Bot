from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FeedMetadata:
    symbol: str
    timeframe: str
    source: str
    provider: str
    provider_symbol: str
    fetched_at: datetime
    latency_seconds: float
    cache_status: str = "fresh"
    source_note: str = ""
    total_bars: int = 0


@dataclass
class SyncStatus:
    provider: str
    timeframe: str
    total_bars: int
    matched: int
    mismatch: int
    latency_ms: float
    chart_source: str
    analysis_source: str
    match_percentage: float
    missing_candles: int
    data_age_seconds: float
    ohlc_diff: float = 0.0
    checks: dict[str, str] = field(default_factory=dict)
    warning: str = ""


@dataclass
class StructureState:
    trend: str
    phase: str
    strength: float
    hh: list[float] = field(default_factory=list)
    hl: list[float] = field(default_factory=list)
    lh: list[float] = field(default_factory=list)
    ll: list[float] = field(default_factory=list)
    swing_points: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    imbalances: list[dict[str, Any]] = field(default_factory=list)
    order_blocks: list[dict[str, Any]] = field(default_factory=list)
    bos: str | None = None
    choch: str | None = None
    liquidity_sweep: str | None = None
    breakout: bool = False
    pullback: bool = False



@dataclass
class Zone:
    type: str
    top: float
    bottom: float
    strength: float
    touches: int
    htf_aligned: bool
    volume_validated: bool


@dataclass
class SignalDecision:
    symbol: str
    timeframe: str
    feed_source: str
    candle_timestamp: str
    signal: str
    confidence: float
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    rr_ratio: float
    reasons: list[str]
    invalidation: str
    indicators: dict[str, float | str]
    structure: dict[str, Any]
    chart_sync: float
    warnings: list[str] = field(default_factory=list)
    confidence_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class AnalysisBundle:
    candles: Any
    metadata: FeedMetadata
    sync: SyncStatus
    structure: StructureState
    zones: list[Zone]
    indicators: dict[str, float | str]
    signal: SignalDecision
    ai_explanation: dict[str, Any]
    chart_payload: dict[str, Any]
    analysis_contract: dict[str, Any]
    trade_payload: dict[str, Any]
    news_signals: list[Any] = field(default_factory=list)   # list[NewsSignal]
    session_signal: Any | None = None                        # SessionSignal | None
    mtf_analysis: dict[str, Any] = field(default_factory=dict)


@dataclass
class EconomicEvent:
    event_name: str
    currency: str
    impact_level: str                   # LOW | MEDIUM | HIGH
    category: str                       # Interest Rate | CPI | GDP | Employment | ...
    publication_time: str               # ISO-8601 UTC
    actual: float | None = None
    forecast: float | None = None
    previous: float | None = None
    affected_pairs: list[str] = field(default_factory=list)
    source: str = "ForexFactory"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class NewsSignal:
    event_name: str
    pair: str
    impact: str                         # LOW | MEDIUM | HIGH
    sentiment: str                      # BULLISH | BEARISH | NEUTRAL
    confidence: int                     # 0-100
    trade_action: str                   # BUY | SELL | WAIT
    entry_allowed: bool
    holding_minutes: int
    risk: str                           # LOW | MEDIUM | HIGH
    expected_duration: str              # Immediate | Intraday | Multi-Day
    reason: str
    warnings: list[str] = field(default_factory=list)
    technical_confirmation: bool = False
    logged_at: str = ""
