import pandas as pd
from core.indicators import add_indicators
from core.market_structure import (
    detect_bos,
    detect_liquidity,
    detect_market_structure,
    detect_zones,
    nearest_zone,
)
from core.risk import MIN_RISK_REWARD, build_trade_plan, fibonacci_levels
from core.signal_schema import build_signal_result


def detect_fvg(df):
    if len(df) < 3:
        return None

    for i in range(len(df) - 1, 1, -1):
        previous = df.iloc[i - 2]
        current = df.iloc[i]
        if previous["high"] < current["low"]:
            return {"type": "bullish", "low": float(previous["high"]), "high": float(current["low"])}
        if previous["low"] > current["high"]:
            return {"type": "bearish", "low": float(current["high"]), "high": float(previous["low"])}

    return None


def candle_pattern(df):
    if len(df) < 2:
        return None

    current = df.iloc[-1]
    previous = df.iloc[-2]
    body = abs(current['close'] - current['open'])
    candle_range = max(current['high'] - current['low'], 0.0001)
    lower_wick = min(current['open'], current['close']) - current['low']
    upper_wick = current['high'] - max(current['open'], current['close'])
    avg_body = df['close'].sub(df['open']).abs().tail(14).mean()
    atr_val = float(df["atr14"].iloc[-1]) if ("atr14" in df.columns and not pd.isna(df["atr14"].iloc[-1])) else float((df["high"] - df["low"]).tail(14).mean())
    if pd.isna(atr_val) or atr_val <= 0:
        atr_val = 0.0001
    
    is_doji = body < avg_body * 0.12 and body < candle_range * 0.18 and candle_range > atr_val * 0.4

    # Check 3-candle continuation patterns first
    if len(df) >= 3:
        c1 = df.iloc[-3]
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]
        
        # Three White Soldiers
        if (c1["close"] > c1["open"] and 
            c2["close"] > c2["open"] and 
            c3["close"] > c3["open"]):
            if c3["close"] > c2["close"] > c1["close"]:
                if (c1["open"] <= c2["open"] <= c1["close"] and 
                    c2["open"] <= c3["open"] <= c2["close"]):
                    body2 = c2["close"] - c2["open"]
                    body3 = c3["close"] - c3["open"]
                    upper_wick2 = c2["high"] - c2["close"]
                    upper_wick3 = c3["high"] - c3["close"]
                    if upper_wick2 < body2 * 0.3 and upper_wick3 < body3 * 0.3:
                        return "three_white_soldiers"
                        
        # Three Black Crows
        if (c1["close"] < c1["open"] and 
            c2["close"] < c2["open"] and 
            c3["close"] < c3["open"]):
            if c3["close"] < c2["close"] < c1["close"]:
                if (c1["close"] <= c2["open"] <= c1["open"] and 
                    c2["close"] <= c3["open"] <= c2["open"]):
                    body2 = c2["open"] - c2["close"]
                    body3 = c3["open"] - c3["close"]
                    lower_wick2 = c2["close"] - c2["low"]
                    lower_wick3 = c3["close"] - c3["low"]
                    if lower_wick2 < body2 * 0.3 and lower_wick3 < body3 * 0.3:
                        return "three_black_crows"

    # Bullish Engulfing (check before Doji)
    if (current['close'] > current['open']
        and previous['close'] < previous['open']
        and current['close'] > previous['open']
        and current['open'] < previous['close']
        and body > avg_body * 0.8):
        return 'bullish_engulfing'
    # Bearish Engulfing
    if (current['close'] < current['open']
        and previous['close'] > previous['open']
        and current['close'] < previous['open']
        and current['open'] > previous['close']
        and body > avg_body * 0.8):
        return 'bearish_engulfing'
    # Hammer: small body, big lower wick, at bottom
    if lower_wick > body * 2.0 and upper_wick < body * 0.5 and not is_doji:
        return 'hammer'
    # Shooting Star: small body, big upper wick, at top
    if upper_wick > body * 2.0 and lower_wick < body * 0.5 and not is_doji:
        return 'shooting_star'
    # Doji — only if truly indecisive
    if is_doji:
        return 'doji'
    return None


