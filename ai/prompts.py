def build_gemini_validation_prompt(symbol, timeframe, trade_payload, candles, sync_status):
    latest = candles.tail(5).copy() if hasattr(candles, "tail") else []
    if hasattr(latest, "to_dict"):
        if "timestamp" in latest.columns:
            latest["timestamp"] = latest["timestamp"].astype(str)
        recent_candles = latest.to_dict(orient="records")
    else:
        recent_candles = []

    return {
        "system": (
            "You are a professional trading risk-review assistant. You are trained on the top 5 Forex strategies:\n"
            "1. Trend Following: Requires 50/200 EMA crossover/alignment (EMA50 > EMA200 for BUY, < for SELL) AND ADX > 25 (strong trend).\n"
            "2. Quick Scalper: Requires Bollinger Band Squeeze (narrow width) and Stochastic crossover in oversold (<25 for BUY) or overbought (>75 for SELL) zones. SL must be tight (5-10 pips).\n"
            "3. Range Trading: Price must touch support (BUY) or resistance (SELL) zone, RSI must be oversold (<35) or overbought (>65), and ADX < 20 (ranging/flat trend).\n"
            "4. Breakout Trading: Price must close beyond key S/R level with a volume spike (>1.4x average).\n"
            "5. Carry Trade: Requires positive interest rate differential (base rate > quote rate for BUY, quote rate > base rate for SELL) AND stable/low volatility (ATR not spiking).\n"
            "Evaluate the trade_payload against these strategy rules. Highlight conflicts, warn of fakeouts, indicator reversals, "
            "and adjust confidence score (confidence_adjustment) between -20 and +10. Return your response in strict JSON."
        ),
        "user": {
            "symbol": symbol,
            "timeframe": timeframe,
            "trade_payload": trade_payload,
            "sync_status": {
                "provider": sync_status.provider,
                "match_percentage": sync_status.match_percentage,
                "latency_ms": sync_status.latency_ms,
                "missing_candles": sync_status.missing_candles,
            },
            "recent_candles": recent_candles,
            "required_fields": {
                "status": "validated | caution | rejected",
                "validation_passed": "boolean",
                "summary": "string",
                "warnings": ["string"],
                "risks": ["string"],
                "confidence_adjustment": "integer between -20 and 10",
            },
        },
    }
