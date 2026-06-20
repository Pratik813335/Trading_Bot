import json
from datetime import datetime, timezone
from pathlib import Path

from config import SIGNAL_HISTORY_PATH


def append_signal_history(symbol, timeframe, signal_result):
    history_path = Path(SIGNAL_HISTORY_PATH)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": signal_result["signal"],
        "confidence": signal_result["confidence"],
        "entry": signal_result["entry"],
        "stop_loss": signal_result["stop_loss"],
        "take_profit": signal_result["take_profit"],
        "risk_reward": signal_result["risk_reward"],
        "trend": signal_result["trend"],
        "data_source": signal_result.get("data_source", "unknown"),
        "analysis_mode": signal_result.get("analysis_mode", "rule_based"),
        "reasons": signal_result.get("reasons", []),
        "warnings": signal_result.get("warnings", []),
    }

    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def read_recent_history(limit=20):
    history_path = Path(SIGNAL_HISTORY_PATH)
    if not history_path.exists():
        return []

    lines = history_path.read_text(encoding="utf-8").splitlines()
    records = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(records) >= limit:
            break
    return records
