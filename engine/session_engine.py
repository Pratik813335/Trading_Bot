"""
engine/session_engine.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Market Session Detection Engine.

Detects the active Forex trading session based on current UTC time
and provides session-specific metadata and Asian-range computation.

Sessions (UTC):
  Asian   : 00:00 – 09:00  (low volatility, ranging)
  London  : 07:00 – 16:00  (high volatility, breakouts/trends)
  New York: 12:00 – 21:00  (high volatility, reversals/continuations)
  Overlap : 12:00 – 16:00  (London + NY, extreme volatility)
  Dead Zone: 21:00 – 00:00 (Pacific/Sydney — avoid trading)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Session window definitions (UTC hours, inclusive start, exclusive end)
# ---------------------------------------------------------------------------

_SESSION_WINDOWS: list[dict] = [
    {
        "name": "Asian",
        "start": 0,
        "end": 9,
        "strategy": "Range",
        "volatility": "LOW",
        "pip_target_min": 5,
        "pip_target_max": 15,
        "color": "#3b82f6",   # blue
        "emoji": "🌏",
        "description": "Low volatility — range trading, tight S/R, small targets",
        "allowed_strategies": ["RANGE_BUY", "RANGE_SELL"],
        "avoid_breakouts": True,
    },
    {
        "name": "London",
        "start": 7,
        "end": 16,
        "strategy": "Breakout + Trend",
        "volatility": "HIGH",
        "pip_target_min": 15,
        "pip_target_max": 50,
        "color": "#f59e0b",   # amber
        "emoji": "🇬🇧",
        "description": "High volatility — Asian range breakout, EMA trend following",
        "allowed_strategies": ["BREAKOUT_BUY", "BREAKOUT_SELL", "TREND_BUY", "TREND_SELL"],
        "avoid_breakouts": False,
    },
    {
        "name": "New York",
        "start": 12,
        "end": 21,
        "strategy": "Reversal + Continuation",
        "volatility": "HIGH",
        "pip_target_min": 20,
        "pip_target_max": 60,
        "color": "#ef4444",   # red
        "emoji": "🗽",
        "description": "High volatility — reversals, stop hunts, news momentum",
        "allowed_strategies": ["REVERSAL_BUY", "REVERSAL_SELL", "CONTINUATION_BUY", "CONTINUATION_SELL"],
        "avoid_breakouts": False,
    },
]

_OVERLAP = {
    "name": "Overlap",
    "start": 12,
    "end": 16,
    "strategy": "All Strategies",
    "volatility": "EXTREME",
    "pip_target_min": 30,
    "pip_target_max": 100,
    "color": "#8b5cf6",   # purple
    "emoji": "⚡",
    "description": "London + New York overlap — extreme volatility, best opportunities",
    "allowed_strategies": ["BREAKOUT_BUY", "BREAKOUT_SELL", "TREND_BUY", "TREND_SELL",
                           "REVERSAL_BUY", "REVERSAL_SELL", "CONTINUATION_BUY", "CONTINUATION_SELL"],
    "avoid_breakouts": False,
}

_DEAD_ZONE = {
    "name": "Dead Zone",
    "start": 21,
    "end": 24,
    "strategy": "Avoid",
    "volatility": "MINIMAL",
    "pip_target_min": 0,
    "pip_target_max": 5,
    "color": "#64748b",   # slate
    "emoji": "🌙",
    "description": "Pacific/Sydney — minimal liquidity, avoid new positions",
    "allowed_strategies": [],
    "avoid_breakouts": True,
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    name: str                      # Asian | London | New York | Overlap | Dead Zone
    strategy: str                  # strategy label
    volatility: str                # LOW | HIGH | EXTREME | MINIMAL
    emoji: str
    color: str                     # hex colour for UI
    description: str
    pip_target_min: int
    pip_target_max: int
    allowed_strategies: list[str]
    avoid_breakouts: bool
    utc_hour: int                  # current UTC hour
    active_sessions: list[str] = field(default_factory=list)   # all sessions active right now
    is_overlap: bool = False
    asian_range_high: float | None = None
    asian_range_low: float | None = None
    asian_range_pips: float | None = None


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class SessionEngine:
    """Detects the active Forex trading session and computes the Asian range."""

    def detect(self, utc_now: datetime | None = None) -> SessionState:
        """
        Returns the SessionState for the given UTC datetime (defaults to now).
        """
        if utc_now is None:
            utc_now = datetime.now(timezone.utc)
        hour = utc_now.hour

        active: list[str] = []
        for win in _SESSION_WINDOWS:
            if win["start"] <= hour < win["end"]:
                active.append(win["name"])

        is_overlap = "London" in active and "New York" in active

        if is_overlap:
            meta = _OVERLAP
        elif active:
            # Most important single session (priority: NY > London > Asian)
            priority = ["New York", "London", "Asian"]
            name = next((n for n in priority if n in active), active[0])
            meta = next(w for w in _SESSION_WINDOWS if w["name"] == name)
        elif hour >= 21:
            meta = _DEAD_ZONE
        else:
            # 09:00–12:00 UTC gap — transitional (pre-London close, pre-NY)
            meta = {
                "name": "Pre-London Close",
                "strategy": "Wait",
                "volatility": "MEDIUM",
                "emoji": "⏳",
                "color": "#94a3b8",
                "description": "Between Asian close and NY open — lower liquidity, wait for setup",
                "pip_target_min": 10,
                "pip_target_max": 30,
                "allowed_strategies": ["TREND_BUY", "TREND_SELL"],
                "avoid_breakouts": True,
            }

        return SessionState(
            name=meta["name"],
            strategy=meta["strategy"],
            volatility=meta["volatility"],
            emoji=meta["emoji"],
            color=meta["color"],
            description=meta["description"],
            pip_target_min=meta["pip_target_min"],
            pip_target_max=meta["pip_target_max"],
            allowed_strategies=meta["allowed_strategies"],
            avoid_breakouts=meta["avoid_breakouts"],
            utc_hour=hour,
            active_sessions=active,
            is_overlap=is_overlap,
        )

    def compute_asian_range(
        self,
        candles: pd.DataFrame,
        utc_now: datetime | None = None,
        pip_size: float = 0.0001,
    ) -> tuple[float | None, float | None, float | None]:
        """
        Compute the Asian session H/L/range from today's candles (00:00–09:00 UTC).
        Returns (high, low, range_pips) or (None, None, None) if no Asian candles.
        """
        if utc_now is None:
            utc_now = datetime.now(timezone.utc)

        try:
            ts = candles["timestamp"]
            if ts.dt.tz is None:
                ts = ts.dt.tz_localize("UTC")
            else:
                ts = ts.dt.tz_convert("UTC")

            today = utc_now.date()
            asian_mask = (
                (ts.dt.date == today) &
                (ts.dt.hour >= 0) &
                (ts.dt.hour < 9)
            )
            asian_candles = candles[asian_mask]
            if asian_candles.empty:
                # Fall back to last 24 candles on low-timeframe data
                last_n = min(48, len(candles))
                asian_candles = candles.tail(last_n).head(last_n // 3)

            if asian_candles.empty:
                return None, None, None

            high = float(asian_candles["high"].max())
            low = float(asian_candles["low"].min())
            rng_pips = round(abs(high - low) / pip_size, 1)
            return high, low, rng_pips
        except Exception:
            return None, None, None

    def get_pip_size(self, symbol: str, df: pd.DataFrame | None = None) -> float:
        """Return pip size for the symbol, with auto-detection if price data is provided."""
        symbol = symbol.upper()
        if df is not None and not df.empty:
            try:
                # Get the last close price
                price = float(df["close"].dropna().iloc[-1])
                # Format to a high precision, strip trailing zeros
                price_str = f"{price:.8f}".rstrip('0')
                parts = price_str.split('.')
                decimals = len(parts[1]) if len(parts) > 1 else 0
                
                # Auto-detect based on decimal places
                if decimals in [2, 3]:
                    # JPY pairs (e.g. 156.45)
                    return 0.01
                elif decimals in [1]:
                    # Gold (e.g. 2350.5)
                    return 0.1
                elif decimals >= 4:
                    # Standard Forex (e.g. 1.08545)
                    return 0.0001
            except Exception:
                pass

        # Fallback to symbol-based naming rules
        if "JPY" in symbol:
            return 0.01
        if symbol in ("XAUUSD", "GOLD"):
            return 0.1
        return 0.0001

    def build_session_timeline(self, utc_now: datetime | None = None) -> list[dict]:
        """
        Returns a list of sessions with their status for the timeline bar.
        Each dict has: name, start, end, active, color, pct_through.
        """
        if utc_now is None:
            utc_now = datetime.now(timezone.utc)
        hour = utc_now.hour
        minute = utc_now.minute
        current_decimal = hour + minute / 60.0

        timeline = []
        for win in _SESSION_WINDOWS:
            active = win["start"] <= hour < win["end"]
            if active:
                pct = (current_decimal - win["start"]) / (win["end"] - win["start"]) * 100
            else:
                pct = 0.0 if hour < win["start"] else 100.0
            timeline.append({
                "name": win["name"],
                "emoji": win["emoji"],
                "start": win["start"],
                "end": win["end"],
                "active": active,
                "color": win["color"],
                "pct_through": round(pct, 1),
                "strategy": win["strategy"],
            })
        return timeline
