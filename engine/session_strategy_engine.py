"""
engine/session_strategy_engine.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Session-Aware Strategy Engine.

Applies session-specific trading rules:
  - Asian  : Range strategy (buy support / sell resistance)
  - London : Breakout + Trend (Asian range breakout + EMA confirmation)
  - NY     : Reversal + Continuation (liquidity grabs, price action, news)
  - Overlap: All strategies — scores all and returns highest-confidence

Minimum 2 confluences required for any actionable signal.
Output: SessionSignal with mandatory output fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from engine.session_engine import SessionEngine, SessionState


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class SessionSignal:
    pair: str
    session: str                   # Asian | London | New York | Overlap | …
    strategy_used: str             # Range | Breakout | Trend | Reversal | Continuation
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
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
    is_actionable: bool = False    # True only if 2+ confluences and all gates pass
    logged_at: str = ""


# ---------------------------------------------------------------------------
# Candle pattern helpers
# ---------------------------------------------------------------------------

def _is_bullish_engulfing(candles: pd.DataFrame) -> bool:
    if len(candles) < 2:
        return False
    prev, last = candles.iloc[-2], candles.iloc[-1]
    return (
        float(prev["close"]) < float(prev["open"]) and   # prev bearish
        float(last["close"]) > float(last["open"]) and   # last bullish
        float(last["close"]) > float(prev["open"]) and
        float(last["open"]) < float(prev["close"])
    )


def _is_bearish_engulfing(candles: pd.DataFrame) -> bool:
    if len(candles) < 2:
        return False
    prev, last = candles.iloc[-2], candles.iloc[-1]
    return (
        float(prev["close"]) > float(prev["open"]) and   # prev bullish
        float(last["close"]) < float(last["open"]) and   # last bearish
        float(last["open"]) > float(prev["close"]) and
        float(last["close"]) < float(prev["open"])
    )


def _is_bullish_pin_bar(candles: pd.DataFrame) -> bool:
    if candles.empty:
        return False
    c = candles.iloc[-1]
    body = abs(float(c["close"]) - float(c["open"]))
    lower_wick = float(c["open"]) - float(c["low"]) if float(c["close"]) > float(c["open"]) else float(c["close"]) - float(c["low"])
    total_range = float(c["high"]) - float(c["low"])
    if total_range == 0:
        return False
    return lower_wick >= body * 2 and lower_wick / total_range >= 0.6


def _is_bearish_pin_bar(candles: pd.DataFrame) -> bool:
    if candles.empty:
        return False
    c = candles.iloc[-1]
    body = abs(float(c["close"]) - float(c["open"]))
    upper_wick = float(c["high"]) - float(c["close"]) if float(c["close"]) > float(c["open"]) else float(c["high"]) - float(c["open"])
    total_range = float(c["high"]) - float(c["low"])
    if total_range == 0:
        return False
    return upper_wick >= body * 2 and upper_wick / total_range >= 0.6


def _is_strong_momentum_candle(candles: pd.DataFrame, direction: str) -> bool:
    """Strong breakout candle: body >= 60% of total range."""
    if candles.empty:
        return False
    c = candles.iloc[-1]
    body = abs(float(c["close"]) - float(c["open"]))
    total = float(c["high"]) - float(c["low"])
    if total == 0:
        return False
    is_directional = (
        float(c["close"]) > float(c["open"]) if direction == "BUY"
        else float(c["close"]) < float(c["open"])
    )
    return is_directional and body / total >= 0.6


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
    Requires at least 2 confluences to produce an actionable signal.
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
    ) -> SessionSignal:
        """
        Route to the correct session strategy and return a SessionSignal.
        """
        pip_size = self.session_engine.get_pip_size(symbol)

        # Compute Asian range for all sessions (London/NY use it)
        ar_high, ar_low, ar_pips = self.session_engine.compute_asian_range(candles, pip_size=pip_size)

        if session.name == "Asian":
            sig = self._asian_strategy(session, symbol, candles, indicators, zones, pip_size, ar_high, ar_low)
        elif session.name == "London":
            sig = self._london_strategy(session, symbol, candles, indicators, zones, pip_size, ar_high, ar_low)
        elif session.name == "New York":
            sig = self._ny_strategy(session, symbol, candles, indicators, zones, pip_size, ar_high, ar_low, structure)
        elif session.name == "Overlap":
            sig = self._overlap_strategy(session, symbol, candles, indicators, zones, pip_size, ar_high, ar_low, structure)
        else:
            sig = self._default_wait(session, symbol, candles, pip_size, ar_high, ar_low)

        sig.asian_range_high = ar_high
        sig.asian_range_low = ar_low
        sig.session_color = session.color
        sig.session_emoji = session.emoji
        sig.logged_at = datetime.now(timezone.utc).isoformat()
        return sig

    # ------------------------------------------------------------------
    # Asian — Range Strategy
    # ------------------------------------------------------------------

    def _asian_strategy(
        self, session, symbol, candles, indicators, zones, pip_size, ar_high, ar_low
    ) -> SessionSignal:
        price = float(candles["close"].iloc[-1])
        atr = _atr_pips(candles, pip_size)
        confluences: list[str] = []
        warnings: list[str] = []

        # Use computed Asian range as S/R
        support = ar_low
        resistance = ar_high
        if support is None or resistance is None:
            # Fall back to zone-based S/R
            zone_sups = sorted([z for z in zones if z.type == "support"], key=lambda z: z.strength, reverse=True)
            zone_res = sorted([z for z in zones if z.type == "resistance"], key=lambda z: z.strength, reverse=True)
            support = zone_sups[0].top if zone_sups else price * 0.999
            resistance = zone_res[0].bottom if zone_res else price * 1.001

        range_size = resistance - support
        at_support = (price - support) <= range_size * 0.15
        at_resistance = (resistance - price) <= range_size * 0.15

        # Confluence 1: RSI extremes
        rsi = indicators.get("rsi14", 50.0) or 50.0
        if at_support and rsi < 45:
            confluences.append(f"RSI {rsi:.1f} — oversold near support")
        elif at_resistance and rsi > 55:
            confluences.append(f"RSI {rsi:.1f} — overbought near resistance")

        # Confluence 2: Price at key level
        if at_support:
            confluences.append(f"Price {price:.5f} near range support {support:.5f}")
        elif at_resistance:
            confluences.append(f"Price {price:.5f} near range resistance {resistance:.5f}")

        # Confluence 3: Pin bar / engulfing at level
        if at_support and _is_bullish_pin_bar(candles):
            confluences.append("Bullish pin bar at support")
        elif at_support and _is_bullish_engulfing(candles):
            confluences.append("Bullish engulfing at support")
        elif at_resistance and _is_bearish_pin_bar(candles):
            confluences.append("Bearish pin bar at resistance")
        elif at_resistance and _is_bearish_engulfing(candles):
            confluences.append("Bearish engulfing at resistance")

        # Confluence 4: EMA flat (confirms range)
        ema50 = indicators.get("ema50") or 0
        ema200 = indicators.get("ema200") or 0
        if ema50 and ema200:
            ema_spread_pct = abs(ema50 - ema200) / ema200 * 100 if ema200 else 0
            if ema_spread_pct < 0.3:
                confluences.append("EMA50/200 flat — confirming range environment")

        direction = "BUY" if at_support else ("SELL" if at_resistance else "WAIT")
        n_conf = len(confluences)
        confidence = min(95, 30 + n_conf * 18)
        is_actionable = n_conf >= 2 and direction != "WAIT"

        if direction == "BUY":
            entry = price
            sl = support - atr * pip_size * 1.5
            tp1 = resistance * 0.9
            tp2 = resistance
            strategy = "Range Buy"
            reason = f"Asian range — buying near support {support:.5f}, targeting range midpoint and resistance"
        elif direction == "SELL":
            entry = price
            sl = resistance + atr * pip_size * 1.5
            tp1 = support * 1.1
            tp2 = support
            strategy = "Range Sell"
            reason = f"Asian range — selling near resistance {resistance:.5f}, targeting range midpoint and support"
        else:
            warnings.append("Price is in the middle of the range — no edge")
            return self._default_wait(session, symbol, candles, pip_size, ar_high, ar_low,
                                       extra_warnings=warnings, confluences=confluences)

        rr = round(abs(tp1 - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0.0

        if not is_actionable:
            warnings.append(f"Only {n_conf} confluence(s) — need at least 2 to act")

        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used=strategy,
            entry_price=round(entry, 5),
            stop_loss=round(sl, 5),
            take_profit_1=round(tp1, 5),
            take_profit_2=round(tp2, 5),
            rr_ratio=rr,
            confidence=confidence,
            reasoning=reason,
            confluences=confluences,
            warnings=warnings,
            trade_action=direction if is_actionable else "WAIT",
            pip_size=pip_size,
            is_actionable=is_actionable,
        )

    # ------------------------------------------------------------------
    # London — Breakout + Trend Strategy
    # ------------------------------------------------------------------

    def _london_strategy(
        self, session, symbol, candles, indicators, zones, pip_size, ar_high, ar_low
    ) -> SessionSignal:
        price = float(candles["close"].iloc[-1])
        atr = _atr_pips(candles, pip_size)
        atr_price = atr * pip_size
        confluences: list[str] = []
        warnings: list[str] = []

        if ar_high is None or ar_low is None:
            warnings.append("Asian range unavailable — breakout strategy limited")
            return self._default_wait(session, symbol, candles, pip_size, ar_high, ar_low,
                                       extra_warnings=warnings)

        broke_above = price > ar_high
        broke_below = price < ar_low
        breakout_margin = atr_price * 0.5

        direction = "BUY" if broke_above else ("SELL" if broke_below else "WAIT")

        # Confluence 1: Asian range breakout
        if broke_above:
            confluences.append(f"Price {price:.5f} broke above Asian high {ar_high:.5f}")
        elif broke_below:
            confluences.append(f"Price {price:.5f} broke below Asian low {ar_low:.5f}")

        # Confluence 2: EMA trend alignment
        ema50 = indicators.get("ema50") or 0.0
        ema200 = indicators.get("ema200") or 0.0
        if ema50 and ema200:
            if broke_above and price > ema50 > ema200:
                confluences.append("EMA50 > EMA200 — bullish trend confirmed")
            elif broke_below and price < ema50 < ema200:
                confluences.append("EMA50 < EMA200 — bearish trend confirmed")
            else:
                warnings.append("EMA alignment does not confirm breakout direction")

        # Confluence 3: Strong momentum candle
        if direction != "WAIT" and _is_strong_momentum_candle(candles, direction):
            confluences.append("Strong momentum breakout candle (body >= 60% range)")

        # Confluence 4: RSI not extreme
        rsi = indicators.get("rsi14", 50.0) or 50.0
        if direction == "BUY" and 40 < rsi < 75:
            confluences.append(f"RSI {rsi:.1f} — momentum without overbought risk")
        elif direction == "SELL" and 25 < rsi < 60:
            confluences.append(f"RSI {rsi:.1f} — momentum without oversold risk")

        # Confluence 5: MACD
        macd = indicators.get("macd", 0.0) or 0.0
        macd_sig = indicators.get("macd_signal", 0.0) or 0.0
        if direction == "BUY" and macd > macd_sig:
            confluences.append("MACD bullish crossover — momentum supporting breakout")
        elif direction == "SELL" and macd < macd_sig:
            confluences.append("MACD bearish crossover — momentum supporting breakdown")

        n_conf = len(confluences)
        confidence = min(95, 35 + n_conf * 15)
        is_actionable = n_conf >= 2 and direction != "WAIT"

        if direction == "BUY":
            entry = ar_high + breakout_margin
            sl = ar_low - atr_price * 0.5   # Below entire Asian range
            tp1 = entry + (ar_high - ar_low) * 1.5
            tp2 = entry + (ar_high - ar_low) * 2.5
            strategy = "London Breakout Buy"
            reason = f"London breakout above Asian high {ar_high:.5f} with {n_conf} confluences"
        elif direction == "SELL":
            entry = ar_low - breakout_margin
            sl = ar_high + atr_price * 0.5
            tp1 = entry - (ar_high - ar_low) * 1.5
            tp2 = entry - (ar_high - ar_low) * 2.5
            strategy = "London Breakout Sell"
            reason = f"London breakout below Asian low {ar_low:.5f} with {n_conf} confluences"
        else:
            warnings.append(f"Price {price:.5f} inside Asian range [{ar_low:.5f}–{ar_high:.5f}] — waiting for breakout")
            return self._default_wait(session, symbol, candles, pip_size, ar_high, ar_low,
                                       extra_warnings=warnings, confluences=confluences)

        sl = max(sl, price - atr_price * 4) if direction == "BUY" else min(sl, price + atr_price * 4)
        rr = round(abs(tp1 - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0.0

        if not is_actionable:
            warnings.append(f"Only {n_conf} confluence(s) — need at least 2")

        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used=strategy,
            entry_price=round(entry, 5),
            stop_loss=round(sl, 5),
            take_profit_1=round(tp1, 5),
            take_profit_2=round(tp2, 5),
            rr_ratio=rr,
            confidence=confidence,
            reasoning=reason,
            confluences=confluences,
            warnings=warnings,
            trade_action=direction if is_actionable else "WAIT",
            pip_size=pip_size,
            is_actionable=is_actionable,
        )

    # ------------------------------------------------------------------
    # New York — Reversal + Continuation Strategy
    # ------------------------------------------------------------------

    def _ny_strategy(
        self, session, symbol, candles, indicators, zones, pip_size, ar_high, ar_low, structure
    ) -> SessionSignal:
        price = float(candles["close"].iloc[-1])
        atr = _atr_pips(candles, pip_size)
        atr_price = atr * pip_size
        confluences: list[str] = []
        warnings: list[str] = []

        ema50 = indicators.get("ema50") or 0.0
        ema200 = indicators.get("ema200") or 0.0
        rsi = indicators.get("rsi14", 50.0) or 50.0
        macd = indicators.get("macd", 0.0) or 0.0
        macd_sig = indicators.get("macd_signal", 0.0) or 0.0

        # Determine London trend direction
        london_trend = "NEUTRAL"
        if structure is not None:
            t = getattr(structure, "trend", None) or (structure.get("trend") if isinstance(structure, dict) else None)
            if t == "bullish":
                london_trend = "BULLISH"
            elif t == "bearish":
                london_trend = "BEARISH"
        elif ema50 and ema200:
            london_trend = "BULLISH" if ema50 > ema200 else "BEARISH"

        # Detect liquidity grab / stop hunt
        liq_grab_buy = False
        liq_grab_sell = False
        if structure is not None:
            ls = getattr(structure, "liquidity_sweep", None)
            if ls == "liquidity_grab_buy":
                liq_grab_buy = True
            elif ls == "liquidity_grab_sell":
                liq_grab_sell = True

        # Check price action patterns
        bull_engulf = _is_bullish_engulfing(candles)
        bear_engulf = _is_bearish_engulfing(candles)
        bull_pin = _is_bullish_pin_bar(candles)
        bear_pin = _is_bearish_pin_bar(candles)

        # Reversal mode: fade the London move
        reversal_buy = london_trend == "BEARISH" and (liq_grab_buy or bull_engulf or bull_pin)
        reversal_sell = london_trend == "BULLISH" and (liq_grab_sell or bear_engulf or bear_pin)

        # Continuation mode: ride London trend
        continuation_buy = london_trend == "BULLISH" and price > ema50 and (bull_engulf or bull_pin)
        continuation_sell = london_trend == "BEARISH" and price < ema50 and (bear_engulf or bear_pin)

        if reversal_buy:
            direction = "BUY"
            strategy = "NY Reversal Buy"
            if liq_grab_buy:
                confluences.append("Buy-side liquidity grab detected — stop hunt cleared")
            if bull_engulf:
                confluences.append("Bullish engulfing candle — reversal confirmation")
            if bull_pin:
                confluences.append("Bullish pin bar — rejection of lows")
            reason = f"NY reversal BUY — fading bearish London trend after liquidity sweep"
        elif reversal_sell:
            direction = "SELL"
            strategy = "NY Reversal Sell"
            if liq_grab_sell:
                confluences.append("Sell-side liquidity grab detected — stop hunt cleared")
            if bear_engulf:
                confluences.append("Bearish engulfing candle — reversal confirmation")
            if bear_pin:
                confluences.append("Bearish pin bar — rejection of highs")
            reason = f"NY reversal SELL — fading bullish London trend after liquidity grab"
        elif continuation_buy:
            direction = "BUY"
            strategy = "NY Continuation Buy"
            confluences.append(f"Continuing London bullish trend (EMA50 {ema50:.5f} > EMA200 {ema200:.5f})")
            if bull_engulf:
                confluences.append("Bullish engulfing — pullback complete, resuming trend")
            elif bull_pin:
                confluences.append("Bullish pin bar — pullback rejection")
            reason = f"NY continuation BUY — London trend is bullish, price pulling back into EMA"
        elif continuation_sell:
            direction = "SELL"
            strategy = "NY Continuation Sell"
            confluences.append(f"Continuing London bearish trend (EMA50 {ema50:.5f} < EMA200 {ema200:.5f})")
            if bear_engulf:
                confluences.append("Bearish engulfing — pullback complete, resuming downtrend")
            elif bear_pin:
                confluences.append("Bearish pin bar — pullback rejection")
            reason = f"NY continuation SELL — London trend is bearish, price rallying into EMA"
        else:
            warnings.append(f"No clear NY setup — London trend: {london_trend}, no confirmed pattern")
            return self._default_wait(session, symbol, candles, pip_size, ar_high, ar_low,
                                       extra_warnings=warnings)

        # RSI filter
        if direction == "BUY" and rsi < 70:
            confluences.append(f"RSI {rsi:.1f} — not overbought, room to move up")
        elif direction == "SELL" and rsi > 30:
            confluences.append(f"RSI {rsi:.1f} — not oversold, room to move down")

        # MACD filter
        if direction == "BUY" and macd > macd_sig:
            confluences.append("MACD bullish — momentum confirms direction")
        elif direction == "SELL" and macd < macd_sig:
            confluences.append("MACD bearish — momentum confirms direction")

        # Key S/R zones
        zone_sups = sorted([z for z in zones if z.type == "support"], key=lambda z: z.strength, reverse=True)
        zone_res = sorted([z for z in zones if z.type == "resistance"], key=lambda z: z.strength, reverse=True)

        if direction == "BUY":
            entry = price
            nearest_sup = zone_sups[0].top if zone_sups else price - atr_price * 1.5
            sl = nearest_sup - atr_price * 0.5
            nearest_res = zone_res[0].bottom if zone_res else price + atr_price * 3
            tp1 = nearest_res
            tp2 = nearest_res + atr_price * 2
            if zone_sups:
                confluences.append(f"Support zone at {zone_sups[0].top:.5f} as SL anchor")
        else:
            entry = price
            nearest_res = zone_res[0].bottom if zone_res else price + atr_price * 1.5
            sl = nearest_res + atr_price * 0.5
            nearest_sup = zone_sups[0].top if zone_sups else price - atr_price * 3
            tp1 = nearest_sup
            tp2 = nearest_sup - atr_price * 2
            if zone_res:
                confluences.append(f"Resistance zone at {zone_res[0].bottom:.5f} as SL anchor")

        n_conf = len(confluences)
        confidence = min(95, 40 + n_conf * 13)
        is_actionable = n_conf >= 2
        rr = round(abs(tp1 - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0.0

        if not is_actionable:
            warnings.append(f"Only {n_conf} confluence(s) — need at least 2")

        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used=strategy,
            entry_price=round(entry, 5),
            stop_loss=round(sl, 5),
            take_profit_1=round(tp1, 5),
            take_profit_2=round(tp2, 5),
            rr_ratio=rr,
            confidence=confidence,
            reasoning=reason,
            confluences=confluences,
            warnings=warnings,
            trade_action=direction if is_actionable else "WAIT",
            pip_size=pip_size,
            is_actionable=is_actionable,
        )

    # ------------------------------------------------------------------
    # Overlap — Score all strategies, return best
    # ------------------------------------------------------------------

    def _overlap_strategy(
        self, session, symbol, candles, indicators, zones, pip_size, ar_high, ar_low, structure
    ) -> SessionSignal:
        # Run all strategies under a London-like session state
        from engine.session_engine import _SESSION_WINDOWS
        london_meta = next(w for w in _SESSION_WINDOWS if w["name"] == "London")
        ny_meta = next(w for w in _SESSION_WINDOWS if w["name"] == "New York")

        from engine.session_engine import SessionState as SS
        london_state = SS(
            name="London", strategy="Breakout + Trend", volatility="HIGH",
            emoji="🇬🇧", color="#f59e0b", description="",
            pip_target_min=15, pip_target_max=50,
            allowed_strategies=london_meta["allowed_strategies"],
            avoid_breakouts=False, utc_hour=session.utc_hour,
        )
        ny_state = SS(
            name="New York", strategy="Reversal + Continuation", volatility="HIGH",
            emoji="🗽", color="#ef4444", description="",
            pip_target_min=20, pip_target_max=60,
            allowed_strategies=ny_meta["allowed_strategies"],
            avoid_breakouts=False, utc_hour=session.utc_hour,
        )

        sigs = []
        for state in (london_state, ny_state):
            try:
                if state.name == "London":
                    s = self._london_strategy(state, symbol, candles, indicators, zones, pip_size, ar_high, ar_low)
                else:
                    s = self._ny_strategy(state, symbol, candles, indicators, zones, pip_size, ar_high, ar_low, structure)
                sigs.append(s)
            except Exception:
                pass

        if not sigs:
            return self._default_wait(session, symbol, candles, pip_size, ar_high, ar_low)

        best = max(sigs, key=lambda s: s.confidence)
        # Boost confidence during overlap
        best.confidence = min(95, best.confidence + 10)
        best.session = "Overlap"
        best.session_color = session.color
        best.session_emoji = session.emoji
        best.confluences.insert(0, "Overlap session: London + NY simultaneously active — highest probability")
        return best

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
        warnings.insert(0, f"{session.name} session — no high-probability setup detected, standing by")
        return SessionSignal(
            pair=symbol,
            session=session.name,
            strategy_used="WAIT",
            entry_price=price,
            stop_loss=0.0,
            take_profit_1=0.0,
            take_profit_2=0.0,
            rr_ratio=0.0,
            confidence=0,
            reasoning=f"No actionable {session.name} session setup — waiting for confluence",
            confluences=confluences or [],
            warnings=warnings,
            trade_action="WAIT",
            pip_size=pip_size,
            asian_range_high=ar_high,
            asian_range_low=ar_low,
            is_actionable=False,
        )
