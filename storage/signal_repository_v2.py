import json
from datetime import datetime, timezone
from pathlib import Path

from config import SIGNAL_HISTORY_PATH

# Signals that represent a directional trade (not neutral/no-trade)
_TRADE_SIGNALS = {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}


def _direction(signal_str):
    """Return 'BUY' or 'SELL' for directional signals, else None."""
    s = str(signal_str).upper()
    if s in ("BUY", "STRONG_BUY"):
        return "BUY"
    if s in ("SELL", "STRONG_SELL"):
        return "SELL"
    return None


class JsonlSignalRepository:
    def __init__(self, path=None):
        self.path = Path(path or SIGNAL_HISTORY_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_active_position(self, symbol: str) -> dict | None:
        """Return the most-recent open (no outcome) trade record for *symbol*.

        Scans the JSONL file in reverse so the first matching record found is
        the most recent.  Returns None if there is no open position.
        """
        if not self.path.exists():
            return None

        symbol_upper = symbol.upper()
        lines = self.path.read_text(encoding="utf-8").splitlines()

        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            if str(rec.get("symbol", "")).upper() != symbol_upper:
                continue
            if rec.get("signal") not in _TRADE_SIGNALS:
                continue
            # A position is "open" when it has no outcome stamped on it
            if rec.get("outcome") in (None, "", "OPEN"):
                return rec

        return None

    def close_position(self, logged_at_iso: str, outcome: str) -> bool:
        """Stamp *outcome* onto the record identified by *logged_at_iso*.

        Rewrites the entire JSONL file in place.  Safe for the file sizes
        typical of this application (<= a few thousand lines).

        Returns True if the record was found and updated, False otherwise.
        """
        if not self.path.exists():
            return False

        # These are terminal states — do not overwrite them
        _FINAL = {"TP_HIT", "SL_HIT", "CLOSED_BY_SIGNAL_CHANGE", "TRADE_REMOVED"}

        lines = self.path.read_text(encoding="utf-8").splitlines()
        updated = False
        new_lines = []

        for line in lines:
            if not line.strip():
                new_lines.append(line)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                new_lines.append(line)
                continue

            if (rec.get("logged_at") == logged_at_iso
                    and rec.get("outcome") not in _FINAL):
                rec["outcome"] = outcome
                rec["closed_at"] = datetime.now(timezone.utc).isoformat()
                new_lines.append(json.dumps(rec))
                updated = True
            else:
                new_lines.append(line)

        if updated:
            self.path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        return updated

    def is_duplicate(self, payload: dict) -> bool:
        """Return True if there is already an open position in the same
        direction for this symbol.  Used as a fast short-circuit guard before
        the richer position-management logic in the orchestrator.
        """
        symbol = str(payload.get("symbol", "")).upper()
        new_dir = _direction(payload.get("signal", ""))
        if new_dir is None:
            return False  # not a trade signal — never block

        active = self.get_active_position(symbol)
        if active is None:
            return False  # no open position → allow log

        active_dir = _direction(active.get("signal", ""))
        # Block only if the direction is the same (same open trade still running)
        return active_dir == new_dir

    def append(self, payload: dict) -> str:
        """Append a new record and return its logged_at ISO timestamp."""
        logged_at = datetime.now(timezone.utc).isoformat()
        record = {"logged_at": logged_at, "outcome": "OPEN", **payload}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return logged_at

    def read_recent(self, limit: int = 20) -> list[dict]:
        """Return the most recent *limit* records (newest first)."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[dict] = []
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
