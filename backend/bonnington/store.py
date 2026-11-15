"""Persistent summons log: the Britney grudge counter and summons context."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

SummonKind = Literal["britney", "bonnington", "hotkey"]

WINDOW_SECONDS = 600.0


@dataclass(frozen=True)
class SummonsContext:
    kind: SummonKind
    britney_count: int
    seconds_since_last: float | None
    summons_last_10min: int
    local_time: datetime


class GrudgeStore:
    def __init__(self, db_path: Path) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path)
        self._db.execute("CREATE TABLE IF NOT EXISTS summons (ts REAL NOT NULL, kind TEXT NOT NULL)")
        self._db.commit()

    def britney_count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM summons WHERE kind = 'britney'").fetchone()[0]

    def summons_count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM summons").fetchone()[0]

    def record_summons(self, kind: SummonKind, now: datetime) -> SummonsContext:
        ts = now.timestamp()
        last = self._db.execute("SELECT MAX(ts) FROM summons").fetchone()[0]
        self._db.execute("INSERT INTO summons (ts, kind) VALUES (?, ?)", (ts, kind))
        self._db.commit()
        recent = self._db.execute(
            "SELECT COUNT(*) FROM summons WHERE ts >= ?", (ts - WINDOW_SECONDS,)
        ).fetchone()[0]
        return SummonsContext(
            kind=kind,
            britney_count=self.britney_count(),
            seconds_since_last=None if last is None else ts - last,
            summons_last_10min=recent,
            local_time=now,
        )
