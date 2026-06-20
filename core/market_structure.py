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
    if len(df) < 10:
        return None

    previous_high = df["high"].iloc[-10:-1].max()
    previous_low = df["low"].iloc[-10:-1].min()
    last = df.iloc[-1]
    if last["close"] > previous_high:
        return "bullish_bos"
    if last["close"] < previous_low:
        return "bearish_bos"
    return None


def detect_liquidity(df):
    if len(df) < 5:
        return None

    previous_high = df["high"].iloc[-5:-1].max()
    previous_low = df["low"].iloc[-5:-1].min()
    current = df.iloc[-1]
    if current["high"] > previous_high and current["close"] < previous_high:
        return "liquidity_grab_sell"
    if current["low"] < previous_low and current["close"] > previous_low:
        return "liquidity_grab_buy"
    return None
