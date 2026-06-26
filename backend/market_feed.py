from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import pandas as pd
import requests

from config import ALPHA_VANTAGE_API_KEY, ALPHA_VANTAGE_INTERVALS
from data.sample_loader import load_sample_data
from engine.models import FeedMetadata
from storage.cache import InMemoryTTLCache


CANONICAL_CANDLE_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "source"]
YAHOO_PROVIDER_NAME = "Yahoo"
OANDA_PROVIDER_NAME = "OANDA"
SAMPLE_PROVIDER_NAME = "Sample"

YAHOO_SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "USDJPY": "JPY=X",
    "USDCHF": "CHF=X",
    "USDCAD": "CAD=X",
    "XAUUSD": "GC=F",
}

OANDA_SYMBOLS = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "AUDUSD": "AUD_USD",
    "USDJPY": "USD_JPY",
    "USDCHF": "USD_CHF",
    "USDCAD": "USD_CAD",
    "XAUUSD": "XAU_USD",
}

YAHOO_INTERVALS = {
    "1": ("1m", "1d"),
    "5": ("5m", "5d"),
    "15": ("15m", "5d"),
    "30": ("30m", "1mo"),
    "60": ("60m", "1mo"),
    "240": ("1h", "3mo"),
    "D": ("1d", "6mo"),
}

OANDA_GRANULARITIES = {
    "1": "M1",
    "5": "M5",
    "15": "M15",
    "30": "M30",
    "60": "H1",
    "240": "H4",
    "D": "D",
}


@dataclass
class QuoteSnapshot:
    symbol: str
    bid: float
    ask: float
    timestamp: datetime
    provider: str
    spread: float = 0.0


@dataclass
class MarketFrame:
    candles: pd.DataFrame
    metadata: FeedMetadata
    quote: QuoteSnapshot | None = None


class MarketProvider(Protocol):
    provider_name: str

    def get_candles(self, symbol: str, timeframe: str) -> MarketFrame | None:
        ... 

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        ...

    def get_symbols(self) -> list[str]:
        ...


def normalize_candles(df: pd.DataFrame, source: str) -> pd.DataFrame:
    candles = pd.DataFrame(df).copy()
    if "timestamp" not in candles.columns:
        if "time" in candles.columns:
            candles = candles.rename(columns={"time": "timestamp"})
        else:
            return pd.DataFrame(columns=CANONICAL_CANDLE_COLUMNS)

    for column in ["open", "high", "low", "close"]:
        candles[column] = pd.to_numeric(candles[column], errors="coerce")

    if "volume" not in candles.columns:
        candles["volume"] = 0
    candles["volume"] = pd.to_numeric(candles["volume"], errors="coerce").fillna(0)
    candles["timestamp"] = pd.to_datetime(candles["timestamp"], errors="coerce", utc=True)
    candles["source"] = source

    candles = candles.dropna(subset=["timestamp", "open", "high", "low", "close"]).reset_index(drop=True)
    if candles.empty:
        return pd.DataFrame(columns=CANONICAL_CANDLE_COLUMNS)

    candles = candles.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return candles[CANONICAL_CANDLE_COLUMNS]


def validate_ohlcv(df: pd.DataFrame) -> tuple[bool, str]:
    if df is None or df.empty:
        return False, "No candle data returned"
    missing_columns = [column for column in CANONICAL_CANDLE_COLUMNS if column not in df.columns]
    if missing_columns:
        return False, f"Missing columns: {', '.join(missing_columns)}"
    if df[["open", "high", "low", "close"]].isnull().any().any():
        return False, "OHLC data contains empty values"
    if len(df) < 20:
        return False, "Not enough candles for signal analysis"
    return True, "Data valid"


