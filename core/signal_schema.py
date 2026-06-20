DEFAULT_SIGNAL_RESULT = {
    "signal": "HOLD",
    "confidence": 0,
    "entry": 0.0,
    "stop_loss": 0.0,
    "take_profit": 0.0,
    "risk_reward": 0.0,
    "trend": "unknown",
    "zones": [],
    "fib": None,
    "reasons": [],
    "warnings": [],
    "data_source": "unknown",
    "analysis_mode": "rule_based",
    "timeframes": {},
}


def build_signal_result(**overrides):
    result = DEFAULT_SIGNAL_RESULT.copy()
    result.update(overrides)

    result["signal"] = str(result["signal"]).upper()
    result["confidence"] = int(result["confidence"])
    result["entry"] = round(float(result["entry"]), 5)
    result["stop_loss"] = round(float(result["stop_loss"]), 5)
    result["take_profit"] = round(float(result["take_profit"]), 5)
    result["risk_reward"] = round(float(result["risk_reward"]), 2)
    result["trend"] = str(result["trend"]).lower()
    result["zones"] = list(result.get("zones") or [])
    result["fib"] = result.get("fib")
    result["reasons"] = list(result.get("reasons") or [])[:6]
    result["warnings"] = list(result.get("warnings") or [])[:6]
    result["data_source"] = str(result.get("data_source") or "unknown")
    result["analysis_mode"] = str(result.get("analysis_mode") or "rule_based")
    result["timeframes"] = dict(result.get("timeframes") or {})
    return result
