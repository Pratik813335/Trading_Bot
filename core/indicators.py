import math

import pandas as pd


def prepare_candles(df):
    if df is None:
        return pd.DataFrame()

    candles = pd.DataFrame(df).copy()
    if "timestamp" not in candles.columns and "time" in candles.columns:
        candles = candles.rename(columns={"time": "timestamp"})
    for column in ["open", "high", "low", "close"]:
        if column not in candles.columns:
            return pd.DataFrame()
        candles[column] = pd.to_numeric(candles[column], errors="coerce")

    candles = candles.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    if "timestamp" not in candles.columns:
        candles["timestamp"] = pd.RangeIndex(start=0, stop=len(candles), step=1)
    if "volume" not in candles.columns:
        candles["volume"] = 0

    return candles


def ema(df, period=21):
    return df["close"].ewm(span=period, adjust=False).mean()


def rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, math.nan)
    values = 100 - (100 / (1 + rs))
    values = values.mask((loss == 0) & (gain > 0), 100)
    values = values.mask((gain == 0) & (loss > 0), 0)
    return values.fillna(50)


def macd(df):
    macd_line = ema(df, 12) - ema(df, 26)
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(df, period=14):
    previous_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period).mean().bfill()


def adx(df, period=14):
    previous_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    up_move = df["high"].diff()
    down_move = -df["low"].diff()

    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)

    plus_mask = (up_move > down_move) & (up_move > 0)
    minus_mask = (down_move > up_move) & (down_move > 0)

    plus_dm[plus_mask] = up_move[plus_mask]
    minus_dm[minus_mask] = down_move[minus_mask]

    # Wilder's smoothing uses alpha=1/period
    str_smoothed = tr.ewm(alpha=1/period, adjust=False).mean()
    splus_dm = plus_dm.ewm(alpha=1/period, adjust=False).mean()
    sminus_dm = minus_dm.ewm(alpha=1/period, adjust=False).mean()

    plus_di = 100 * splus_dm / str_smoothed.replace(0, math.nan)
    minus_di = 100 * sminus_dm / str_smoothed.replace(0, math.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, math.nan)
    adx_values = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx_values.fillna(0), plus_di.fillna(0), minus_di.fillna(0)


def stochastic(df, k_period=14, d_period=3):
    lowest_low = df["low"].rolling(window=k_period).min()
    highest_high = df["high"].rolling(window=k_period).max()

    numerator = df["close"] - lowest_low
    denominator = highest_high - lowest_low

    stoch_k = 100 * numerator / denominator.replace(0, math.nan)
    stoch_k = stoch_k.fillna(50)

    stoch_d = stoch_k.rolling(window=d_period).mean().fillna(50)
    return stoch_k, stoch_d


def add_indicators(df):
    candles = prepare_candles(df)
    if candles.empty:
        return candles

    candles["ema21"] = ema(candles, 21)
    candles["ema50"] = ema(candles, 50)
    candles["ema200"] = ema(candles, 200)
    candles["rsi14"] = rsi(candles, 14)
    candles["atr14"] = atr(candles, 14)
    candles["macd"], candles["macd_signal"], candles["macd_hist"] = macd(candles)
    candles["bb_mid"] = candles["close"].rolling(20).mean()
    candles["bb_std"] = candles["close"].rolling(20).std().fillna(0)
    candles["bb_upper"] = candles["bb_mid"] + candles["bb_std"] * 2
    candles["bb_lower"] = candles["bb_mid"] - candles["bb_std"] * 2
    candles["bb_width"] = ((candles["bb_upper"] - candles["bb_lower"]) / candles["bb_mid"].replace(0, math.nan)).fillna(0)
    candles["volume_avg"] = candles["volume"].rolling(20).mean().fillna(candles["volume"])
    
    adx_vals, plus_di, minus_di = adx(candles, 14)
    candles["adx14"] = adx_vals
    candles["plus_di"] = plus_di
    candles["minus_di"] = minus_di
    
    stoch_k, stoch_d = stochastic(candles, 14, 3)
    candles["stoch_k"] = stoch_k
    candles["stoch_d"] = stoch_d

    return candles
