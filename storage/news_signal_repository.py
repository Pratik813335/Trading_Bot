"""
storage/news_signal_repository.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
JSONL persistence for NewsSignal objects.
Mirrors the pattern used by JsonlSignalRepository.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from config import NEWS_SIGNAL_HISTORY_PATH
from engine.models import NewsSignal


class NewsSignalRepository:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or NEWS_SIGNAL_HISTORY_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(self, signal: NewsSignal) -> None:
        record = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            **dataclasses.asdict(signal),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_recent(self, limit: int = 50) -> list[dict]:
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

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        records: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    # ------------------------------------------------------------------
    # Dedup
    # ------------------------------------------------------------------

    def is_duplicate(self, signal: NewsSignal) -> bool:
        """
        Returns True if an identical event+pair+trade_action was logged
        in the last 200 records (prevents double-logging the same event).
        """
        if not self.path.exists():
            return False
        check_key = (signal.event_name, signal.pair, signal.trade_action)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines[-200:]):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                rec_key = (
                    rec.get("event_name", ""),
                    rec.get("pair", ""),
                    rec.get("trade_action", ""),
                )
                if rec_key == check_key:
                    return True
            except json.JSONDecodeError:
                continue
        return False
