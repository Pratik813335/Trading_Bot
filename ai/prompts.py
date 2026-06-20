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
            "You are a trading risk-review assistant. Review the rule-based trade. "
            "Do not create a new trade, do not change BUY/SELL direction, and do not override risk rules. "
            "Only validate the existing setup, highlight conflicts, and return strict JSON."
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
