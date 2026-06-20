import pandas as pd
import requests
import time

from config import (
    ALPHA_VANTAGE_API_KEY,
    ALPHA_VANTAGE_INTERVALS,
    REQUIRED_OHLC_COLUMNS,
)
from data.sample_loader import load_sample_data

LIVE_DATA_CACHE = {}
CACHE_TTL_SECONDS = 60


YAHOO_SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "USDJPY": "JPY=X",
    "USDCHF": "CHF=X",
    "USDCAD": "CAD=X",
    "XAUUSD": "GC=F",
}

YAHOO_INTERVALS = {
    "5": ("5m", "5d"),
    "15": ("15m", "5d"),
    "30": ("30m", "1mo"),
    "60": ("60m", "1mo"),
    "240": ("1h", "3mo"),
    "D": ("1d", "6mo"),
}


def validate_ohlc_data(df):
    if df is None or df.empty:
        return False, "No candle data returned"

    missing_columns = [col for col in REQUIRED_OHLC_COLUMNS if col not in df.columns]
    if missing_columns:
        return False, f"Missing columns: {', '.join(missing_columns)}"

    if df[["open", "high", "low", "close"]].isnull().any().any():
        return False, "OHLC data contains empty values"

    if len(df) < 20:
        return False, "Not enough candles for signal analysis"

    return True, "Data valid"


def _get_cached_live_data(provider, symbol, timeframe):
    cache_key = (provider, symbol, timeframe)
    cached = LIVE_DATA_CACHE.get(cache_key)
    if not cached:
        return None
    if time.time() - cached["timestamp"] > CACHE_TTL_SECONDS:
        return None

    df = cached["df"].copy()
    df.attrs.update(cached.get("attrs", {}))
    df.attrs["cache_status"] = "cached"
    return df


def _store_cached_live_data(provider, symbol, timeframe, df):
    cache_key = (provider, symbol, timeframe)
    LIVE_DATA_CACHE[cache_key] = {
        "timestamp": time.time(),
        "df": df.copy(),
        "attrs": dict(getattr(df, "attrs", {})),
    }