def _score_single_timeframe(candles):
    base_result = build_signal_result(data_source="rule_engine")
    if candles.empty or len(candles) < 20:
        base_result["warnings"].append("Not enough clean candle data for professional analysis")
        return base_result

    price = float(candles["close"].iloc[-1])
    atr_value = float(candles["atr14"].iloc[-1] or 0)
    if atr_value <= 0:
        atr_value = max(float(candles["high"].tail(14).max() - candles["low"].tail(14).min()) / 14, 0.0001)

    structure, swings, structure_warning = detect_market_structure(candles)
    zones = detect_zones(candles, swings)
    fib = fibonacci_levels(candles, structure, swings) or {}
    FVG = detect_fvg(candles)
    bos = detect_bos(candles)
    liquidity = detect_liquidity(candles)
    pattern = candle_pattern(candles)

    bullish_score = 0
    bearish_score = 0
    reasons = []
    warnings = []

    if structure_warning:
        warnings.append(structure_warning)

    last = candles.iloc[-1]
    if last["close"] > last["ema50"] and last["close"] > last["ema200"]:
        bullish_score += 18
        reasons.append("Price is above EMA50 and EMA200")
    elif last["close"] < last["ema50"] and last["close"] < last["ema200"]:
        bearish_score += 18
        reasons.append("Price is below EMA50 and EMA200")
    else:
        warnings.append("EMA trend is mixed")

    if structure == "bullish":
        bullish_score += 20
        reasons.append("Market structure is bullish")
    elif structure == "bearish":
        bearish_score += 20
        reasons.append("Market structure is bearish")
    else:
        warnings.append("Market structure is ranging or unclear")

    if bos == "bullish_bos":
        bullish_score += 12
        reasons.append("Bullish break of structure detected")
    elif bos == "bearish_bos":
        bearish_score += 12
        reasons.append("Bearish break of structure detected")

    if FVG:
        is_unmitigated = (price > FVG["low"]) if FVG["type"] == "bullish" else (price < FVG["high"])
        if is_unmitigated:
            if FVG["type"] == "bullish":
                bullish_score += 8
                reasons.append("Bullish fair value gap is present (unmitigated)")
            elif FVG["type"] == "bearish":
                bearish_score += 8
                reasons.append("Bearish fair value gap is present (unmitigated)")

    if liquidity == "liquidity_grab_buy":
        bullish_score += 10
        reasons.append("Sell-side liquidity sweep and reclaim detected")
    elif liquidity == "liquidity_grab_sell":
        bearish_score += 10
        reasons.append("Buy-side liquidity sweep and rejection detected")

    if pattern in ["bullish_engulfing", "hammer", "three_white_soldiers"]:
        bullish_score += 10
        reasons.append(f"Bullish candle confirmation: {pattern.replace('_', ' ').title()}")
    elif pattern in ["bearish_engulfing", "shooting_star", "three_black_crows"]:
        bearish_score += 10
        reasons.append(f"Bearish candle confirmation: {pattern.replace('_', ' ').title()}")
    elif pattern == "doji":
        warnings.append("Doji candle shows indecision")

    if last["macd"] > last["macd_signal"]:
        bullish_score += 8
        reasons.append("MACD supports bullish momentum")
    elif last["macd"] < last["macd_signal"]:
        bearish_score += 8
        reasons.append("MACD supports bearish momentum")

    if last["rsi14"] > 70:
        warnings.append("RSI is overbought")
        bearish_score += 4
    elif last["rsi14"] < 30:
        warnings.append("RSI is oversold")
        bullish_score += 4

    if fib:
        in_ote = fib["ote_low"] <= price <= fib["ote_high"]
        if in_ote and structure == "bullish":
            bullish_score += 12
            reasons.append("Price is inside bullish Fibonacci OTE zone")
        elif in_ote and structure == "bearish":
            bearish_score += 12
            reasons.append("Price is inside bearish Fibonacci OTE zone")

    support = nearest_zone(zones, "support", price, below=True)
    resistance = nearest_zone(zones, "resistance", price, below=False)
    if support and abs(price - support["mid"]) <= atr_value * 1.5:
        bullish_score += 8
        reasons.append("Price is near a support zone")
    if resistance and abs(price - resistance["mid"]) <= atr_value * 1.5:
        bearish_score += 8
        reasons.append("Price is near a resistance zone")

    if bullish_score >= bearish_score + 15 and bullish_score >= 45:
        signal = "BUY"
        confidence = min(95, bullish_score)
    elif bearish_score >= bullish_score + 15 and bearish_score >= 45:
        signal = "SELL"
        confidence = min(95, bearish_score)
    else:
        signal = "HOLD"
        confidence = min(60, max(bullish_score, bearish_score))
        warnings.append("No trade: confirmations are not strong enough")

    stop_loss, take_profit, rr = build_trade_plan(signal, price, atr_value, zones, fib, nearest_zone)
    if signal in ["BUY", "SELL"] and rr < MIN_RISK_REWARD:
        warnings.append("No trade: risk reward is below 1:2")
        signal = "HOLD"

    return build_signal_result(
        signal=signal,
        confidence=confidence,
        entry=price,
        stop_loss=stop_loss if signal in ["BUY", "SELL"] else 0,
        take_profit=take_profit if signal in ["BUY", "SELL"] else 0,
        risk_reward=rr if signal in ["BUY", "SELL"] else 0,
        trend=structure,
        zones=zones,
        fib=fib,
        reasons=reasons,
        warnings=warnings,
        data_source="rule_engine",
    )


