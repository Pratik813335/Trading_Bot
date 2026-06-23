def find_swings(df, lookback=2):
    swings = []
    if len(df) < lookback * 2 + 1:
        return swings

    for index in range(lookback, len(df) - lookback):
        window = df.iloc[index - lookback : index + lookback + 1]
        candle = df.iloc[index]
        if candle["high"] == window["high"].max():
            swings.append({"type": "high", "index": index, "price": float(candle["high"])})
        if candle["low"] == window["low"].min():
            swings.append({"type": "low", "index": index, "price": float(candle["low"])})

    return swings


def detect_market_structure(df):
    swings = find_swings(df)
    highs = [s for s in swings if s["type"] == "high"][-3:]
    lows = [s for s in swings if s["type"] == "low"][-3:]

    if len(highs) < 2 or len(lows) < 2:
        recent_close = df["close"].iloc[-1]
        previous_close = df["close"].iloc[-min(len(df), 20)]
        fallback = "bullish" if recent_close > previous_close else "bearish"
        return fallback, swings, "Structure fallback used because swing history is limited"

    higher_highs = highs[-1]["price"] > highs[-2]["price"]
    higher_lows = lows[-1]["price"] > lows[-2]["price"]
    lower_highs = highs[-1]["price"] < highs[-2]["price"]
    lower_lows = lows[-1]["price"] < lows[-2]["price"]

    if higher_highs and higher_lows:
        return "bullish", swings, None
    if lower_highs and lower_lows:
        return "bearish", swings, None
    return "range", swings, "Market structure is mixed or ranging"


def _merge_zone(zones, price, zone_type, tolerance):
    for zone in zones:
        if zone["type"] == zone_type and abs(zone["mid"] - price) <= tolerance:
            zone["low"] = min(zone["low"], price)
            zone["high"] = max(zone["high"], price)
            zone["mid"] = (zone["low"] + zone["high"]) / 2
            zone["touches"] += 1
            return

    zones.append(
        {
            "type": zone_type,
            "low": price - tolerance,
            "high": price + tolerance,
            "mid": price,
            "touches": 1,
        }
    )


def detect_zones(df, swings=None):
    if swings is None:
        swings = find_swings(df)

    average_atr = float(df["atr14"].tail(20).mean()) if "atr14" in df else 0
    price_range = float(df["high"].max() - df["low"].min())
    tolerance = max(average_atr * 0.35, price_range * 0.003, 0.0001)
    zones = []

    for swing in swings:
        zone_type = "resistance" if swing["type"] == "high" else "support"
        _merge_zone(zones, swing["price"], zone_type, tolerance)

    zones = sorted(zones, key=lambda z: (z["touches"], z["mid"]), reverse=True)
    return zones[:8]


def nearest_zone(zones, zone_type, price, below=True):
    typed = [zone for zone in zones if zone["type"] == zone_type]
    if below:
        typed = [zone for zone in typed if zone["mid"] <= price]
        return max(typed, key=lambda z: z["mid"]) if typed else None

    typed = [zone for zone in typed if zone["mid"] >= price]
    return min(typed, key=lambda z: z["mid"]) if typed else None


def detect_bos(df):
    """
    SMC-grade Break of Structure detection.

    A valid BOS requires:
    1. At least one confirmed swing high / swing low in the lookback window.
    2. The most-recent *closed* candle's close decisively breaks beyond that
       structural level (not just a wick poke).
    3. The breakout displacement is at least a fraction of ATR14 so micro-noise
       is filtered out.

    Returns:
        'bullish_bos'  – close broke above last significant swing high
        'bearish_bos'  – close broke below last significant swing low
        None           – no clean BOS found
    """
    min_bars = 15
    if len(df) < min_bars:
        return None

    # ATR-based displacement threshold (at least 10 % of ATR14)
    atr = float(df["atr14"].iloc[-1]) if "atr14" in df.columns else 0.0
    if atr <= 0:
        atr = float((df["high"].tail(14).max() - df["low"].tail(14).min()) / 14)
    min_displacement = atr * 0.10

    # Collect confirmed swing highs and lows in a 50-bar lookback window
    # (exclude the last candle so we measure the break from a prior structure)
    lookback = df.iloc[-(min(50, len(df))):-1].reset_index(drop=True)
    swings = find_swings(lookback, lookback=2)

    swing_highs = sorted([s for s in swings if s["type"] == "high"], key=lambda s: s["index"])
    swing_lows  = sorted([s for s in swings if s["type"] == "low"],  key=lambda s: s["index"])

    last_close = float(df["close"].iloc[-1])

    # --- Bullish BOS: close breaks above the most recent confirmed swing high ---
    if swing_highs:
        # Use the most recent swing high as the structural level
        key_level_high = float(swing_highs[-1]["price"])
        if last_close > key_level_high + min_displacement:
            return "bullish_bos"

    # --- Bearish BOS: close breaks below the most recent confirmed swing low ---
    if swing_lows:
        key_level_low = float(swing_lows[-1]["price"])
        if last_close < key_level_low - min_displacement:
            return "bearish_bos"

    return None


