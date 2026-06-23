from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
from engine.session_strategy_engine import SessionStrategyEngine
from engine.session_engine import SessionState


def build_mock_candles(rows=100, trend="bullish", squeeze=False):
    data = []
    start = datetime.now(timezone.utc) - timedelta(minutes=5 * rows)
    base_price = 1.1000
    
    for i in range(rows):
        candle_time = start + timedelta(minutes=5 * i)
        # Apply trend
        if trend == "bullish":
            price_change = 0.0002 * (i / 10.0)
        elif trend == "bearish":
            price_change = -0.0002 * (i / 10.0)
        else:
            # Range trading/flat
            price_change = 0.0001 * np.sin(i / 2.0)
            
        close = base_price + price_change
        high = close + 0.0005
        low = close - 0.0005
        
        # Volatility squeeze
        if squeeze:
            high = close + 0.0001
            low = close - 0.0001
            
        data.append({
            "timestamp": candle_time,
            "open": close - 0.0001,
            "high": high,
            "low": low,
            "close": close,
            "volume": 2000 if i != rows-1 else 4000 # volume spike on last candle
        })
        
    df = pd.DataFrame(data)
    
    # Calculate basic indicators required
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["atr14"] = 0.0010
    
    # Mock ADX
    if trend == "flat":
        df["adx14"] = 15.0
    else:
        df["adx14"] = 30.0
        
    df["bb_upper"] = df["close"] + 0.0010
    df["bb_lower"] = df["close"] - 0.0010
    df["bb_width"] = 0.0020 if not squeeze else 0.0005
    df["stoch_k"] = 20.0
    df["stoch_d"] = 20.0
    df["volume_avg"] = 2000.0
    
    return df


class MockZone:
    def __init__(self, ztype, top, bottom, strength=1.0):
        self.type = ztype
        self.top = top
        self.bottom = bottom
        self.strength = strength


def test_trend_following_buy():
    engine = SessionStrategyEngine()
    df = build_mock_candles(rows=100, trend="bullish")
    
    # Ensure EMA50 > EMA200
    df.loc[df.index[-1], "ema50"] = 1.1500
    df.loc[df.index[-1], "ema200"] = 1.1200
    df.loc[df.index[-2], "ema50"] = 1.1190
    df.loc[df.index[-2], "ema200"] = 1.1200 # crossover simulation
    
    session = SessionState(
        name="London", strategy="Breakout + Trend", volatility="HIGH",
        emoji="🇬🇧", color="#f59e0b", description="",
        pip_target_min=15, pip_target_max=50,
        allowed_strategies=[], avoid_breakouts=False, utc_hour=8
    )
    
    indicators = {
        "ema50": 1.1500,
        "ema200": 1.1200,
        "adx14": 30.0,
        "atr14": 0.0010
    }
    
    sig = engine.analyze(
        session=session,
        symbol="EURUSD",
        candles=df,
        indicators=indicators,
        zones=[],
        forced_strategy="Trend Following"
    )
    
    assert sig.strategy_used == "Trend Following"
    assert sig.trade_action in ["BUY", "WAIT"] # depends on confluences


def test_scalping_squeeze():
    engine = SessionStrategyEngine()
    df = build_mock_candles(rows=100, squeeze=True)
    
    # Simulate Stochastic crossover in oversold
    df.loc[df.index[-1], "stoch_k"] = 21.0
    df.loc[df.index[-1], "stoch_d"] = 20.0
    df.loc[df.index[-2], "stoch_k"] = 19.0
    df.loc[df.index[-2], "stoch_d"] = 20.0
    
    session = SessionState(
        name="London", strategy="", volatility="HIGH",
        emoji="", color="", description="",
        pip_target_min=15, pip_target_max=50,
        allowed_strategies=[], avoid_breakouts=False, utc_hour=8
    )
    
    indicators = {
        "bb_upper": 1.1010,
        "bb_lower": 1.0990,
        "bb_width": 0.0005,
        "stoch_k": 21.0,
        "stoch_d": 20.0,
        "atr14": 0.0010
    }
    
    sig = engine.analyze(
        session=session,
        symbol="EURUSD",
        candles=df,
        indicators=indicators,
        zones=[],
        forced_strategy="Quick Scalper"
    )
    
    assert sig.strategy_used == "Scalping"


