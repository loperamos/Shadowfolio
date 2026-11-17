"""The system's jobs, run by the app itself when deployed (SHADOWFOLIO_RUN_JOBS): filling due orders every minute,
and the sync of splits and dividends when it starts (covering a day it was off) and then each day at 07:00 New York
time, before the US market opens, after the providers have published the night's corporate actions. A failing job is
logged and tried again at its next turn; it never stops the others."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from shadowfolio.ports.clock import Clock

SYNC_ZONE = ZoneInfo("America/New_York")
SYNC_AT = time(7, 0)
TICK_SECONDS = 60

log = logging.getLogger(__name__)


class DailySync(Protocol):
    def all_wallets(self) -> object: ...


class OrderFilling(Protocol):
    def fill_all(self) -> object: ...


class Jobs:
    def __init__(self, sync: DailySync, orders: OrderFilling, clock: Clock) -> None:
        self._sync = sync
        self._orders = orders
        self._clock = clock
        self._next_sync: datetime | None = None  # None until the first run, at start

    def tick(self) -> None:
        """Run what is due now: the sync when its time has come, and filling due orders."""
        now = self._clock.now()
        if self._next_sync is None or now >= self._next_sync:
            self._run("sync", self._sync.all_wallets)
            self._next_sync = _next_sync_after(now)
        self._run("order filling", self._orders.fill_all)

    async def run_forever(self) -> None:
        """Tick every minute, in a worker thread so requests are never held up."""
        while True:
            await asyncio.to_thread(self.tick)
            await asyncio.sleep(TICK_SECONDS)

    def _run(self, name: str, job: Callable[[], object]) -> None:
        try:
            job()
        except Exception:
            log.exception("the %s job failed; trying again at its next turn", name)


def _next_sync_after(moment: datetime) -> datetime:
    """The first 07:00 in New York after `moment`."""
    local = moment.astimezone(SYNC_ZONE)
    today = datetime.combine(local.date(), SYNC_AT, tzinfo=SYNC_ZONE)
    return today if today > local else datetime.combine(local.date() + timedelta(days=1), SYNC_AT, tzinfo=SYNC_ZONE)
