import pandas as pd
from datetime import datetime, timezone
from engine.models import EconomicEvent, NewsSignal, FeedMetadata, SyncStatus, StructureState, Zone, SignalDecision
from engine.news_intelligence_engine import NewsIntelligenceEngine
from engine.analysis_orchestrator import AnalysisOrchestrator

class DummyFeed:
    def fetch_for_currency(self, currency):
        return []

class DummyRepo:
    def is_duplicate(self, signal):
        return False
    def append(self, signal):
        pass

def test_economic_surprise_and_interpretation():
    engine = NewsIntelligenceEngine()
    
    # Positive CPI surprise (forecast: 2.0, actual: 2.5) -> BULLISH
    event = EconomicEvent(
        event_name="CPI y/y",
        currency="USD",
        category="CPI",
        impact_level="HIGH",
        publication_time="2026-06-24T12:00:00Z",
        forecast=2.0,
        actual=2.5,
        previous=1.8,
        affected_pairs=["EURUSD", "GBPUSD", "USDJPY"]
    )
    
    indicators = {"price": 1.1000, "ema50": 1.0950, "ema200": 1.0900, "rsi14": 55.0}
    signal = engine.analyze(event, "EURUSD", indicators)
    
    assert signal.surprise == 0.5
    assert signal.surprise_pct == 0.5 / 1.8
    assert signal.sentiment == "BULLISH"
    assert signal.fundamental_score > 50.0
    assert signal.risk_score >= 50.0

def test_contrarian_bias_from_rsi():
    engine = NewsIntelligenceEngine()
    
    # Overbought RSI (80) -> Crowd is Long, contrarian SSI bias is BEARISH
    event = EconomicEvent(
        event_name="FOMC Statement",
        currency="USD",
        category="Central Bank",
        impact_level="HIGH",
        publication_time="2026-06-24T12:00:00Z",
        forecast=None,
        actual=None,
        previous=None,
        affected_pairs=["EURUSD"]
    )
    
    # RSI = 80 -> Overbought. Crowd Long % = 80 - (80 - 30) * 1.5 = 5.0%
    # If crowd long pct is 5.0% <= 25.0%, contrarian bias is BULLISH
    indicators_ob = {"rsi14": 80.0}
    signal_ob = engine.analyze(event, "EURUSD", indicators_ob)
    assert signal_ob.contrarian_bias == "BULLISH"

    # Oversold RSI = 20 -> Crowd Long % = 80 - (20 - 30) * 1.5 = 95% (capped at 90%).
    # Since 90.0% >= 75.0%, contrarian bias is BEARISH
    indicators_os = {"rsi14": 20.0}
    signal_os = engine.analyze(event, "EURUSD", indicators_os)
    assert signal_os.contrarian_bias == "BEARISH"

def test_technical_fundamental_conflict_gate():
    # Setup AnalysisOrchestrator components
    orchestrator = AnalysisOrchestrator(
        market_feed=None,
        indicator_engine=None,
        structure_engine=None,
        zone_engine=None,
        signal_engine=None,
        renderer=None,
        signal_repository=None,
        forex_factory_feed=DummyFeed(),
        news_engine=NewsIntelligenceEngine(),
        news_signal_repository=DummyRepo()
    )

    # Technical Buy Signal
    signal = SignalDecision(
        symbol="EURUSD",
        timeframe="15",
        feed_source="Yahoo",
        candle_timestamp="2026-06-24T12:00:00Z",
        signal="BUY",
        confidence=70.0,
        entry=1.1000,
        stop_loss=1.0950,
        tp1=1.1100,
        tp2=1.1200,
        rr_ratio=2.0,
        reasons=[],
        invalidation="",
        indicators={"rsi14": 50.0, "adx14": 25.0},
        structure={"trend": "bullish", "bos": "none", "choch": "none"},
        chart_sync=100.0,
        warnings=[]
    )

    sync_status = SyncStatus(
        provider="Yahoo", timeframe="15", total_bars=100, matched=100, mismatch=0,
        latency_ms=10.0, chart_source="Y", analysis_source="Y", match_percentage=100.0,
        missing_candles=0, data_age_seconds=10.0
    )

    structure_state = StructureState(trend="bullish", phase="impulse", strength=1.0)
    zones = []

    # Bearish fundamental news
    news_signals = [
        NewsSignal(
            event_name="CPI Miss",
            pair="EURUSD",
            impact="HIGH",
            sentiment="BEARISH",
            trade_action="SELL",
            confidence=80,
            expected_duration="short",
            holding_minutes=60,
            risk="HIGH",
            entry_allowed=True,
            reason="Bearish Fundamental",
            warnings=[],
            technical_confirmation=False,
            logged_at="",
            surprise=-0.2,
            surprise_pct=-0.1,
            currency_strength_score=35.0,
            contrarian_bias="NEUTRAL",
            fundamental_score=20.0,
            risk_score=60.0
        )
    ]

    # Validate gates. Should trigger technical-fundamental conflict and turn signal into NO_TRADE
    orchestrator.validate_10_gates(
        signal=signal,
        sync_status=sync_status,
        structure_state=structure_state,
        indicators={"rsi14": 50.0, "adx14": 25.0},
        zones=zones,
        news_signals=news_signals,
        ai_explanation={},
        forced_strategy=None,
        session_signal=None
    )

    assert signal.signal == "NO_TRADE"
    assert any("Technical-Fundamental Conflict" in r for r in signal.reasons)


