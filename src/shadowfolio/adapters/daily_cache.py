"""Daily market data (closes, exchange rates) kept in a SQLite file, so each day is fetched from its provider once.

A past day's value never changes (closes are asked for unadjusted); the current day's can, until the market closes or
the day's rate is published, so days from the day of a fetch on are fetched again once FRESH_FOR has passed. Per series
(a symbol, a currency pair) the file holds one span of days already fetched (days in it without a value are known to
have none) and its values. The file only holds copies: deleting it loses nothing.

Entries are kept per source (e.g. "alpaca/iex"): data from one provider, plan or feed never answers for another, as
their licenses differ.
"""

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

from shadowfolio.ports.clock import Clock

# How long values of the day of a fetch, or later, are trusted before being fetched again.
FRESH_FOR = timedelta(minutes=15)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fetched_days (
    source TEXT NOT NULL,
    series TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (source, series)
);
CREATE TABLE IF NOT EXISTS daily_values (
    source TEXT NOT NULL,
    series TEXT NOT NULL,
    day TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (source, series, day)
);
"""

# A day's value as stored: its fields as strings (or None), e.g. a close's price, currency and time.
type Fields = list[str | None]


class DailyCache[T]:
    def __init__(self, path: Path, source: str, clock: Clock, encode: Callable[[T], Fields], decode: Callable[[Fields], T]) -> None:
        """`path` is the cache file, created if missing; `source` names the provider and its plan or feed."""
        self._path = path
        self._source = source
        self._clock = clock
        self._encode = encode
        self._decode = decode
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(_SCHEMA)

    def between(self, series: str, start: date, end: date, fetch: Callable[[date, date], dict[date, T]]) -> dict[date, T]:
        """The values of `series` from `start` to `end`, fetching (with `fetch(first, last)`) only the days missing."""
        key = (self._source, series)
        with closing(sqlite3.connect(self._path)) as conn, conn:
            fetched = conn.execute("SELECT start, end, fetched_at FROM fetched_days WHERE source = ? AND series = ?", key).fetchone()
            missing = self._missing(fetched, start, end)
            if missing is not None:
                first, last = missing
                values = fetch(first, last)
                conn.execute(
                    "DELETE FROM daily_values WHERE source = ? AND series = ? AND day BETWEEN ? AND ?",
                    (*key, first.isoformat(), last.isoformat()),
                )
                conn.executemany(
                    "INSERT INTO daily_values VALUES (?, ?, ?, ?)",
                    [(*key, day.isoformat(), json.dumps(self._encode(value))) for day, value in values.items()],
                )
                if fetched is not None:
                    first, last = min(first, date.fromisoformat(fetched[0])), max(last, date.fromisoformat(fetched[1]))
                conn.execute(
                    "INSERT OR REPLACE INTO fetched_days VALUES (?, ?, ?, ?, ?)",
                    (*key, first.isoformat(), last.isoformat(), self._clock.now().isoformat()),
                )
            rows = conn.execute(
                "SELECT day, value FROM daily_values WHERE source = ? AND series = ? AND day BETWEEN ? AND ?",
                (*key, start.isoformat(), end.isoformat()),
            )
            return {date.fromisoformat(day): self._decode(json.loads(value)) for day, value in rows}

    def _missing(self, fetched: tuple[str, str, str] | None, start: date, end: date) -> tuple[date, date] | None:
        """The days to fetch for `start` to `end`, given the span already fetched; None when the cache has them all.
        Days are fetched up to the end of the span too, so the span stays one block of days."""
        if fetched is None:
            return start, end
        first, last, fetched_at = date.fromisoformat(fetched[0]), date.fromisoformat(fetched[1]), datetime.fromisoformat(fetched[2])
        if start < first:
            return start, max(end, last)
        # Days from the day of the fetch on may have changed since, once they are no longer fresh.
        stale = last + timedelta(days=1)
        if self._clock.now() - fetched_at >= FRESH_FOR:
            stale = min(stale, fetched_at.date())
        return (stale, max(end, last)) if stale <= end else None
