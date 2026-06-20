import json
from datetime import datetime, timezone
from pathlib import Path

from config import SIGNAL_HISTORY_PATH


class JsonlSignalRepository:
    def __init__(self, path=None):
        self.path = Path(path or SIGNAL_HISTORY_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def is_duplicate(self, payload):
        """Return True if a record with the same symbol+candle_timestamp+signal+entry already exists."""
        if not self.path.exists():
            return False
        check_key = (
            str(payload.get("symbol", "")),
            str(payload.get("candle_timestamp", "")),
            str(payload.get("signal", "")),
            str(payload.get("entry", "")),
        )
        # Read last 200 lines (most recent first) to detect duplicates efficiently
        lines = self.path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines[-200:]):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                rec_key = (
                    str(rec.get("symbol", "")),
                    str(rec.get("candle_timestamp", "")),
                    str(rec.get("signal", "")),
                    str(rec.get("entry", "")),
                )
                if rec_key == check_key:
                    return True
            except json.JSONDecodeError:
                continue
        return False

    def append(self, payload):
        record = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def read_recent(self, limit=20):
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(records) >= limit:
                break
        return records
