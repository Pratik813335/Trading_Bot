"""
engine/session_strategy_engine.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Session-Aware Strategy Engine.

Applies session-specific trading rules deeply implementing the Top 5 Forex Strategies:
  - Trend Following (EMA Crossover + ADX > 25)
  - Scalping (Bollinger Band Squeeze + Stochastic)
  - Range Trading (S/R Bounce + RSI + ADX < 20)
  - Breakout Trading (S/R Breakout + Volume Spike)
  - Carry Trade (Interest Rate Differential)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from engine.session_engine import SessionEngine, SessionState
from config import MIN_CONFIRMATION_CONFIDENCE


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class SessionSignal:
    pair: str
    session: str                   # Asian | London | New York | Overlap | …
    strategy_used: str             # Trend Following | Scalping | Range Trading | Breakout Trading | Carry Trade | WAIT
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    rr_ratio: float
    confidence: int                # 1–100
    reasoning: str
    confluences: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trade_action: str = "WAIT"     # BUY | SELL | WAIT
    pip_size: float = 0.0001
    asian_range_high: float | None = None
    asian_range_low: float | None = None
    session_color: str = "#64748b"
    session_emoji: str = "⏳"
    is_actionable: bool = False    # True only if confluences pass and confidence >= MIN_CONFIRMATION_CONFIDENCE
    logged_at: str = ""


# ---------------------------------------------------------------------------
# Helper function
# ---------------------------------------------------------------------------

def _atr_pips(candles: pd.DataFrame, pip_size: float, n: int = 14) -> float:
    try:
        return float(candles["atr14"].iloc[-1]) / pip_size
    except Exception:
        highs = candles["high"].tail(n)
        lows = candles["low"].tail(n)
        return float((highs - lows).mean()) / pip_size


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class SessionStrategyEngine:
    """
    Generates session-aware trading signals using rules specific to each session.
    Supports manual strategy override and deep logic for the Top 5 strategies.
    """

    def __init__(self):
        self.session_engine = SessionEngine()

    def analyze(
        self,
        session: SessionState,
        symbol: str,
        candles: pd.DataFrame,
        indicators: dict[str, Any],
        zones: list[Any],
        structure: Any | None = None,
        forced_strategy: str | None = None,
    ) -> SessionSignal:
        """
        Route to the correct strategy and return a SessionSignal.
        """
        pip_size = self.session_engine.get_pip_size(symbol, candles)

        # Compute Asian range for dashboard reporting
        ar_high, ar_low, ar_pips = self.session_engine.compute_asian_range(candles, pip_size=pip_size)

        # Run forced strategy or session-based strategy
        if forced_strategy == "Trend Following":
            sig = self._trend_following_strategy(session, symbol, candles, indicators, zones, pip_size)
        elif forced_strategy == "Quick Scalper":
            sig = self._scalping_strategy(session, symbol, candles, indicators, zones, pip_size)
        elif forced_strategy == "Range Trader":
            sig = self._range_trading_strategy(session, symbol, candles, indicators, zones, pip_size)
        elif forced_strategy == "Breakout Trader":
            sig = self._breakout_strategy(session, symbol, candles, indicators, zones, pip_size)
        elif forced_strategy == "Carry Trader":
            sig = self._carry_trade_strategy(session, symbol, candles, indicators, zones, pip_size)
        else:
            # Default Session routing
            if session.name == "Asian":
                sig = self._range_trading_strategy(session, symbol, candles, indicators, zones, pip_size)
            elif session.name == "London":
                sig = self._breakout_strategy(session, symbol, candles, indicators, zones, pip_size)
            elif session.name == "New York":
                sig = self._trend_following_strategy(session, symbol, candles, indicators, zones, pip_size)
            elif session.name == "Overlap":
                # Evaluate both Breakout and Trend, select highest confidence
                sig_breakout = self._breakout_strategy(session, symbol, candles, indicators, zones, pip_size)
                sig_trend = self._trend_following_strategy(session, symbol, candles, indicators, zones, pip_size)
                sig = sig_breakout if sig_breakout.confidence >= sig_trend.confidence else sig_trend
            else:
                sig = self._default_wait(session, symbol, candles, pip_size, ar_high, ar_low)

        sig.asian_range_high = ar_high
        sig.asian_range_low = ar_low
        sig.session_color = session.color
        sig.session_emoji = session.emoji
        sig.logged_at = datetime.now(timezone.utc).isoformat()
        return sig

    # ------------------------------------------------------------------
    # Strategy 1: Trend Following
    # ------------------------------------------------------------------

    def _trend_following_strategy(
        self, session, symbol, candles, indicators, zones, pip_size
    ) -> SessionSignal:
        price = float(candles["close"].iloc[-1])
        atr = _atr_pips(candles, pip_size)
        atr_price = atr * pip_size
        confluences: list[str] = []
        warnings: list[str] = []

        ema50 = indicators.get("ema50") or 0.0
        ema200 = indicators.get("ema200") or 0.0
        adx_val = indicators.get("adx14") or 0.0

        if not ema50 or not ema200:
            return self._default_wait(session, symbol, candles, pip_size, None, None, ["EMA50/200 unavailable for Trend Following"])

        trend_bullish = ema50 > ema200
        trend_bearish = ema50 < ema200

        # Crossover checking in the last 15 candles
        crossover_buy = False
        crossover_sell = False
        for i in range(1, min(16, len(candles))):
            prev = candles.iloc[-i-1]
            curr = candles.iloc[-i]
            if prev["ema50"] <= prev["ema200"] and curr["ema50"] > curr["ema200"]:
                crossover_buy = True
                break
            if prev["ema50"] >= prev["ema200"] and curr["ema50"] < curr["ema200"]:
                crossover_sell = True
                break

        direction = "WAIT"
        if trend_bullish:
            direction = "BUY"
            confluences.append("EMA50 > EMA200: Bullish trend alignment")
            if crossover_buy:
                confluences.append("Recent Bullish EMA Crossover detected (within 15 bars)")
        elif trend_bearish:
            direction = "SELL"
            confluences.append("EMA50 < EMA200: Bearish trend alignment")
            if crossover_sell:
                confluences.append("Recent Bearish EMA Crossover detected (within 15 bars)")

        if adx_val > 25:
            confluences.append(f"ADX {adx_val:.1f} > 25: Strong trend confirmed")
        else:
            warnings.append(f"ADX {adx_val:.1f} <= 25: Weak trend, breakout/ranging risk exists")

        # Pullback validation (price close to 50 EMA)
        near_ema = abs(price - ema50) <= atr_price * 1.8
        if near_ema:
            confluences.append("Price is testing or pulled back near the 50 EMA")

        n_conf = len(confluences)
        confidence = min(98, 40 + n_conf * 15)
        is_actionable = n_conf >= 2 and direction != "WAIT" and adx_val > 25

        if direction == "BUY":
            entry = price
            sl = min(ema200 - atr_price * 0.5, price - atr_price * 2.0)
            tp1 = entry + abs(entry - sl) * 1.5
            tp2 = entry + abs(entry - sl) * 2.5
            tp3 = entry + abs(entry - sl) * 3.5
            reason = f"Trend Following BUY (ADX: {adx_val:.1f})"
        elif direction == "SELL":
            entry = price
            sl = max(ema200 + atr_price * 0.5, price + atr_price * 2.0)
            tp1 = entry - abs(sl - entry) * 1.5
            tp2 = entry - abs(sl - entry) * 2.5
            tp3 = entry - abs(sl - entry) * 3.5
            reason = f"Trend Following SELL (ADX: {adx_val:.1f})"
        else:
            return self._default_wait(session, symbol, candles, pip_size, None, None, ["No clear trend alignment"])

        rr = round(abs(tp1 - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0.0

        if not is_actionable:
            confidence = min(68, confidence)
            warnings.append("Trend confirmation filters (ADX > 25) not fully met")

        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used="Trend Following",
            entry_price=round(entry, 5),
            stop_loss=round(sl, 5),
            take_profit_1=round(tp1, 5),
            take_profit_2=round(tp2, 5),
            take_profit_3=round(tp3, 5),
            rr_ratio=rr,
            confidence=confidence,
            reasoning=reason,
            confluences=confluences,
            warnings=warnings,
            trade_action=direction if (direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE) else "WAIT",
            pip_size=pip_size,
            is_actionable=bool(direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE),
        )

    # ------------------------------------------------------------------
    # Strategy 2: Scalping
    # ------------------------------------------------------------------

    def _scalping_strategy(
        self, session, symbol, candles, indicators, zones, pip_size
    ) -> SessionSignal:
        price = float(candles["close"].iloc[-1])
        atr = _atr_pips(candles, pip_size)
        atr_price = atr * pip_size
        confluences: list[str] = []
        warnings: list[str] = []

        bb_upper = indicators.get("bb_upper") or 0.0
        bb_lower = indicators.get("bb_lower") or 0.0
        bb_width = indicators.get("bb_width") or 0.0
        stoch_k = indicators.get("stoch_k") or 50.0
        stoch_d = indicators.get("stoch_d") or 50.0

        if not bb_upper or not bb_lower:
            return self._default_wait(session, symbol, candles, pip_size, None, None, ["BB bands unavailable for Scalping"])

        # BB Width SMA for squeeze check
        bb_width_sma = candles["bb_width"].rolling(20).mean().iloc[-1] if len(candles) >= 20 else bb_width
        is_squeeze = bb_width <= bb_width_sma * 1.05

        if is_squeeze:
            confluences.append(f"Bollinger Band Squeeze (width {bb_width:.4f} <= SMA {bb_width_sma:.4f})")
        else:
            warnings.append("Bollinger Bands not in a squeeze zone")

        prev_k = candles["stoch_k"].iloc[-2]
        prev_d = candles["stoch_d"].iloc[-2]

        stoch_buy = (prev_k < prev_d) and (stoch_k >= stoch_d) and (stoch_k < 25)
        stoch_sell = (prev_k > prev_d) and (stoch_k <= stoch_d) and (stoch_k > 75)

        direction = "WAIT"
        if stoch_buy:
            direction = "BUY"
            confluences.append(f"Stochastic bullish cross oversold (K: {stoch_k:.1f}, D: {stoch_d:.1f})")
        elif stoch_sell:
            direction = "SELL"
            confluences.append(f"Stochastic bearish cross overbought (K: {stoch_k:.1f}, D: {stoch_d:.1f})")
        else:
            warnings.append("No oversold/overbought Stochastic crossover")

        n_conf = len(confluences)
        confidence = min(95, 35 + n_conf * 20)
        is_actionable = n_conf >= 2 and direction != "WAIT"

        # Scalper targets
        pip_target_sl = 8.0
        pip_target_tp1 = 10.0

        if direction == "BUY":
            entry = price
            sl = price - pip_target_sl * pip_size
            tp1 = price + pip_target_tp1 * pip_size
            tp2 = bb_upper
            tp3 = price + (bb_upper - price) * 1.5
            reason = "Quick Scalp BUY (BB Squeeze + Stochastic oversold)"
        elif direction == "SELL":
            entry = price
            sl = price + pip_target_sl * pip_size
            tp1 = price - pip_target_tp1 * pip_size
            tp2 = bb_lower
            tp3 = price - (price - bb_lower) * 1.5
            reason = "Quick Scalp SELL (BB Squeeze + Stochastic overbought)"
        else:
            return self._default_wait(session, symbol, candles, pip_size, None, None, ["No scalp triggers met"])

        rr = round(abs(tp1 - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0.0

        if not is_actionable:
            confidence = min(68, confidence)
            warnings.append("Scalping confluences (Squeeze & Stochastic) not fully aligned")

        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used="Scalping",
            entry_price=round(entry, 5),
            stop_loss=round(sl, 5),
            take_profit_1=round(tp1, 5),
            take_profit_2=round(tp2, 5),
            take_profit_3=round(tp3, 5),
            rr_ratio=rr,
            confidence=confidence,
            reasoning=reason,
            confluences=confluences,
            warnings=warnings,
            trade_action=direction if (direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE) else "WAIT",
            pip_size=pip_size,
            is_actionable=bool(direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE),
        )

    # ------------------------------------------------------------------
    # Strategy 3: Range Trading
    # ------------------------------------------------------------------

    def _range_trading_strategy(
        self, session, symbol, candles, indicators, zones, pip_size
    ) -> SessionSignal:
        price = float(candles["close"].iloc[-1])
        atr = _atr_pips(candles, pip_size)
        atr_price = atr * pip_size
        confluences: list[str] = []
        warnings: list[str] = []

        rsi_val = indicators.get("rsi14") or 50.0
        adx_val = indicators.get("adx14") or 0.0

        # Sort by proximity to current price to get closest S/R zones
        zone_sups = sorted([z for z in zones if z.type == "support"], key=lambda z: abs(price - z.top))
        zone_res = sorted([z for z in zones if z.type == "resistance"], key=lambda z: abs(price - z.bottom))

        closest_support = zone_sups[0].top if zone_sups else None
        closest_resistance = zone_res[0].bottom if zone_res else None

        if closest_support is None or closest_resistance is None:
            return self._default_wait(session, symbol, candles, pip_size, None, None, ["Missing valid S/R zones for Range strategy"])

        range_size = closest_resistance - closest_support
        at_support = -5 * pip_size <= (price - closest_support) <= range_size * 0.20
        at_resistance = -5 * pip_size <= (closest_resistance - price) <= range_size * 0.20

        direction = "WAIT"
        if at_support:
            direction = "BUY"
            confluences.append(f"Price is near range support {closest_support:.5f}")
            if rsi_val < 35:
                confluences.append(f"RSI {rsi_val:.1f} confirms oversold conditions")
            else:
                warnings.append(f"RSI {rsi_val:.1f} is not oversold at support")
        elif at_resistance:
            direction = "SELL"
            confluences.append(f"Price is near range resistance {closest_resistance:.5f}")
            if rsi_val > 65:
                confluences.append(f"RSI {rsi_val:.1f} confirms overbought conditions")
            else:
                warnings.append(f"RSI {rsi_val:.1f} is not overbought at resistance")

        if adx_val < 20:
            confluences.append(f"ADX {adx_val:.1f} < 20: Sideways range confirmed")
        else:
            warnings.append(f"ADX {adx_val:.1f} >= 20: Market shows trending characteristics")

        n_conf = len(confluences)
        confidence = min(96, 30 + n_conf * 22)
        is_actionable = n_conf >= 2 and direction != "WAIT" and adx_val < 20

        if direction == "BUY":
            entry = price
            sl = closest_support - 15 * pip_size
            if sl >= entry:
                sl = entry - 15 * pip_size
            tp1 = closest_support + range_size * 0.5
            tp2 = closest_resistance - atr_price * 0.5
            tp3 = closest_resistance
            reason = "Range Support BUY Bounce"
        elif direction == "SELL":
            entry = price
            sl = closest_resistance + 15 * pip_size
            if sl <= entry:
                sl = entry + 15 * pip_size
            tp1 = closest_resistance - range_size * 0.5
            tp2 = closest_support + atr_price * 0.5
            tp3 = closest_support
            reason = "Range Resistance SELL Reject"
        else:
            return self._default_wait(session, symbol, candles, pip_size, closest_resistance, closest_support, ["Price in middle of range"])

        rr = round(abs(tp1 - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0.0

        if not is_actionable:
            confidence = min(68, confidence)
            warnings.append("Range setups require flat trend (ADX < 20)")

        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used="Range Trading",
            entry_price=round(entry, 5),
            stop_loss=round(sl, 5),
            take_profit_1=round(tp1, 5),
            take_profit_2=round(tp2, 5),
            take_profit_3=round(tp3, 5),
            rr_ratio=rr,
            confidence=confidence,
            reasoning=reason,
            confluences=confluences,
            warnings=warnings,
            trade_action=direction if (direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE) else "WAIT",
            pip_size=pip_size,
            is_actionable=bool(direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE),
        )

    # ------------------------------------------------------------------
    # Strategy 4: Breakout Trading
    # ------------------------------------------------------------------

    def _breakout_strategy(
        self, session, symbol, candles, indicators, zones, pip_size
    ) -> SessionSignal:
        price = float(candles["close"].iloc[-1])
        atr = _atr_pips(candles, pip_size)
        atr_price = atr * pip_size
        confluences: list[str] = []
        warnings: list[str] = []

        curr_volume = float(candles["volume"].iloc[-1]) if "volume" in candles.columns else 0.0
        volume_avg = indicators.get("volume_avg") or 1.0

        # Sort by proximity to current price to get closest boundaries
        zone_sups = sorted([z for z in zones if z.type == "support"], key=lambda z: abs(price - z.bottom))
        zone_res = sorted([z for z in zones if z.type == "resistance"], key=lambda z: abs(price - z.top))

        closest_support = zone_sups[0].bottom if zone_sups else None
        closest_resistance = zone_res[0].top if zone_res else None

        if closest_support is None or closest_resistance is None:
            return self._default_wait(session, symbol, candles, pip_size, None, None, ["Missing valid S/R boundaries for Breakout"])

        # Check if price has broken out and is still within entry distance (1.8 * ATR) to avoid late chases
        broke_above = price > closest_resistance and (price - closest_resistance) <= atr_price * 1.8
        broke_below = price < closest_support and (closest_support - price) <= atr_price * 1.8

        direction = "WAIT"
        if broke_above:
            direction = "BUY"
            confluences.append(f"Price broke above key resistance level {closest_resistance:.5f}")
        elif broke_below:
            direction = "SELL"
            confluences.append(f"Price broke below key support level {closest_support:.5f}")

        # Volume spike filter
        if curr_volume >= volume_avg * 1.4:
            confluences.append(f"Volume spike confirmed ({curr_volume:.0f} > 1.4x avg {volume_avg:.0f})")
        else:
            warnings.append(f"No volume spike detected (Vol: {curr_volume:.0f} vs Avg: {volume_avg:.0f})")

        n_conf = len(confluences)
        confidence = min(96, 30 + n_conf * 20)
        is_actionable = n_conf >= 2 and direction != "WAIT"

        if direction == "BUY":
            entry = price
            sl = closest_resistance - atr_price * 0.8
            tp1 = entry + abs(entry - sl) * 2.0
            tp2 = entry + abs(entry - sl) * 3.5
            tp3 = entry + abs(entry - sl) * 5.0
            reason = "Resistance Breakout BUY"
        elif direction == "SELL":
            entry = price
            sl = closest_support + atr_price * 0.8
            tp1 = entry - abs(sl - entry) * 2.0
            tp2 = entry - abs(sl - entry) * 3.5
            tp3 = entry - abs(sl - entry) * 5.0
            reason = "Support Breakdown SELL"
        else:
            return self._default_wait(session, symbol, candles, pip_size, closest_resistance, closest_support, ["Price remains within range"])

        rr = round(abs(tp1 - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0.0

        if not is_actionable:
            confidence = min(68, confidence)
            warnings.append("Breakout setups require a clear volume spike to reduce fakeouts")

        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used="Breakout Trading",
            entry_price=round(entry, 5),
            stop_loss=round(sl, 5),
            take_profit_1=round(tp1, 5),
            take_profit_2=round(tp2, 5),
            take_profit_3=round(tp3, 5),
            rr_ratio=rr,
            confidence=confidence,
            reasoning=reason,
            confluences=confluences,
            warnings=warnings,
            trade_action=direction if (direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE) else "WAIT",
            pip_size=pip_size,
            is_actionable=bool(direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE),
        )

    # ------------------------------------------------------------------
    # Strategy 5: Carry Trade
    # ------------------------------------------------------------------

    def _carry_trade_strategy(
        self, session, symbol, candles, indicators, zones, pip_size
    ) -> SessionSignal:
        from config import CURRENCY_INTEREST_RATES
        price = float(candles["close"].iloc[-1])
        atr = _atr_pips(candles, pip_size)
        atr_price = atr * pip_size
        confluences: list[str] = []
        warnings: list[str] = []

        base = symbol[:3].upper()
        quote = symbol[3:].upper() if len(symbol) >= 6 else ""

        base_rate = CURRENCY_INTEREST_RATES.get(base, 0.0)
        quote_rate = CURRENCY_INTEREST_RATES.get(quote, 0.0)
        interest_diff = base_rate - quote_rate

        # Filter out flat interest differentials
        if abs(interest_diff) < 1.5:
            return self._default_wait(session, symbol, candles, pip_size, None, None, [f"Interest differential too flat ({interest_diff:+.2f}%)"])

        # Long-term trend check
        ema200 = indicators.get("ema200") or price
        trend_aligned_long = price > ema200
        trend_aligned_short = price < ema200

        # ATR Volatility check
        atr_sma = candles["atr14"].rolling(50).mean().iloc[-1] if len(candles) >= 50 else candles["atr14"].mean()
        curr_atr = candles["atr14"].iloc[-1]
        is_high_volatility = curr_atr > atr_sma * 1.75

        direction = "WAIT"
        if interest_diff >= 1.5:
            if trend_aligned_long:
                direction = "BUY"
                confluences.append(f"Yield favors Long: {base} ({base_rate}%) > {quote} ({quote_rate}%)")
                confluences.append("Long-term market trend (Price > EMA200) aligns with carry direction")
            else:
                warnings.append("Yield favors Long, but technical trend is bearish (Price < EMA200)")
        elif interest_diff <= -1.5:
            if trend_aligned_short:
                direction = "SELL"
                confluences.append(f"Yield favors Short: {quote} ({quote_rate}%) > {base} ({base_rate}%)")
                confluences.append("Long-term market trend (Price < EMA200) aligns with carry direction")
            else:
                warnings.append("Yield favors Short, but technical trend is bullish (Price > EMA200)")

        if is_high_volatility:
            warnings.append(f"High ATR volatility ({curr_atr:.5f} > SMA: {atr_sma * 1.75:.5f}) - Carry trade blocked")
        else:
            confluences.append("Stable volatility regime (no risk-off panic detected)")

        n_conf = len(confluences)
        confidence = min(95, 30 + n_conf * 22)
        is_actionable = n_conf >= 3 and direction != "WAIT" and not is_high_volatility

        if direction == "BUY":
            entry = price
            sl = price - atr_price * 3.5
            tp1 = price + abs(price - sl) * 2.5
            tp2 = price + abs(price - sl) * 4.0
            tp3 = price + abs(price - sl) * 5.5
            reason = f"Carry Trade BUY (Interest diff: {interest_diff:+.2f}%)"
        elif direction == "SELL":
            entry = price
            sl = price + atr_price * 3.5
            tp1 = price - abs(sl - price) * 2.5
            tp2 = price - abs(sl - price) * 4.0
            tp3 = price - abs(sl - price) * 5.5
            reason = f"Carry Trade SELL (Interest diff: {interest_diff:+.2f}%)"
        else:
            return self._default_wait(session, symbol, candles, pip_size, None, None, ["Yield favors trade direction, but trend is contrary"])

        rr = round(abs(tp1 - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0.0

        if not is_actionable:
            confidence = min(68, confidence)
            warnings.append("Carry Trade requires Trend Alignment and Low Volatility (ATR < 1.75x average)")

        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used="Carry Trade",
            entry_price=round(entry, 5),
            stop_loss=round(sl, 5),
            take_profit_1=round(tp1, 5),
            take_profit_2=round(tp2, 5),
            take_profit_3=round(tp3, 5),
            rr_ratio=rr,
            confidence=confidence,
            reasoning=reason,
            confluences=confluences,
            warnings=warnings,
            trade_action=direction if (direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE) else "WAIT",
            pip_size=pip_size,
            is_actionable=bool(direction != "WAIT" and confidence >= MIN_CONFIRMATION_CONFIDENCE),
        )

    # ------------------------------------------------------------------
    # Default WAIT
    # ------------------------------------------------------------------

    def _default_wait(
        self,
        session: SessionState,
        symbol: str,
        candles: pd.DataFrame,
        pip_size: float,
        ar_high: float | None,
        ar_low: float | None,
        extra_warnings: list[str] | None = None,
        confluences: list[str] | None = None,
    ) -> SessionSignal:
        price = float(candles["close"].iloc[-1]) if not candles.empty else 0.0
        warnings = extra_warnings or []
        warnings.insert(0, f"Standing by — no high-probability setup detected for {session.name}")
        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used="WAIT",
            entry_price=price,
            stop_loss=0.0,
            take_profit_1=0.0,
            take_profit_2=0.0,
            take_profit_3=0.0,
            rr_ratio=0.0,
            confidence=0,
            reasoning=f"Standing by in {session.name} session",
            confluences=confluences or [],
            warnings=warnings,
            trade_action="WAIT",
            pip_size=pip_size,
            asian_range_high=ar_high,
            asian_range_low=ar_low,
            is_actionable=False,
        )