def test_confluence_gate_bypass():
    orchestrator = AnalysisOrchestrator(
        market_feed=None,
        indicator_engine=None,
        structure_engine=None,
        zone_engine=None,
        signal_engine=None,
        renderer=None,
        signal_repository=None,
        forex_factory_feed=DummyFeed(),
        news_engine=NewsIntelligenceEngine(),
        news_signal_repository=DummyRepo()
    )

    # 1. High Confidence (70.0), Low Confluence (0) -> Should Bypass G4 Fail and keep BUY
    signal_high = SignalDecision(
        symbol="EURUSD",
        timeframe="15",
        feed_source="Yahoo",
        candle_timestamp="2026-06-24T12:00:00Z",
        signal="BUY",
        confidence=70.0,
        entry=1.1000,
        stop_loss=1.0950,
        tp1=1.1100,
        tp2=1.1200,
        rr_ratio=3.0,
        reasons=[],
        invalidation="",
        indicators={"rsi14": 50.0, "adx14": 25.0},
        structure={"trend": "bullish", "bos": "none", "choch": "none"},
        chart_sync=100.0,
        warnings=[]
    )

    sync_status = SyncStatus(
        provider="Yahoo", timeframe="15", total_bars=100, matched=100, mismatch=0,
        latency_ms=10.0, chart_source="Y", analysis_source="Y", match_percentage=100.0,
        missing_candles=0, data_age_seconds=10.0
    )
    structure_state = StructureState(trend="bullish", phase="impulse", strength=1.0)

    orchestrator.validate_10_gates(
        signal=signal_high,
        sync_status=sync_status,
        structure_state=structure_state,
        indicators={"rsi14": 50.0, "adx14": 25.0},
        zones=[],
        news_signals=[],
        ai_explanation={},
        forced_strategy=None,
        session_signal=None
    )
    assert signal_high.signal == "BUY"
    assert any("G4 Warning" in warning for warning in signal_high.warnings)

    # 2. Low Confidence (50.0), Low Confluence (0) -> Should trigger G4 Fail and change signal to NO_TRADE
    signal_low = SignalDecision(
        symbol="EURUSD",
        timeframe="15",
        feed_source="Yahoo",
        candle_timestamp="2026-06-24T12:00:00Z",
        signal="BUY",
        confidence=50.0,
        entry=1.1000,
        stop_loss=1.0950,
        tp1=1.1100,
        tp2=1.1200,
        rr_ratio=3.0,
        reasons=[],
        invalidation="",
        indicators={"rsi14": 50.0, "adx14": 25.0},
        structure={"trend": "bullish", "bos": "none", "choch": "none"},
        chart_sync=100.0,
        warnings=[]
    )

    orchestrator.validate_10_gates(
        signal=signal_low,
        sync_status=sync_status,
        structure_state=structure_state,
        indicators={"rsi14": 50.0, "adx14": 25.0},
        zones=[],
        news_signals=[],
        ai_explanation={},
        forced_strategy=None,
        session_signal=None
    )
    assert signal_low.signal == "NO_TRADE"
    assert any("G4 Fail" in reason for reason in signal_low.reasons)

    # 3. High Confidence (70.0), Score Gap warning -> Should Bypass G5 Fail and keep BUY
    signal_gap_high = SignalDecision(
        symbol="EURUSD",
        timeframe="15",
        feed_source="Yahoo",
        candle_timestamp="2026-06-24T12:00:00Z",
        signal="BUY",
        confidence=70.0,
        entry=1.1000,
        stop_loss=1.0950,
        tp1=1.1100,
        tp2=1.1200,
        rr_ratio=3.0,
        reasons=[],
        invalidation="",
        indicators={"rsi14": 50.0, "adx14": 25.0},
        structure={"trend": "bullish", "bos": "none", "choch": "none"},
        chart_sync=100.0,
        warnings=["Insufficient confluence", "score gap"]
    )

    orchestrator.validate_10_gates(
        signal=signal_gap_high,
        sync_status=sync_status,
        structure_state=structure_state,
        indicators={"rsi14": 50.0, "adx14": 25.0},
        zones=[],
        news_signals=[],
        ai_explanation={},
        forced_strategy=None,
        session_signal=None
    )
    assert signal_gap_high.signal == "BUY"

    # 4. Low Confidence (50.0), Score Gap warning -> Should trigger G5 Fail and change signal to NO_TRADE
    signal_gap_low = SignalDecision(
        symbol="EURUSD",
        timeframe="15",
        feed_source="Yahoo",
        candle_timestamp="2026-06-24T12:00:00Z",
        signal="BUY",
        confidence=50.0,
        entry=1.1000,
        stop_loss=1.0950,
        tp1=1.1100,
        tp2=1.1200,
        rr_ratio=3.0,
        reasons=[],
        invalidation="",
        indicators={"rsi14": 50.0, "adx14": 25.0},
        structure={"trend": "bullish", "bos": "none", "choch": "none"},
        chart_sync=100.0,
        warnings=["Insufficient confluence", "score gap"]
    )

    orchestrator.validate_10_gates(
        signal=signal_gap_low,
        sync_status=sync_status,
        structure_state=structure_state,
        indicators={"rsi14": 50.0, "adx14": 25.0},
        zones=[],
        news_signals=[],
        ai_explanation={},
        forced_strategy=None,
        session_signal=None
    )
    assert signal_gap_low.signal == "NO_TRADE"
    assert any("G5 Fail" in reason for reason in signal_gap_low.reasons)


