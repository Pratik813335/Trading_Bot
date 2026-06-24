"""
engine/news_intelligence_engine.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Forex Macro News Intelligence Engine — 6-step probability-based pipeline.

Transforms economic events into structured NewsSignal outputs.
This engine does NOT predict markets and does NOT execute trades.
It converts forex news into probability-based trading bias signals.

Pipeline:
  Step 1 — Extract & normalise event fields
  Step 2 — Fundamental interpretation (rules-based)
  Step 3 — Technical validation (EMA50, EMA200, RSI)
  Step 4 — Confidence scoring (0–100)
  Step 5 — Risk control (force WAIT gates)
  Step 6 — Build and return NewsSignal
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any

from config import NEWS_MAX_AGE_MINUTES
from engine.models import EconomicEvent, NewsSignal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOLDING_MINUTES: dict[str, int] = {
    "Immediate": 30,
    "Intraday": 240,
    "Multi-Day": 1440,
}

RISK_MAP: dict[str, str] = {
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}


# ---------------------------------------------------------------------------
# Step 2 helpers — fundamental interpretation rules
# ---------------------------------------------------------------------------

def _interpret_interest_rate(event: EconomicEvent) -> tuple[str, str, str]:
    """actual > forecast → BULLISH; actual < forecast → BEARISH; else NEUTRAL."""
    if event.actual is None or event.forecast is None:
        return "NEUTRAL", "Intraday", "Actual or forecast missing — cannot determine rate direction"
    if event.actual > event.forecast:
        return "BULLISH", "Intraday", f"Rate actual ({event.actual}) exceeded forecast ({event.forecast}) → hawkish surprise"
    if event.actual < event.forecast:
        return "BEARISH", "Intraday", f"Rate actual ({event.actual}) below forecast ({event.forecast}) → dovish surprise"
    return "NEUTRAL", "Intraday", "Rate matched forecast — no directional surprise"


def _interpret_cpi(event: EconomicEvent) -> tuple[str, str, str]:
    """Higher inflation → BULLISH only if it implies rate hike pressure."""
    if event.actual is None or event.forecast is None:
        return "NEUTRAL", "Intraday", "Actual or forecast missing — cannot determine CPI direction"
    if event.actual > event.forecast:
        return "BULLISH", "Intraday", (
            f"CPI beat ({event.actual} vs {event.forecast}) → rate hike expectations elevated"
        )
    if event.actual < event.forecast:
        return "BEARISH", "Intraday", (
            f"CPI miss ({event.actual} vs {event.forecast}) → easing pressure increasing"
        )
    return "NEUTRAL", "Intraday", "CPI in-line with forecast — no directional pressure"


def _interpret_employment(event: EconomicEvent) -> tuple[str, str, str]:
    """Strong jobs → BULLISH; weak jobs → BEARISH."""
    if event.actual is None or event.forecast is None:
        if event.actual is None and event.previous is None:
            return "NEUTRAL", "Intraday", "Employment data unavailable"
        # Attempt previous comparison
        if event.actual is not None and event.previous is not None:
            if event.actual > event.previous:
                return "BULLISH", "Intraday", f"Employment improved vs previous ({event.actual} > {event.previous})"
            return "BEARISH", "Intraday", f"Employment deteriorated vs previous ({event.actual} < {event.previous})"
        return "NEUTRAL", "Intraday", "Insufficient employment data"
    # Nonfarm payroll style: higher number = more jobs = bullish
    if event.actual > event.forecast:
        return "BULLISH", "Intraday", f"Employment beat ({event.actual}K vs {event.forecast}K) → labour market strength"
    if event.actual < event.forecast:
        return "BEARISH", "Intraday", f"Employment miss ({event.actual}K vs {event.forecast}K) → labour market weakness"
    return "NEUTRAL", "Intraday", "Employment in-line with forecast"


def _interpret_gdp(event: EconomicEvent) -> tuple[str, str, str]:
    """Higher growth → BULLISH; lower growth → BEARISH."""
    if event.actual is None or event.forecast is None:
        return "NEUTRAL", "Multi-Day", "GDP data missing — cannot determine growth direction"
    if event.actual > event.forecast:
        return "BULLISH", "Multi-Day", f"GDP beat ({event.actual}% vs {event.forecast}%) → stronger growth"
    if event.actual < event.forecast:
        return "BEARISH", "Multi-Day", f"GDP miss ({event.actual}% vs {event.forecast}%) → weaker growth"
    return "NEUTRAL", "Multi-Day", "GDP matched forecast — neutral growth signal"


def _interpret_central_bank(event: EconomicEvent) -> tuple[str, str, str]:
    """
    Hawkish/dovish classification from event name keywords,
    then fallback to actual vs previous rate change comparison.
    """
    name_lower = event.event_name.lower()
    hawkish_words = (
        "hike", "hawkish", "tighten", "restrictive", "above target",
        "rate rise", "increase rate", "quantitative tightening", "qt",
        "tapering", "taper",
    )
    dovish_words = (
        "cut", "dovish", "easing", "accommodative", "below target",
        "rate cut", "reduce rate", "pause", "quantitative easing", "qe",
        "pivot",
    )
    if any(w in name_lower for w in hawkish_words):
        return "BULLISH", "Multi-Day", f"Hawkish tone detected: '{event.event_name}'"
    if any(w in name_lower for w in dovish_words):
        return "BEARISH", "Multi-Day", f"Dovish tone detected: '{event.event_name}'"

    # Fallback: compare actual rate vs previous rate (rate decision events)
    if event.actual is not None and event.previous is not None:
        if event.actual > event.previous:
            return "BULLISH", "Multi-Day", (
                f"Rate raised: {event.actual}% vs previous {event.previous}% → hawkish"
            )
        if event.actual < event.previous:
            return "BEARISH", "Multi-Day", (
                f"Rate cut: {event.actual}% vs previous {event.previous}% → dovish"
            )
        return "NEUTRAL", "Intraday", (
            f"Rate held at {event.actual}% — no change from previous"
        )

    return "NEUTRAL", "Intraday", (
        f"Central bank event '{event.event_name}' — tone unclear from name, no rate data"
    )


def _interpret_geopolitical(event: EconomicEvent) -> tuple[str, str, str]:
    """Uncertainty → BEARISH; stability → BULLISH."""
    name_lower = event.event_name.lower()
    risk_on_words = ("ceasefire", "peace", "resolution", "agreement", "deal", "stability")
    risk_off_words = ("war", "conflict", "sanction", "tension", "attack", "crisis", "escalat")
    if any(w in name_lower for w in risk_on_words):
        return "BULLISH", "Multi-Day", f"Geopolitical stability signal: '{event.event_name}'"
    if any(w in name_lower for w in risk_off_words):
        return "BEARISH", "Multi-Day", f"Geopolitical uncertainty: '{event.event_name}' → risk-off pressure"
    return "BEARISH", "Intraday", f"Geopolitical event: '{event.event_name}' — default to cautious bearish"


def _interpret_commodity(event: EconomicEvent) -> tuple[str, str, str]:
    if event.actual is None or event.forecast is None:
        return "NEUTRAL", "Intraday", "Commodity data missing"
    if event.actual > event.forecast:
        return "BULLISH", "Intraday", f"Commodity beat ({event.actual} vs {event.forecast})"
    if event.actual < event.forecast:
        return "BEARISH", "Intraday", f"Commodity miss ({event.actual} vs {event.forecast})"
    return "NEUTRAL", "Intraday", "Commodity in-line with forecast"


def _interpret_market_sentiment(event: EconomicEvent) -> tuple[str, str, str]:
    if event.actual is None or event.forecast is None:
        return "NEUTRAL", "Intraday", "Sentiment data missing"
    if event.actual > event.forecast:
        return "BULLISH", "Intraday", f"Sentiment improved ({event.actual} vs {event.forecast})"
    if event.actual < event.forecast:
        return "BEARISH", "Intraday", f"Sentiment declined ({event.actual} vs {event.forecast})"
    return "NEUTRAL", "Intraday", "Sentiment in-line with forecast"


_CATEGORY_INTERPRETERS = {
    "Interest Rate": _interpret_interest_rate,
    "CPI": _interpret_cpi,
    "Employment": _interpret_employment,
    "GDP": _interpret_gdp,
    "Central Bank": _interpret_central_bank,
    "Geopolitical": _interpret_geopolitical,
    "Commodity": _interpret_commodity,
    "Market Sentiment": _interpret_market_sentiment,
}


# ---------------------------------------------------------------------------
# Step 3 — Technical validation
# ---------------------------------------------------------------------------

def _technical_validation(
    sentiment: str,
    indicators: dict[str, Any],
) -> tuple[str, bool]:
    """
    Validates sentiment direction against EMA / RSI.

    Returns:
        (tech_action, technical_confirmation)
        tech_action: "BUY" | "SELL" | "WAIT"
    """
    price = indicators.get("price") or indicators.get("close")
    ema50 = indicators.get("ema50")
    ema200 = indicators.get("ema200")
    rsi = indicators.get("rsi14") or indicators.get("rsi")

    if price is None or ema50 is None or ema200 is None or rsi is None:
        return "WAIT", False

    price = float(price)
    ema50 = float(ema50)
    ema200 = float(ema200)
    rsi = float(rsi)

    buy_conditions = price > ema50 and ema50 > ema200 and rsi < 70
    sell_conditions = price < ema50 and ema50 < ema200 and rsi > 30

    if buy_conditions and sentiment == "BULLISH":
        return "BUY", True
    if sell_conditions and sentiment == "BEARISH":
        return "SELL", True
    if buy_conditions or sell_conditions:
        # Technical signal exists but sentiment doesn't align
        return "WAIT", False
    return "WAIT", False


# ---------------------------------------------------------------------------
# Step 4 — Confidence model
# ---------------------------------------------------------------------------

def _score_confidence(
    event: EconomicEvent,
    sentiment: str,
    tech_action: str,
    technical_confirmation: bool,
    indicators: dict[str, Any],
) -> tuple[int, list[str]]:
    """
    Confidence starts at 50, scored up/down per rules.
    Returns (clamped_score, list_of_score_notes).
    """
    score = 50
    notes: list[str] = []

    # +15 if news direction is clear (not NEUTRAL)
    if sentiment in ("BULLISH", "BEARISH"):
        score += 15
        notes.append("+15: Clear news direction")

    # +15 if actual vs forecast difference is meaningful (>0.1 difference or >0.05%)
    if event.actual is not None and event.forecast is not None:
        diff = abs(event.actual - event.forecast)
        if diff > 0.05:
            score += 15
            notes.append(f"+15: Meaningful actual vs forecast gap ({diff:.3f})")
        else:
            score -= 5
            notes.append(f"-5: Actual/forecast gap too small ({diff:.3f})")

    # +10 if technical indicators align
    if technical_confirmation:
        score += 10
        notes.append("+10: Technical confirmation")

    # +10 if impact HIGH
    if event.impact_level == "HIGH":
        score += 10
        notes.append("+10: HIGH impact event")

    # −20 conflicting signals (sentiment ≠ NEUTRAL but tech says opposite)
    if sentiment != "NEUTRAL" and tech_action == "WAIT" and not technical_confirmation:
        score -= 20
        notes.append("-20: Conflicting news vs technical signals")

    # −20 missing important values
    missing = []
    if event.actual is None:
        missing.append("actual")
    if event.forecast is None:
        missing.append("forecast")
    if missing:
        score -= 20
        notes.append(f"-20: Missing fields: {', '.join(missing)}")

    # −30 unclear market context (no valid indicators)
    price = indicators.get("price") or indicators.get("close")
    ema50 = indicators.get("ema50")
    if price is None or ema50 is None:
        score -= 30
        notes.append("-30: Unclear market context — no indicator data")

    # Clamp 0–100
    score = max(0, min(100, score))
    return score, notes


# ---------------------------------------------------------------------------
# Step 5 — Risk control
# ---------------------------------------------------------------------------

def _age_minutes(publication_time: str) -> float:
    """Returns how many minutes ago the event was published (UTC)."""
    if not publication_time:
        return float("inf")
    try:
        pub = datetime.fromisoformat(publication_time)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - pub).total_seconds() / 60.0
    except (ValueError, TypeError):
        return float("inf")


def _risk_control_gates(
    event: EconomicEvent,
    confidence: int,
    technical_confirmation: bool,
    age_mins: float,
    sentiment: str,
) -> list[str]:
    """
    Returns list of WAIT reasons. Empty list means all gates passed.
    Any non-empty result forces trade_action = WAIT.
    """
    gates: list[str] = []

    if event.impact_level != "HIGH":
        gates.append(f"WAIT: Impact is {event.impact_level}, only HIGH-impact events are actionable")

    if confidence < 65:
        gates.append(f"WAIT: Confidence {confidence}/100 is below threshold of 65")

    if age_mins > NEWS_MAX_AGE_MINUTES:
        gates.append(f"WAIT: Event is {age_mins:.0f} minutes old (max {NEWS_MAX_AGE_MINUTES})")

    if not technical_confirmation:
        gates.append("WAIT: No technical confirmation from EMA/RSI")

    if sentiment == "NEUTRAL":
        gates.append("WAIT: Sentiment is NEUTRAL — no directional bias")

    if event.actual is None or event.forecast is None:
        gates.append("WAIT: Actual or forecast values missing — required fields absent")

    return gates


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class NewsIntelligenceEngine:
    """
    Transforms a single EconomicEvent + market indicators into a
    probability-based NewsSignal.

    Does NOT predict markets. Does NOT execute trades.
    """

    def analyze(
        self,
        event: EconomicEvent,
        pair: str,
        indicators: dict[str, Any],
    ) -> NewsSignal:
        """
        Run the full 6-step pipeline.

        Parameters
        ----------
        event       : EconomicEvent from ForexFactoryFeed
        pair        : Trading pair this signal is for (e.g. 'EURUSD')
        indicators  : dict with keys: price/close, ema50, ema200, rsi14/rsi, atr14
        """

        # ── Step 1: Extract (already done by ForexFactoryFeed) ────────────
        # Validate required fields
        missing_top: list[str] = []
        for field in ["event_name", "currency", "impact_level", "category"]:
            if not getattr(event, field, None):
                missing_top.append(field)

        # ── Step 2: Fundamental interpretation ────────────────────────────
        interpreter = _CATEGORY_INTERPRETERS.get(event.category)
        if interpreter and not missing_top:
            sentiment, expected_duration, reason = interpreter(event)
        else:
            sentiment = "NEUTRAL"
            expected_duration = "Intraday"
            reason = f"No interpreter for category '{event.category}' or missing fields: {missing_top}"

        # ── Step 3: Technical validation ──────────────────────────────────
        tech_action, technical_confirmation = _technical_validation(sentiment, indicators)

        # ── Step 4: Confidence model ───────────────────────────────────────
        confidence, score_notes = _score_confidence(
            event, sentiment, tech_action, technical_confirmation, indicators
        )

        # ── Step 5: Risk control gates ────────────────────────────────────
        age_mins = _age_minutes(event.publication_time)
        gate_warnings = _risk_control_gates(event, confidence, technical_confirmation, age_mins, sentiment)

        entry_allowed = len(gate_warnings) == 0
        if gate_warnings:
            trade_action = "WAIT"
        else:
            trade_action = tech_action  # BUY | SELL (already validated in step 3)

        # Risk label
        if entry_allowed and confidence >= 85:
            risk = "LOW"
        elif entry_allowed and confidence >= 80:
            risk = "MEDIUM"
        else:
            risk = "HIGH"

        # Holding duration
        holding_minutes = HOLDING_MINUTES.get(expected_duration, 240)

        # Assemble all warnings
        all_warnings = gate_warnings + score_notes

        # ── Step 6: Build output ──────────────────────────────────────────
        return NewsSignal(
            event_name=event.event_name,
            pair=pair,
            impact=event.impact_level,
            sentiment=sentiment,
            confidence=confidence,
            trade_action=trade_action,
            entry_allowed=entry_allowed,
            holding_minutes=holding_minutes,
            risk=risk,
            expected_duration=expected_duration,
            reason=reason,
            warnings=all_warnings,
            technical_confirmation=technical_confirmation,
            logged_at=datetime.now(timezone.utc).isoformat(),
        )

    def analyze_event_for_all_pairs(
        self,
        event: EconomicEvent,
        indicators_by_pair: dict[str, dict[str, Any]],
    ) -> list[NewsSignal]:
        """
        Run the pipeline for every affected pair in the event,
        using the provided indicators dict keyed by pair symbol.
        """
        signals: list[NewsSignal] = []
        for pair in event.affected_pairs:
            indicators = indicators_by_pair.get(pair, {})
            signal = self.analyze(event, pair, indicators)
            signals.append(signal)
        return signals

    def to_json_dict(self, signal: NewsSignal) -> dict[str, Any]:
        """
        Returns the canonical JSON output format specified in the pipeline spec.
        All unavailable fields use null.
        """
        return {
            "event_name": signal.event_name or None,
            "pair": signal.pair or None,
            "impact": signal.impact or None,
            "sentiment": signal.sentiment or None,
            "confidence": signal.confidence,
            "trade_action": signal.trade_action,
            "entry_allowed": signal.entry_allowed,
            "holding_minutes": signal.holding_minutes,
            "risk": signal.risk,
            "expected_duration": signal.expected_duration or None,
            "reason": signal.reason or None,
            "warnings": signal.warnings,
            "technical_confirmation": signal.technical_confirmation,
        }
