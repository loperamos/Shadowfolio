"""Spreading observations published on some days (trading days, ECB working days) over every calendar day."""

from collections.abc import Iterable
from datetime import date, timedelta


def last_on_or_before[T](observations: Iterable[tuple[date, T]], start: date, end: date, lookback: timedelta) -> dict[date, T]:
    """For each day from `start` to `end`, the last observation on or before it, if no older than `lookback`.

    Days with none that recent are left out. `observations` must be oldest first.
    """
    pending = list(observations)
    result: dict[date, T] = {}
    latest: tuple[date, T] | None = None
    index = 0
    day = start
    while day <= end:
        while index < len(pending) and pending[index][0] <= day:
            latest = pending[index]
            index += 1
        if latest is not None and day - latest[0] <= lookback:
            result[day] = latest[1]
        day += timedelta(days=1)
    return result