def test_session_actionable_gate_bypass():
    from engine.session_strategy_engine import SessionSignal
    orchestrator = AnalysisOrchestrator(
        market_feed=None,
        indicator_engine=None,
        structure_engine=None,
        zone_engine=None,
        signal_engine=None,
        renderer=None,
        signal_repository=None,
        forex_factory_feed=DummyFeed(),
        news_engine=NewsIntelligenceEngine(),
        news_signal_repository=DummyRepo()
    )

    # 1. Actionable Session Signal with R:R = 1.5 and ranging trend -> Should bypass G2 and G7
    signal_session = SignalDecision(
        symbol="EURUSD",
        timeframe="15",
        feed_source="Yahoo",
        candle_timestamp="2026-06-24T12:00:00Z",
        signal="BUY",
        confidence=70.0,
        entry=1.1000,
        stop_loss=1.0900,
        tp1=1.1150,
        tp2=1.1200,
        rr_ratio=1.5, # low R:R
        reasons=[],
        invalidation="",
        indicators={"rsi14": 50.0, "adx14": 25.0},
        structure={"trend": "range", "bos": "none", "choch": "none"}, # ranging market
        chart_sync=100.0,
        warnings=[]
    )

    sync_status = SyncStatus(
        provider="Yahoo", timeframe="15", total_bars=100, matched=100, mismatch=0,
        latency_ms=10.0, chart_source="Y", analysis_source="Y", match_percentage=100.0,
        missing_candles=0, data_age_seconds=10.0
    )
    structure_state = StructureState(trend="range", phase="consolidation", strength=1.0)

    session_sig = SessionSignal(
        pair="EURUSD",
        session="New York",
        strategy_used="Trend Following",
        entry_price=1.1000,
        stop_loss=1.0900,
        take_profit_1=1.1150,
        take_profit_2=1.1200,
        rr_ratio=1.5,
        confidence=70,
        reasoning="Session BUY",
        confluences=["EMA crossover"],
        warnings=[],
        trade_action="BUY",
        is_actionable=True
    )

    orchestrator.validate_10_gates(
        signal=signal_session,
        sync_status=sync_status,
        structure_state=structure_state,
        indicators={"rsi14": 50.0, "adx14": 25.0},
        zones=[],
        news_signals=[],
        ai_explanation={},
        forced_strategy=None,
        session_signal=session_sig
    )
    # Both G2 (ranging) and G7 (low R:R) must be bypassed, keeping the BUY signal active!
    assert signal_session.signal == "BUY"

    # 2. No session signal, same low R:R and ranging trend -> Should fail G2 and G7, changing signal to NO_TRADE
    signal_no_session = SignalDecision(
        symbol="EURUSD",
        timeframe="15",
        feed_source="Yahoo",
        candle_timestamp="2026-06-24T12:00:00Z",
        signal="BUY",
        confidence=70.0,
        entry=1.1000,
        stop_loss=1.0900,
        tp1=1.1150,
        tp2=1.1200,
        rr_ratio=1.5,
        reasons=[],
        invalidation="",
        indicators={"rsi14": 50.0, "adx14": 25.0},
        structure={"trend": "range", "bos": "none", "choch": "none"},
        chart_sync=100.0,
        warnings=[]
    )

    orchestrator.validate_10_gates(
        signal=signal_no_session,
        sync_status=sync_status,
        structure_state=structure_state,
        indicators={"rsi14": 50.0, "adx14": 25.0},
        zones=[],
        news_signals=[],
        ai_explanation={},
        forced_strategy=None,
        session_signal=None
    )
    assert signal_no_session.signal == "NO_TRADE"
    assert any("G2 Fail" in reason for reason in signal_no_session.reasons)
    assert any("G7 Fail" in reason for reason in signal_no_session.reasons)

