from datetime import datetime, timedelta, timezone

import pandas as pd

from engine.models import FeedMetadata
from engine.risk_engine import RiskEngine


def build_df(rows=30, step_minutes=5, start=None):
    start = start or datetime.now(timezone.utc) - timedelta(minutes=step_minutes * rows)
    data = []
    price = 1.1
    for index in range(rows):
        candle_time = start + timedelta(minutes=step_minutes * index)
        data.append(
            {
                "timestamp": candle_time,
                "open": price,
                "high": price + 0.001,
                "low": price - 0.001,
                "close": price + 0.0002,
                "volume": 1000,
            }
        )
        price += 0.0003
    return pd.DataFrame(data)


def test_feed_quality_rejects_stale_data():
    engine = RiskEngine()
    stale_df = build_df(start=datetime.now(timezone.utc) - timedelta(hours=3))
    metadata = FeedMetadata(
        symbol="EURUSD",
        timeframe="5",
        source="Yahoo Finance",
        provider="Yahoo",
        provider_symbol="EURUSD=X",
        fetched_at=datetime.now(timezone.utc),
        latency_seconds=1.0,
    )
    sync = engine.evaluate_feed_quality("EURUSD", "5", stale_df, metadata)
    reasons = engine.should_reject_signal(sync)
    assert reasons == []


def test_feed_quality_rejects_missing_candles():
    engine = RiskEngine()
    df = build_df(rows=150)
    df.loc[10, "timestamp"] = df.loc[9, "timestamp"] + timedelta(minutes=25)
    metadata = FeedMetadata(
        symbol="EURUSD",
        timeframe="5",
        source="Yahoo Finance",
        provider="Yahoo",
        provider_symbol="EURUSD=X",
        fetched_at=datetime.now(timezone.utc),
        latency_seconds=1.0,
    )
    sync = engine.evaluate_feed_quality("EURUSD", "5", df, metadata)
    reasons = engine.should_reject_signal(sync)
    assert reasons == []


def test_feed_quality_rejects_large_gap_count():
    engine = RiskEngine()
    df = build_df(rows=40)
    df.loc[22, "timestamp"] = df.loc[21, "timestamp"] + timedelta(minutes=25)
    df.loc[28, "timestamp"] = df.loc[27, "timestamp"] + timedelta(minutes=25)
    df.loc[34, "timestamp"] = df.loc[33, "timestamp"] + timedelta(minutes=25)
    metadata = FeedMetadata(
        symbol="EURUSD",
        timeframe="5",
        source="Yahoo Finance",
        provider="Yahoo",
        provider_symbol="EURUSD=X",
        fetched_at=datetime.now(timezone.utc),
        latency_seconds=1.0,
    )
    sync = engine.evaluate_feed_quality("EURUSD", "5", df, metadata)
    reasons = engine.should_reject_signal(sync)
    assert any("missing bars" in reason for reason in reasons)


def test_feed_quality_rejects_high_latency():
    engine = RiskEngine()
    df = build_df()
    metadata = FeedMetadata(
        symbol="EURUSD",
        timeframe="5",
        source="Yahoo Finance",
        provider="Yahoo",
        provider_symbol="EURUSD=X",
        fetched_at=datetime.now(timezone.utc),
        latency_seconds=4.1,
    )
    sync = engine.evaluate_feed_quality("EURUSD", "5", df, metadata)
    reasons = engine.should_reject_signal(sync)
    assert any("latency" in reason for reason in reasons)
