MIN_RISK_REWARD = 2.0


def fibonacci_levels(df, structure="bullish", swings=None):
    # Detect swings dynamically if not provided
    if not swings:
        from core.market_structure import find_swings
        swings = find_swings(df, lookback=3)

    swing_highs = sorted([s for s in swings if s["type"] == "high"], key=lambda s: s["index"])
    swing_lows = sorted([s for s in swings if s["type"] == "low"], key=lambda s: s["index"])

    if not swing_highs or not swing_lows:
        # Fallback to absolute high/low of last 100 bars
        high = float(df["high"].tail(100).max())
        low = float(df["low"].tail(100).min())
    else:
        if structure == "bearish":
            # Retracement leg starts at High and ends at Low
            # Find the latest swing low
            latest_low = swing_lows[-1]
            low = float(latest_low["price"])
            # Find the highest swing high before this low
            preceding_highs = [s for s in swing_highs if s["index"] < latest_low["index"]]
            if preceding_highs:
                high = float(max(preceding_highs, key=lambda s: s["price"])["price"])
            else:
                high = float(swing_highs[-1]["price"])
        else:
            # Retracement leg starts at Low and ends at High
            # Find the latest swing high
            latest_high = swing_highs[-1]
            high = float(latest_high["price"])
            # Find the lowest swing low before this high
            preceding_lows = [s for s in swing_lows if s["index"] < latest_high["index"]]
            if preceding_lows:
                low = float(min(preceding_lows, key=lambda s: s["price"])["price"])
            else:
                low = float(swing_lows[-1]["price"])

    if high <= low:
        # Emergency backup to prevent returning None
        high = float(df["high"].tail(50).max())
        low = float(df["low"].tail(50).min())
        if high <= low:
            return None

    diff = high - low
    if structure == "bearish":
        levels = {
            "0.0": high,
            "0.236": low + diff * 0.236,
            "0.382": low + diff * 0.382,
            "0.5": low + diff * 0.5,
            "0.618": low + diff * 0.618,
            "0.705": low + diff * 0.705,
            "0.786": low + diff * 0.786,
            "0.886": low + diff * 0.886,
            "1.0": low,
            "ote_low": low + diff * 0.705,
            "ote_high": low + diff * 0.786,
            "ext_1.272": low - diff * 0.272,
            "ext_1.618": low - diff * 0.618,
        }
    else:
        levels = {
            "0.0": low,
            "0.236": high - diff * (1 - 0.236),
            "0.382": high - diff * 0.382,
            "0.5": high - diff * 0.5,
            "0.618": high - diff * 0.618,
            "0.705": high - diff * 0.705,
            "0.786": high - diff * 0.786,
            "0.886": high - diff * 0.886,
            "1.0": high,
            "ote_low": high - diff * 0.786,
            "ote_high": high - diff * 0.705,
            "ext_1.272": high + diff * 0.272,
            "ext_1.618": high + diff * 0.618,
        }

    levels["swing_high"] = high
    levels["swing_low"] = low
    return levels


def risk_reward(entry, stop_loss, take_profit, signal):
    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    if risk <= 0:
        return 0
    if signal == "BUY" and not (stop_loss < entry < take_profit):
        return 0
    if signal == "SELL" and not (take_profit < entry < stop_loss):
        return 0
    return round(reward / risk, 2)


def build_trade_plan(signal, price, atr_value, zones, fib, nearest_zone):
    fib = fib or {}
    if signal == "BUY":
        support = nearest_zone(zones, "support", price, below=True)
        resistance = nearest_zone(zones, "resistance", price, below=False)
        structural_sl = support["low"] if support else price - atr_value * 1.5
        stop_loss = min(structural_sl, price - atr_value * 1.5)
        take_profit = resistance["mid"] if resistance else fib.get("ext_1.272", price + atr_value * 3)
        take_profit = max(take_profit, price + abs(price - stop_loss) * MIN_RISK_REWARD)
    elif signal == "SELL":
        resistance = nearest_zone(zones, "resistance", price, below=False)
        support = nearest_zone(zones, "support", price, below=True)
        structural_sl = resistance["high"] if resistance else price + atr_value * 1.5
        stop_loss = max(structural_sl, price + atr_value * 1.5)
        take_profit = support["mid"] if support else fib.get("ext_1.272", price - atr_value * 3)
        take_profit = min(take_profit, price - abs(stop_loss - price) * MIN_RISK_REWARD)
    else:
        stop_loss = 0
        take_profit = 0

    rr = risk_reward(price, stop_loss, take_profit, signal) if signal in ["BUY", "SELL"] else 0
    return round(stop_loss, 5), round(take_profit, 5), rr