def detect_liquidity(df):
    """
    SMC-grade Liquidity Sweep (Stop Hunt) detection.

    A liquidity sweep requires:
    1. A confirmed swing high or swing low in recent price history (the pool of
       liquidity — stops cluster above highs / below lows).
    2. The current candle's *wick* pierces that level (engineered stop run).
    3. The candle *closes back* on the other side of that level (rejection /
       reclaim), confirming smart money absorbed the stops.
    4. The wick extension beyond the level is at least 15 % of ATR14 to avoid
       micro-noise triggers.

    Returns:
        'liquidity_grab_buy'   – sell-side sweep → bullish continuation expected
        'liquidity_grab_sell'  – buy-side sweep  → bearish continuation expected
        None                   – no sweep detected
    """
    min_bars = 10
    if len(df) < min_bars:
        return None

    # ATR filter
    atr = float(df["atr14"].iloc[-1]) if "atr14" in df.columns else 0.0
    if atr <= 0:
        atr = float((df["high"].tail(14).max() - df["low"].tail(14).min()) / 14)
    min_wick = atr * 0.15

    # Scan multiple lookback windows for robustness: 5, 10, 20 bars
    current = df.iloc[-1]
    cur_high  = float(current["high"])
    cur_low   = float(current["low"])
    cur_close = float(current["close"])

    for window_size in [5, 10, 20]:
        window = df.iloc[-(window_size + 1):-1]   # exclude current candle
        if window.empty:
            continue

        prior_high = float(window["high"].max())
        prior_low  = float(window["low"].min())

        # --- Sell-side liquidity sweep (below swing lows) → bullish reversal ---
        # Wick pierces below prior_low AND close reclaims above prior_low
        if cur_low < prior_low and cur_close > prior_low:
            wick_extension = prior_low - cur_low
            if wick_extension >= min_wick:
                return "liquidity_grab_buy"

        # --- Buy-side liquidity sweep (above swing highs) → bearish reversal ---
        # Wick pierces above prior_high AND close falls back below prior_high
        if cur_high > prior_high and cur_close < prior_high:
            wick_extension = cur_high - prior_high
            if wick_extension >= min_wick:
                return "liquidity_grab_sell"

    return None


def detect_order_blocks(df, n_candles=50):
    order_blocks = []
    if len(df) < 5:
        return order_blocks

    for i in range(2, min(n_candles, len(df) - 1)):
        candle = df.iloc[-i]
        next_candle = df.iloc[-i + 1]
        
        # Bullish OB: bearish candle followed by strong bullish move
        if (candle['close'] < candle['open']  # bearish OB candle
            and next_candle['close'] > candle['high']  # strong impulse above
            and (next_candle['close'] - next_candle['open']) > (candle['high'] - candle['low'])):
            order_blocks.append({
                'type': 'bullish_ob',
                'high': float(candle['high']),
                'low': float(candle['low']),
                'timestamp': str(candle['timestamp'])
            })
            
        # Bearish OB: bullish candle followed by strong bearish move
        elif (candle['close'] > candle['open']  # bullish OB candle
              and next_candle['close'] < candle['low']  # strong impulse below
              and (candle['open'] - candle['close']) > (candle['high'] - candle['low'])):
            order_blocks.append({
                'type': 'bearish_ob',
                'high': float(candle['high']),
                'low': float(candle['low']),
                'timestamp': str(candle['timestamp'])
            })
            
    return order_blocks

