"""
backend/forex_factory_feed.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Fetches the ForexFactory economic calendar via the community-discovered
JSON mirror at https://nfs.faireconomy.media/ff_calendar_thisweek.json

No authentication required. Results are cached in-process for
FOREXFACTORY_CACHE_TTL seconds (default 300 s / 5 min).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from config import FOREXFACTORY_CACHE_TTL
from engine.models import EconomicEvent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

IMPACT_MAP: dict[str, str] = {
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "non-economic": "LOW",
    "holiday": "LOW",
}

# Keyword → category mapping (first match wins, case-insensitive)
CATEGORY_KEYWORDS: list[tuple[str, str]] = [
    (("interest rate", "rate decision", "fed funds", "boe rate", "ecb rate", "rba rate"), "Interest Rate"),
    (("cpi", "inflation", "pce", "price index", "consumer price"), "CPI"),
    (("gdp", "gross domestic product", "economic growth"), "GDP"),
    (("employment", "nonfarm", "jobs", "unemployment", "claimant", "labor", "labour", "payroll", "adp"), "Employment"),
    (("fed", "fomc", "powell", "central bank", "rba", "boe", "ecb", "boj", "snb", "rbnz", "statement", "minutes", "speech", "press conference"), "Central Bank"),
    (("oil", "crude", "gold", "commodity", "opec"), "Commodity"),
    (("war", "geopolit", "sanction", "conflict", "election", "referendum"), "Geopolitical"),
    (("sentiment", "confidence", "survey", "pmi", "ism", "business climate"), "Market Sentiment"),
]

# Currency → affected forex pairs (canonical bot symbols)
CURRENCY_PAIRS: dict[str, list[str]] = {
    "USD": ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD", "XAUUSD"],
    "EUR": ["EURUSD"],
    "GBP": ["GBPUSD"],
    "AUD": ["AUDUSD"],
    "JPY": ["USDJPY"],
    "CHF": ["USDCHF"],
    "CAD": ["USDCAD"],
    "NZD": ["AUDUSD"],   # proxy — bot doesn't track NZDUSD
    "XAU": ["XAUUSD"],
}

# Expected holding durations in minutes
DURATION_HOLDING: dict[str, int] = {
    "Immediate": 30,
    "Intraday": 240,
    "Multi-Day": 1440,
}


# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------

class _Cache:
    def __init__(self, ttl: float):
        self._ttl = ttl
        self._data: list[EconomicEvent] | None = None
        self._fetched_at: float = 0.0

    def get(self) -> list[EconomicEvent] | None:
        if self._data is not None and (time.monotonic() - self._fetched_at) < self._ttl:
            return self._data
        return None

    def set(self, data: list[EconomicEvent]) -> None:
        self._data = data
        self._fetched_at = time.monotonic()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_category(event_name: str) -> str:
    name_lower = event_name.lower()
    for keywords, category in CATEGORY_KEYWORDS:
        if any(kw in name_lower for kw in keywords):
            return category
    return "Other"


def _parse_float(value: Any) -> float | None:
    if value is None or value == "" or value == "N/A":
        return None
    try:
        # Strip trailing % or K or M, etc.
        cleaned = str(value).replace("%", "").replace("K", "").replace("M", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_utc_time(date_str: str) -> str:
    """
    FF JSON timestamps from nfs.faireconomy.media are in US Eastern Time
    (UTC-5 standard / UTC-4 DST). Naive timestamps must be shifted to UTC.
    Already-timezone-aware strings are converted directly.
    EST = UTC-5, so UTC = EST + 5h.
    """
    if not date_str:
        return date_str
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            # EST is UTC-5: add 5 hours to convert naive EST to UTC
            from datetime import timedelta
            dt = dt.replace(tzinfo=timezone.utc) + timedelta(hours=5)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return date_str


def _parse_event(raw: dict[str, Any]) -> EconomicEvent | None:
    event_name: str = str(raw.get("title") or raw.get("name") or "").strip()
    currency: str = str(raw.get("country") or raw.get("currency") or "").strip().upper()
    impact_raw: str = str(raw.get("impact") or "").strip().lower()
    date_str: str = str(raw.get("date") or raw.get("datetime") or "").strip()

    if not event_name or not currency:
        return None

    impact_level = IMPACT_MAP.get(impact_raw, "LOW")
    category = _detect_category(event_name)
    publication_time = _parse_utc_time(date_str) if date_str else ""
    affected_pairs = CURRENCY_PAIRS.get(currency, [])

    return EconomicEvent(
        event_name=event_name,
        currency=currency,
        impact_level=impact_level,
        category=category,
        publication_time=publication_time,
        actual=_parse_float(raw.get("actual")),
        forecast=_parse_float(raw.get("forecast")),
        previous=_parse_float(raw.get("previous")),
        affected_pairs=affected_pairs,
        source="ForexFactory",
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Public feed class
# ---------------------------------------------------------------------------

class ForexFactoryFeed:
    """
    Fetches this-week's ForexFactory calendar from the community JSON mirror.

    Usage::

        feed = ForexFactoryFeed()
        events = feed.fetch_events()            # list[EconomicEvent]
        high_only = feed.fetch_high_impact()    # filtered
    """

    def __init__(self, ttl: float = FOREXFACTORY_CACHE_TTL):
        self._cache = _Cache(ttl)
        self.last_fetch_error: str = ""
        self._rate_limited_until: float = 0.0

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def fetch_events(self, force_refresh: bool = False) -> list[EconomicEvent]:
        """Return all parsed events for the current week."""
        if not force_refresh:
            cached = self._cache.get()
            if cached is not None:
                return cached

        # Honour rate-limit backoff
        if time.monotonic() < self._rate_limited_until:
            remaining = int(self._rate_limited_until - time.monotonic())
            self.last_fetch_error = f"Rate limited — retrying in {remaining}s"
            # Return stale cache if available rather than empty list
            if self._cache._data is not None:
                return self._cache._data
            return []

        raw_events = self._fetch_raw()
        events: list[EconomicEvent] = []
        for raw in raw_events:
            event = _parse_event(raw)
            if event is not None:
                events.append(event)

        if events:
            self.last_fetch_error = ""
        self._cache.set(events)
        return events

    def fetch_high_impact(self, force_refresh: bool = False) -> list[EconomicEvent]:
        """Return only HIGH-impact events."""
        return [e for e in self.fetch_events(force_refresh) if e.impact_level == "HIGH"]

    def fetch_for_currency(self, currency: str, force_refresh: bool = False) -> list[EconomicEvent]:
        """Return events affecting a specific currency (e.g. 'USD')."""
        return [e for e in self.fetch_events(force_refresh) if e.currency == currency.upper()]

    def fetch_for_pair(self, pair: str, force_refresh: bool = False) -> list[EconomicEvent]:
        """Return events that affect a given trading pair (e.g. 'EURUSD')."""
        return [e for e in self.fetch_events(force_refresh) if pair.upper() in e.affected_pairs]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_raw(self) -> list[dict[str, Any]]:
        try:
            response = requests.get(
                FF_CALENDAR_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; TradingBot/1.0)",
                    "Accept": "application/json",
                },
                timeout=15,
            )
            if response.status_code == 429:
                # Back off for 60 seconds before next attempt
                self._rate_limited_until = time.monotonic() + 60.0
                self.last_fetch_error = "Rate limited by ForexFactory mirror (429). Auto-retry in 60s."
                print(f"[ForexFactoryFeed] Rate limited (429) — backing off 60s")
                # Return stale cache if available
                return []
            response.raise_for_status()
            self.last_fetch_error = ""
            data = response.json()
            if isinstance(data, list):
                return data
            # Some mirrors wrap in {"data": [...]}
            if isinstance(data, dict):
                return data.get("data", data.get("events", []))
            return []
        except Exception as exc:
            self.last_fetch_error = str(exc)
            print(f"[ForexFactoryFeed] Failed to fetch calendar: {exc}")
            return []