def generate_signal(df):
    candles = add_indicators(df)
    return _score_single_timeframe(candles)


def generate_mtf_signal(timeframe_map):
    if not timeframe_map:
        return build_signal_result(warnings=["No timeframe data supplied"], data_source="mtf_engine")

    timeframe_results = {}
    bullish_alignment = 0
    bearish_alignment = 0

    for timeframe, df in timeframe_map.items():
        result = generate_signal(df)
        timeframe_results[timeframe] = result
        if result["signal"] == "BUY" or result["trend"] == "bullish":
            bullish_alignment += 1
        if result["signal"] == "SELL" or result["trend"] == "bearish":
            bearish_alignment += 1

    priority = ["D", "240", "60", "15", "5"]
    primary_timeframe = next((tf for tf in priority if tf in timeframe_results), next(iter(timeframe_results)))
    primary_result = timeframe_results[primary_timeframe]
    reasons = list(primary_result["reasons"])
    warnings = list(primary_result["warnings"])

    if bullish_alignment and bearish_alignment:
        warnings.append("Multi-timeframe alignment is mixed")

    if bullish_alignment >= 2 and bullish_alignment > bearish_alignment and primary_result["signal"] != "SELL":
        signal = "BUY" if primary_result["signal"] != "HOLD" else "HOLD"
        confidence = min(95, primary_result["confidence"] + 5)
        trend = "bullish"
        reasons.append("Higher timeframes align bullish")
    elif bearish_alignment >= 2 and bearish_alignment > bullish_alignment and primary_result["signal"] != "BUY":
        signal = "SELL" if primary_result["signal"] != "HOLD" else "HOLD"
        confidence = min(95, primary_result["confidence"] + 5)
        trend = "bearish"
        reasons.append("Higher timeframes align bearish")
    else:
        signal = "HOLD"
        confidence = min(65, primary_result["confidence"])
        trend = primary_result["trend"]
        warnings.append("No trade: higher timeframe alignment is weak")

    return build_signal_result(
        signal=signal,
        confidence=confidence,
        entry=primary_result["entry"],
        stop_loss=primary_result["stop_loss"] if signal in ["BUY", "SELL"] else 0,
        take_profit=primary_result["take_profit"] if signal in ["BUY", "SELL"] else 0,
        risk_reward=primary_result["risk_reward"] if signal in ["BUY", "SELL"] else 0,
        trend=trend,
        zones=primary_result["zones"],
        fib=primary_result["fib"],
        reasons=reasons,
        warnings=warnings,
        data_source="mtf_engine",
        analysis_mode="multi_timeframe",
        timeframes=timeframe_results,
    )
