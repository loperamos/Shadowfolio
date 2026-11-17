"""When the app runs the jobs itself: filling due orders every minute, and the sync of splits and dividends when it
starts (covering a day it was off) and then each day at 07:00 New York time, before the US market opens, after the
providers have published the night's corporate actions."""

from datetime import UTC, datetime, timedelta

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.interfaces.jobs import Jobs


class Counted:
    def __init__(self) -> None:
        self.syncs = 0
        self.fills = 0

    def all_wallets(self) -> None:
        self.syncs += 1

    def fill_all(self) -> None:
        self.fills += 1


def test_orders_fill_every_tick_and_the_sync_runs_at_start_then_daily_at_7_new_york() -> None:
    clock = FixedClock(datetime(2026, 11, 17, 10, 0, tzinfo=UTC))  # 05:00 in New York
    counted = Counted()
    jobs = Jobs(counted, counted, clock)

    jobs.tick()  # starting: sync, as a day may have been missed
    assert (counted.syncs, counted.fills) == (1, 1)
    clock.set(datetime(2026, 11, 17, 11, 59, tzinfo=UTC))  # 06:59: not yet
    jobs.tick()
    assert (counted.syncs, counted.fills) == (1, 2)
    clock.set(datetime(2026, 11, 17, 12, 0, tzinfo=UTC))  # 07:00 in New York
    jobs.tick()
    jobs.tick()
    assert (counted.syncs, counted.fills) == (2, 4)  # once that day
    clock.set(datetime(2026, 11, 18, 12, 0, tzinfo=UTC) + timedelta(minutes=1))
    jobs.tick()
    assert counted.syncs == 3


def test_a_failing_job_does_not_stop_the_others() -> None:
    class Failing(Counted):
        def all_wallets(self) -> None:
            raise RuntimeError("provider down")

    failing = Failing()
    jobs = Jobs(failing, failing, FixedClock(datetime(2026, 11, 17, 10, 0, tzinfo=UTC)))

    jobs.tick()

    assert failing.fills == 1