def test_range_trading():
    engine = SessionStrategyEngine()
    df = build_mock_candles(rows=100, trend="flat")
    
    session = SessionState(
        name="Asian", strategy="", volatility="LOW",
        emoji="", color="", description="",
        pip_target_min=5, pip_target_max=15,
        allowed_strategies=[], avoid_breakouts=True, utc_hour=2
    )
    
    indicators = {
        "rsi14": 28.0,
        "adx14": 15.0,
        "atr14": 0.0010
    }
    
    zones = [
        MockZone("support", 1.1002, 1.0998, strength=3),
        MockZone("resistance", 1.1052, 1.1048, strength=3)
    ]
    
    # Force price near support
    df.loc[df.index[-1], "close"] = 1.1001
    
    sig = engine.analyze(
        session=session,
        symbol="EURUSD",
        candles=df,
        indicators=indicators,
        zones=zones,
        forced_strategy="Range Trader"
    )
    
    assert sig.strategy_used == "Range Trading"


def test_carry_trade():
    engine = SessionStrategyEngine()
    df = build_mock_candles(rows=100, trend="bullish")
    
    session = SessionState(
        name="Overlap", strategy="", volatility="HIGH",
        emoji="", color="", description="",
        pip_target_min=15, pip_target_max=50,
        allowed_strategies=[], avoid_breakouts=False, utc_hour=14
    )
    
    indicators = {
        "ema200": 1.0800,
        "atr14": 0.0010
    }
    
    # We test AUDJPY which has wide interest spread
    # Base AUD (4.35%) > Quote JPY (0.25%) -> long position
    df.loc[df.index[-1], "close"] = 95.00
    df.loc[df.index[-1], "atr14"] = 0.50
    df["atr14"] = 0.50
    
    sig = engine.analyze(
        session=session,
        symbol="AUDJPY",
        candles=df,
        indicators=indicators,
        zones=[],
        forced_strategy="Carry Trader"
    )
    
    assert sig.strategy_used == "Carry Trade"


def test_order_block_detection():
    # Detect order blocks test
    from core.market_structure import detect_order_blocks
    # Build candles simulating a bullish OB
    # Bullish OB is a bearish candle followed by a strong bullish candle
    data = []
    for i in range(10):
        data.append({
            "timestamp": datetime.now() - timedelta(minutes=5 * (10 - i)),
            "open": 1.1000,
            "high": 1.1005,
            "low": 1.0995,
            "close": 1.1002,
        })
    # Make candle at index -2 bearish
    data[-2] = {
        "timestamp": datetime.now() - timedelta(minutes=10),
        "open": 1.1000,
        "high": 1.1005,
        "low": 1.0995,
        "close": 1.0996, # bearish
    }
    # Make candle at index -1 strong bullish
    data[-1] = {
        "timestamp": datetime.now() - timedelta(minutes=5),
        "open": 1.0996,
        "high": 1.1015,
        "low": 1.0995,
        "close": 1.1012, # strong bullish
    }
    df = pd.DataFrame(data)
    obs = detect_order_blocks(df)
    assert len(obs) > 0
    assert obs[0]["type"] == "bullish_ob"


def test_structure_aware_sl():
    # Test structure aware SL
    from core.risk import build_trade_plan
    # Define zones, swings, etc.
    swings = {
        "hl": [{"price": 1.0950, "index": 5}],
        "lh": [{"price": 1.1050, "index": 5}]
    }
    sl, tp, rr = build_trade_plan(
        signal="BUY",
        price=1.1000,
        atr_value=0.0010,
        zones=[],
        fib={},
        nearest_zone=lambda zones, ztype, check_price, below=True: None,
        swings=swings
    )
    # Price is 1.1000, swing low is 1.0950
    # SL should be hl_price - atr * 0.3 = 1.0950 - 0.0003 = 1.0947
    assert sl == 1.0947
    assert tp >= 1.11325


def test_choch_scoring():
    from engine.signal_engine_v2 import SignalEngineV2
    from engine.models import StructureState, FeedMetadata, SyncStatus
    from engine.risk_engine import RiskEngine
    
    risk_engine = RiskEngine()
    engine = SignalEngineV2(risk_engine)
    
    # Setup mock structure state with bullish CHOCH
    structure_state = StructureState(
        trend="bullish",
        phase="continuation",
        strength=1.0,
        choch="bullish_choch",
        order_blocks=[]
    )
    
    df = build_mock_candles(rows=100)
    metadata = FeedMetadata("EURUSD", "5", "Yahoo", "Yahoo", "EURUSD=X", datetime.now(), 0.1)
    sync = SyncStatus("Yahoo", "5", 100, 100, 0, 100.0, "", "", 100.0, 0, 0.0)
    
    indicators = {
        "ema50": 1.1500,
        "ema200": 1.1200,
        "adx14": 30.0,
        "atr14": 0.0010,
        "rsi14": 50.0,
        "macd": 0.001,
        "macd_signal": 0.0005,
        "volume_avg": 2000.0
    }
    
    decision = engine.generate("EURUSD", "5", df, metadata, sync, indicators, structure_state, [])
    assert decision.confidence_breakdown.get("choch") == 8.0