class YahooProvider:
    provider_name = YAHOO_PROVIDER_NAME

    def get_symbols(self) -> list[str]:
        return list(YAHOO_SYMBOLS.keys())

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        frame = self.get_candles(symbol, "5")
        if frame is None or frame.candles.empty:
            return None
        last = frame.candles.iloc[-1]
        price = float(last["close"])
        return QuoteSnapshot(
            symbol=symbol,
            bid=price,
            ask=price,
            timestamp=last["timestamp"].to_pydatetime(),
            provider=self.provider_name,
        )

    def get_candles(self, symbol: str, timeframe: str) -> MarketFrame | None:
        provider_symbol = YAHOO_SYMBOLS.get(symbol)
        interval_range = YAHOO_INTERVALS.get(timeframe)
        if not provider_symbol or not interval_range:
            return None

        interval, data_range = interval_range
        started_at = datetime.now(timezone.utc)
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{provider_symbol}",
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

        normalized = normalize_candles(
            pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
                    "open": quote.get("open"),
                    "high": quote.get("high"),
                    "low": quote.get("low"),
                    "close": quote.get("close"),
                    "volume": quote.get("volume"),
                }
            ),
            source=self.provider_name,
        )
        is_valid, _ = validate_ohlcv(normalized)
        if not is_valid:
            return None

        fetched_at = datetime.now(timezone.utc)
        note = "Using GC=F gold futures proxy for XAUUSD" if symbol == "XAUUSD" else ""
        return MarketFrame(
            candles=normalized,
            metadata=FeedMetadata(
                symbol=symbol,
                timeframe=timeframe,
                source=self.provider_name,
                provider=self.provider_name,
                provider_symbol=provider_symbol,
                fetched_at=fetched_at,
                latency_seconds=(fetched_at - started_at).total_seconds(),
                source_note=note,
                total_bars=len(normalized),
            ),
            quote=None,
        )


class YFinanceProvider:
    provider_name = "yfinance"

    def get_symbols(self) -> list[str]:
        return list(YAHOO_SYMBOLS.keys())

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        frame = self.get_candles(symbol, "5")
        if frame is None or frame.candles.empty:
            return None
        last = frame.candles.iloc[-1]
        price = float(last["close"])
        return QuoteSnapshot(
            symbol=symbol,
            bid=price,
            ask=price,
            timestamp=last["timestamp"].to_pydatetime(),
            provider=self.provider_name,
        )

    def get_candles(self, symbol: str, timeframe: str) -> MarketFrame | None:
        provider_symbol = YAHOO_SYMBOLS.get(symbol)
        interval_range = YAHOO_INTERVALS.get(timeframe)
        if not provider_symbol or not interval_range:
            return None

        interval, data_range = interval_range
        started_at = datetime.now(timezone.utc)
        
        try:
            import yfinance as yf
            ticker = yf.Ticker(provider_symbol)
            df = ticker.history(period=data_range, interval=interval, prepost=False)
            if df.empty:
                return None
            
            df = df.reset_index()
            if "Datetime" in df.columns:
                df = df.rename(columns={"Datetime": "timestamp"})
            elif "Date" in df.columns:
                df = df.rename(columns={"Date": "timestamp"})
            
            df = df.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            
            normalized = normalize_candles(df, source=self.provider_name)
            is_valid, _ = validate_ohlcv(normalized)
            if not is_valid:
                return None

            fetched_at = datetime.now(timezone.utc)
            note = "Using GC=F gold futures proxy for XAUUSD" if symbol == "XAUUSD" else ""
            return MarketFrame(
                candles=normalized,
                metadata=FeedMetadata(
                    symbol=symbol,
                    timeframe=timeframe,
                    source=self.provider_name,
                    provider=self.provider_name,
                    provider_symbol=provider_symbol,
                    fetched_at=fetched_at,
                    latency_seconds=(fetched_at - started_at).total_seconds(),
                    source_note=note,
                    total_bars=len(normalized),
                ),
                quote=None,
            )
        except Exception as e:
            print(f"YFinanceProvider error: {e}")
            return None


