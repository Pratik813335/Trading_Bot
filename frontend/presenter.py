def signal_to_panel_rows(bundle):
    signal = bundle.signal
    ai = bundle.ai_explanation
    actionable = signal.signal in ["BUY", "SELL", "STRONG_BUY"]
    return [
        ("Symbol", signal.symbol),
        ("Timeframe", signal.timeframe),
        ("Feed Source", signal.feed_source),
        ("Last Candle", signal.candle_timestamp),
        ("Signal", signal.signal),
        ("Trade Status", "Approved" if actionable else "Blocked / No Trade"),
        ("Confidence", f"{signal.confidence}%"),
        ("Trend", signal.structure["trend"]),
        ("Phase", signal.structure["phase"]),
        ("Structure Strength", signal.structure["strength"]),
        ("Chart Sync", f"{signal.chart_sync}%"),
        ("Gemini Provider", ai.get("provider", "gemini")),
        ("Gemini Status", ai.get("status", "unknown")),
        ("Gemini Validation", "passed" if ai.get("validation_passed") else "not_passed"),
    ]