def get_yahoo_finance_data(symbol="EURUSD", timeframe="5"):
    cached = _get_cached_live_data("yahoo_finance", symbol, timeframe)
    if cached is not None:
        return cached

    yahoo_symbol = YAHOO_SYMBOLS.get(symbol)
    interval_range = YAHOO_INTERVALS.get(timeframe)
    if not yahoo_symbol or not interval_range:
        return None

    interval, data_range = interval_range
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}",
        params={
            "interval": interval,
            "range": data_range,
            "includePrePost": "false",
            "events": "div,splits",
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    result = (((payload or {}).get("chart") or {}).get("result") or [None])[0]
    if not result:
        return None

    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote")) or [None])[0] or {}
    if not timestamps or not quote:
        return None

    df = pd.DataFrame(
        {
            "time": pd.to_datetime(timestamps, unit="s", utc=True),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        }
    )
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

    is_valid, message = validate_ohlc_data(df)
    if not is_valid:
        print(f"Yahoo Finance data validation failed: {message}")
        return None

    df.attrs["data_source"] = "yahoo_finance"
    df.attrs["cache_status"] = "fresh"
    if symbol == "XAUUSD":
        df.attrs["source_note"] = "Using GC=F gold futures proxy for XAUUSD"
    _store_cached_live_data("yahoo_finance", symbol, timeframe, df)
    return df


def get_live_forex(symbol="EURUSD", timeframe="5"):
    try:
        cached_alpha = _get_cached_live_data("alpha_vantage", symbol, timeframe)
        if cached_alpha is not None:
            return cached_alpha

        if not ALPHA_VANTAGE_API_KEY:
            print("Alpha Vantage API key missing. Falling back to sample data.")
            yahoo_df = get_yahoo_finance_data(symbol, timeframe)
            if yahoo_df is not None:
                yahoo_df.attrs["fallback_reason"] = "Alpha Vantage API key missing, using Yahoo Finance."
                return yahoo_df
            sample_df = load_sample_data(fallback_reason="Alpha Vantage API key missing, Yahoo Finance also failed.")
            sample_df.attrs["data_source"] = "local_sample_data"
            return sample_df

        interval = ALPHA_VANTAGE_INTERVALS.get(timeframe)
        if interval is None:
            print(f"Unsupported Alpha Vantage timeframe: {timeframe}. Falling back to sample data.")
            sample_df = load_sample_data(fallback_reason=f"Unsupported Alpha Vantage timeframe: {timeframe}")
            sample_df.attrs["data_source"] = "local_sample_data"
            return sample_df


        from_currency = symbol[:3]
        to_currency = symbol[3:]

        response = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "FX_INTRADAY",
                "from_symbol": from_currency,
                "to_symbol": to_currency,
                "interval": interval,
                "apikey": ALPHA_VANTAGE_API_KEY,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        if "Note" in data:
            print("Alpha Vantage API limit reached")
            yahoo_df = get_yahoo_finance_data(symbol, timeframe)
            if yahoo_df is not None:
                yahoo_df.attrs["fallback_reason"] = "Alpha Vantage API limit reached, using Yahoo Finance."
                return yahoo_df
            sample_df = load_sample_data(fallback_reason="Alpha Vantage API limit reached, Yahoo Finance also failed.")
            sample_df.attrs["data_source"] = "local_sample_data"
            return sample_df

        if "Error Message" in data:
            print(f"Invalid Alpha Vantage API call: {data['Error Message']}")
            yahoo_df = get_yahoo_finance_data(symbol, timeframe)
            if yahoo_df is not None:
                yahoo_df.attrs["fallback_reason"] = f"Invalid Alpha Vantage API call, using Yahoo Finance: {data['Error Message']}"
                return yahoo_df
            sample_df = load_sample_data(fallback_reason=f"Invalid Alpha Vantage API call, Yahoo Finance also failed: {data['Error Message']}")
            sample_df.attrs["data_source"] = "local_sample_data"
            return sample_df

        if "Information" in data:
            print(f"Alpha Vantage response: {data['Information']}")
            yahoo_df = get_yahoo_finance_data(symbol, timeframe)
            if yahoo_df is not None:
                yahoo_df.attrs["fallback_reason"] = f"Alpha Vantage info message, using Yahoo Finance: {data['Information']}"
                return yahoo_df
            sample_df = load_sample_data(fallback_reason=f"Alpha Vantage info message, Yahoo Finance also failed: {data['Information']}")
            sample_df.attrs["data_source"] = "local_sample_data"
            return sample_df

        keys = [key for key in data.keys() if "Time Series" in key]
        if not keys:
            print("No time series data found in Alpha Vantage response")
            yahoo_df = get_yahoo_finance_data(symbol, timeframe)
            if yahoo_df is not None:
                yahoo_df.attrs["fallback_reason"] = "No time series data found in Alpha Vantage response, using Yahoo Finance."
                return yahoo_df
            sample_df = load_sample_data(fallback_reason="No time series data found in Alpha Vantage response, Yahoo Finance also failed.")
            sample_df.attrs["data_source"] = "local_sample_data"
            return sample_df

        df = pd.DataFrame(data[keys[0]]).T
        df.index = pd.to_datetime(df.index)
        df = df.rename(
            columns={
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
                "5. volume": "volume",
            }
        )
        if "volume" not in df.columns:
            df["volume"] = 0.0
            
        df = df.astype(float)
        df.reset_index(inplace=True)
        df.rename(columns={"index": "time"}, inplace=True)
        df = df.sort_values("time").reset_index(drop=True)

        is_valid, message = validate_ohlc_data(df)
        if not is_valid:
            print(f"Live data validation failed: {message}")
            yahoo_df = get_yahoo_finance_data(symbol, timeframe)
            if yahoo_df is not None:
                return yahoo_df
            sample_df = load_sample_data(fallback_reason=f"Live data validation failed, Yahoo Finance also failed: {message}")
            sample_df.attrs["data_source"] = "local_sample_data"
            return sample_df

        df.attrs["data_source"] = "alpha_vantage"
        df.attrs["cache_status"] = "fresh"
        _store_cached_live_data("alpha_vantage", symbol, timeframe, df)
        return df

    except Exception as e:
        # This catch-all handles network errors, JSON parsing errors, etc.
        print(f"Data fetch error: {e}")
        yahoo_df = get_yahoo_finance_data(symbol, timeframe)
        if yahoo_df is not None:
            yahoo_df.attrs["fallback_reason"] = f"Alpha Vantage request failed: {e}"
            return yahoo_df
        sample_df = load_sample_data(fallback_reason=f"Data fetch error from all sources: {e}")
        sample_df.attrs["data_source"] = "local_sample_data"
        return sample_df