class OandaProvider:
    provider_name = OANDA_PROVIDER_NAME

    def __init__(self):
        self.api_token = os.getenv("OANDA_API_TOKEN", "").strip()
        self.account_environment = os.getenv("OANDA_ENVIRONMENT", "practice").strip().lower()

    def get_symbols(self) -> list[str]:
        return list(OANDA_SYMBOLS.keys())

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        return None

    def get_candles(self, symbol: str, timeframe: str) -> MarketFrame | None:
        if not self.api_token:
            return None

        provider_symbol = OANDA_SYMBOLS.get(symbol)
        granularity = OANDA_GRANULARITIES.get(timeframe)
        if not provider_symbol or not granularity:
            return None

        host = "api-fxpractice.oanda.com" if self.account_environment == "practice" else "api-fxtrade.oanda.com"
        started_at = datetime.now(timezone.utc)
        response = requests.get(
            f"https://{host}/v3/instruments/{provider_symbol}/candles",
            params={"granularity": granularity, "count": 500, "price": "M"},
            headers={"Authorization": f"Bearer {self.api_token}"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        candles = payload.get("candles") or []
        rows = []
        for candle in candles:
            if not candle.get("complete"):
                continue
            mid = candle.get("mid") or {}
            rows.append(
                {
                    "timestamp": candle.get("time"),
                    "open": mid.get("o"),
                    "high": mid.get("h"),
                    "low": mid.get("l"),
                    "close": mid.get("c"),
                    "volume": candle.get("volume", 0),
                }
            )

        normalized = normalize_candles(pd.DataFrame(rows), source=self.provider_name)
        is_valid, _ = validate_ohlcv(normalized)
        if not is_valid:
            return None

        fetched_at = datetime.now(timezone.utc)
        return MarketFrame(
            candles=normalized,
            metadata=FeedMetadata(
                symbol=symbol,
                timeframe=timeframe,
                source=self.provider_name,
                provider=self.provider_name,
                provider_symbol=provider_symbol,
                fetched_at=fetched_at,
                latency_seconds=(fetched_at - started_at).total_seconds(),
                total_bars=len(normalized),
            ),
            quote=None,
        )


class AlphaVantageProvider:
    provider_name = "Alpha Vantage"

    def get_symbols(self) -> list[str]:
        return ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        return None

    def get_candles(self, symbol: str, timeframe: str) -> MarketFrame | None:
        if not ALPHA_VANTAGE_API_KEY:
            return None

        interval = ALPHA_VANTAGE_INTERVALS.get(timeframe)
        if interval is None:
            return None

        started_at = datetime.now(timezone.utc)
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "FX_INTRADAY",
                "from_symbol": symbol[:3],
                "to_symbol": symbol[3:],
                "interval": interval,
                "apikey": ALPHA_VANTAGE_API_KEY,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if "Note" in payload or "Error Message" in payload or "Information" in payload:
            return None

        keys = [key for key in payload.keys() if "Time Series" in key]
        if not keys:
            return None

        frame = pd.DataFrame(payload[keys[0]]).T
        frame.index = pd.to_datetime(frame.index, utc=True)
        frame = frame.rename(
            columns={
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
            }
        )
        frame = frame.astype(float).reset_index().rename(columns={"index": "timestamp"})
        frame["volume"] = 0
        normalized = normalize_candles(frame, source=self.provider_name)
        is_valid, _ = validate_ohlcv(normalized)
        if not is_valid:
            return None

        fetched_at = datetime.now(timezone.utc)
        return MarketFrame(
            candles=normalized,
            metadata=FeedMetadata(
                symbol=symbol,
                timeframe=timeframe,
                source=self.provider_name,
                provider=self.provider_name,
                provider_symbol=symbol,
                fetched_at=fetched_at,
                latency_seconds=(fetched_at - started_at).total_seconds(),
                total_bars=len(normalized),
            ),
            quote=None,
        )


class SampleDataProvider:
    provider_name = SAMPLE_PROVIDER_NAME

    def get_symbols(self) -> list[str]:
        return ["XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        return None

    def get_candles(self, symbol: str, timeframe: str) -> MarketFrame | None:
        frame = load_sample_data(fallback_reason="Live providers unavailable")
        if frame is None:
            return None
        normalized = normalize_candles(frame, source=self.provider_name)
        is_valid, _ = validate_ohlcv(normalized)
        if not is_valid:
            return None
        fetched_at = datetime.now(timezone.utc)
        return MarketFrame(
            candles=normalized,
            metadata=FeedMetadata(
                symbol=symbol,
                timeframe=timeframe,
                source=self.provider_name,
                provider=self.provider_name,
                provider_symbol=symbol,
                fetched_at=fetched_at,
                latency_seconds=0.0,
                source_note="Fallback sample candles",
                total_bars=len(normalized),
            ),
            quote=None,
        )


class MT5Provider:
    provider_name = "MT5"

    def get_symbols(self) -> list[str]:
        return ["XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        from mt5_data import initialize_mt5, find_mt5_symbol
        import MetaTrader5 as mt5
        try:
            initialize_mt5()
            matched_symbol = find_mt5_symbol(symbol)
            tick = mt5.symbol_info_tick(matched_symbol)
            if tick is not None:
                bid = float(tick.bid)
                ask = float(tick.ask)
                spread = ask - bid
                return QuoteSnapshot(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    timestamp=datetime.fromtimestamp(tick.time, tz=timezone.utc),
                    provider=self.provider_name,
                    spread=spread
                )
        except Exception as e:
            print(f"MT5 get_quote error: {e}")

        frame = self.get_candles(symbol, "5")
        if frame is None or frame.candles.empty:
            return None
        last = frame.candles.iloc[-1]
        price = float(last["close"])
        return QuoteSnapshot(
            symbol=symbol,
            bid=price,
            ask=price,
            timestamp=last["timestamp"].to_pydatetime(),
            provider=self.provider_name,
            spread=0.0
        )

    def get_candles(self, symbol: str, timeframe: str) -> MarketFrame | None:
        from mt5_data import get_mt5_candles, find_mt5_symbol
        started_at = datetime.now(timezone.utc)
        try:
            matched_symbol = find_mt5_symbol(symbol)
            # Fetch Rates from MT5
            df = get_mt5_candles(symbol, timeframe, num_candles=500)
            if df is None or df.empty:
                return None
            
            # Normalize to canonical form
            normalized = normalize_candles(df, source=self.provider_name)
            is_valid, _ = validate_ohlcv(normalized)
            if not is_valid:
                return None

            fetched_at = datetime.now(timezone.utc)
            return MarketFrame(
                candles=normalized,
                metadata=FeedMetadata(
                    symbol=symbol,
                    timeframe=timeframe,
                    source=self.provider_name,
                    provider=self.provider_name,
                    provider_symbol=matched_symbol,
                    fetched_at=fetched_at,
                    latency_seconds=(fetched_at - started_at).total_seconds(),
                    total_bars=len(normalized),
                ),
                quote=None,
            )
        except Exception as e:
            print(f"MT5Provider error: {e}")
            return None


def get_simulated_spread(symbol: str) -> float:
    return {
        "XAUUSD": 0.25,
        "EURUSD": 0.00012,
        "GBPUSD": 0.00015,
        "AUDUSD": 0.00014,
        "USDJPY": 0.015,
        "USDCHF": 0.00015,
        "USDCAD": 0.00016,
        "BTCUSD": 15.0
    }.get(symbol.upper(), 0.0001)


class UnifiedMarketFeed:
    def __init__(self, providers: list[MarketProvider], cache: InMemoryTTLCache):
        self.providers = providers
        self.cache = cache

    def fetch(self, symbol: str, timeframe: str, force_refresh: bool = False) -> MarketFrame | None:
        cache_key = (symbol, timeframe)
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                cached.metadata.cache_status = "cached"
                return cached

        for provider in self.providers:
            if symbol not in provider.get_symbols():
                continue
            try:
                frame = provider.get_candles(symbol, timeframe)
            except Exception:
                frame = None
            if frame is not None:
                frame.metadata.cache_status = "fresh"
                # Enrich with quote snapshot
                try:
                    quote = provider.get_quote(symbol)
                    if quote is not None:
                        # If spread is zero or invalid, simulate a realistic spread
                        if quote.bid == quote.ask or quote.spread <= 0.0:
                            sim_spread = get_simulated_spread(symbol)
                            quote.spread = sim_spread
                            quote.ask = quote.bid + sim_spread
                        frame.quote = quote
                except Exception:
                    pass
                self.cache.set(cache_key, frame)
                return frame
        return None
