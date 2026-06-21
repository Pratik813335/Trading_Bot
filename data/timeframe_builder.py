import math

import pandas as pd


TIMEFRAME_TO_MINUTES = {
    "1": 1,
    "5": 5,
    "15": 15,
    "30": 30,
    "60": 60,
    "240": 240,
    "D": 1440,
}


def _normalize_time_column(df, base_timeframe):
    candles = df.copy()
    if "time" not in candles.columns:
        step_minutes = TIMEFRAME_TO_MINUTES.get(base_timeframe, 5)
        candles["time"] = pd.date_range(
            end=pd.Timestamp.utcnow().floor("min"),
            periods=len(candles),
            freq=f"{step_minutes}min",
        )
    else:
        parsed = pd.to_datetime(candles["time"], errors="coerce")
        if parsed.isna().all():
            step_minutes = TIMEFRAME_TO_MINUTES.get(base_timeframe, 5)
            candles["time"] = pd.date_range(
                end=pd.Timestamp.utcnow().floor("min"),
                periods=len(candles),
                freq=f"{step_minutes}min",
            )
        else:
            candles["time"] = parsed.ffill().bfill()
    return candles


def resample_candles(df, source_timeframe, target_timeframe):
    candles = _normalize_time_column(df, source_timeframe)
    if source_timeframe == target_timeframe:
        return candles.reset_index(drop=True)

    source_minutes = TIMEFRAME_TO_MINUTES.get(source_timeframe)
    target_minutes = TIMEFRAME_TO_MINUTES.get(target_timeframe)
    if source_minutes is None or target_minutes is None or target_minutes < source_minutes:
        return candles.reset_index(drop=True)

    ratio = max(1, math.ceil(target_minutes / source_minutes))
    ordered = candles.sort_values("time").reset_index(drop=True).copy()
    ordered["_bucket"] = ordered.index // ratio

    aggregations = {
        "time": "first",
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in ordered.columns:
        aggregations["volume"] = "sum"

    resampled = ordered.groupby("_bucket", as_index=False).agg(aggregations)
    if "volume" not in resampled.columns:
        resampled["volume"] = 0
    resampled.attrs["data_source"] = ordered.attrs.get("data_source", "resampled")
    return resampled.reset_index(drop=True)


def build_timeframe_map(df, source_timeframe, target_timeframes=None):
    timeframes = target_timeframes or ["D", "240", "60", "15", "5"]
    source_minutes = TIMEFRAME_TO_MINUTES.get(source_timeframe, 5)

    available = {}
    for timeframe in timeframes:
        target_minutes = TIMEFRAME_TO_MINUTES.get(timeframe)
        if target_minutes is None or target_minutes < source_minutes:
            continue
        timeframe_df = resample_candles(df, source_timeframe, timeframe)
        if timeframe_df is not None and len(timeframe_df) >= 20:
            available[timeframe] = timeframe_df

    if source_timeframe not in available:
        source_df = resample_candles(df, source_timeframe, source_timeframe)
        if source_df is not None and len(source_df) >= 20:
            available[source_timeframe] = source_df

    ordered = dict(
        sorted(
            available.items(),
            key=lambda item: TIMEFRAME_TO_MINUTES.get(item[0], source_minutes),
            reverse=True,
        )
    )
    return ordered
