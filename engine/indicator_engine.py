from core.indicators import add_indicators


class IndicatorEngine:
    def enrich(self, candles):
        enriched = add_indicators(candles)
        if enriched.empty:
            return enriched, {}

        last = enriched.iloc[-1]
        indicators = {
            "ema21": round(float(last["ema21"]), 5),
            "ema50": round(float(last["ema50"]), 5),
            "ema200": round(float(last["ema200"]), 5),
            "rsi14": round(float(last["rsi14"]), 2),
            "macd": round(float(last["macd"]), 5),
            "macd_signal": round(float(last["macd_signal"]), 5),
            "macd_hist": round(float(last["macd_hist"]), 5),
            "atr14": round(float(last["atr14"]), 5),
            "bb_upper": round(float(last["bb_upper"]), 5) if not last["bb_upper"] != last["bb_upper"] else 0.0,
            "bb_lower": round(float(last["bb_lower"]), 5) if not last["bb_lower"] != last["bb_lower"] else 0.0,
            "bb_width": round(float(last["bb_width"]), 5) if not last["bb_width"] != last["bb_width"] else 0.0,
            "adx14": round(float(last["adx14"]), 2) if not last["adx14"] != last["adx14"] else 0.0,
            "plus_di": round(float(last["plus_di"]), 2) if not last["plus_di"] != last["plus_di"] else 0.0,
            "minus_di": round(float(last["minus_di"]), 2) if not last["minus_di"] != last["minus_di"] else 0.0,
            "stoch_k": round(float(last["stoch_k"]), 2) if not last["stoch_k"] != last["stoch_k"] else 50.0,
            "stoch_d": round(float(last["stoch_d"]), 2) if not last["stoch_d"] != last["stoch_d"] else 50.0,
            "volume_avg": round(float(last["volume_avg"]), 2),
        }
        return enriched, indicators
