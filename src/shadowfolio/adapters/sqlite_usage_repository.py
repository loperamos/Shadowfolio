"""UsageRepository in a SQLite file: the wallets' database, in a table of its own."""

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import date
from pathlib import Path

from shadowfolio.domain.usage import Counter, UsageCount, UsageKey
from shadowfolio.ports.usage_repository import UsageRepository

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    day TEXT NOT NULL,
    user_id TEXT NOT NULL,
    source TEXT NOT NULL,
    counter TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (day, user_id, source, counter)
);
"""


class SqliteUsageRepository(UsageRepository):
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(_SCHEMA)

    def add(self, counts: Mapping[UsageKey, int]) -> None:
        rows = [(key.day.isoformat(), key.user_id, key.source, key.counter.value, count) for key, count in counts.items()]
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.executemany(
                "INSERT INTO usage VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (day, user_id, source, counter) DO UPDATE SET count = count + excluded.count",
                rows,
            )

    def between(self, start: date, end: date) -> list[UsageCount]:
        with closing(sqlite3.connect(self._path)) as conn:
            rows = conn.execute(
                "SELECT day, user_id, source, counter, count FROM usage WHERE day BETWEEN ? AND ? ORDER BY day, user_id, source, counter",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return [
            UsageCount(UsageKey(date.fromisoformat(day), user, source, Counter(counter)), count)
            for day, user, source, counter, count in rows
        ]
