"""How a wallet, or a benchmark, did over a period: its gain, and two standard returns.

- The time-weighted return ignores when and how much money was put in or taken out: it chains each day's growth, so it
  measures the choices made (what was held), and compares wallets and benchmarks fairly.
- The money-weighted return (an internal rate of return) includes them: the steady rate at which the money put in
  would have grown into the end value, so it measures the actual result, timing included.

Both run from the value at the end of the day before the period (or its first valued day) to its last valued day.
Days that could not be valued are skipped: money moved on them counts at the next valued day.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

DAYS_PER_YEAR = 365
# Bounds for the daily money-weighted rate (-99% to +100% a day) and how closely it is solved.
LOWEST_DAILY_RATE = Decimal("-0.99")
HIGHEST_DAILY_RATE = Decimal(1)
SOLVER_STEPS = 200


@dataclass(frozen=True)
class DayValue:
    day: date
    value: Decimal | None  # at the end of the day, money moved that day included; None when it could not be valued
    flow: Decimal  # money put in (positive) or taken out (negative) that day


@dataclass(frozen=True)
class Performance:
    start_day: date  # the day whose end value the period starts from
    end_day: date  # its last valued day
    start_value: Decimal
    end_value: Decimal
    net_flows: Decimal  # money put in less money taken out after the start
    gain: Decimal  # end value - start value - net flows
    time_weighted: Decimal  # over the period, as a ratio (0.21 for +21%)
    time_weighted_per_year: Decimal | None  # only for periods of a year or more
    money_weighted: Decimal | None  # over the period; None when no rate explains the end value
    money_weighted_per_year: Decimal | None  # only for periods of a year or more


def performance(points: Sequence[DayValue], start: date, end: date) -> Performance | None:
    """How it did from `start` to `end` (both included), given its daily values oldest first. None when no day in the
    period could be valued."""
    in_period = [point for point in points if start - timedelta(days=1) <= point.day <= end]
    valued = [index for index, point in enumerate(in_period) if point.value is not None]
    if not valued:
        return None
    base = in_period[valued[0]]
    assert base.value is not None
    last_value = base.value
    end_point = base
    growth = Decimal(1)
    pending = net_flows = Decimal(0)
    flows: list[tuple[date, Decimal]] = []  # from the owner's side: money in is spent (negative), the end value received
    for point in in_period[valued[0] + 1 :]:
        pending += point.flow
        if point.flow:
            flows.append((point.day, -point.flow))
        if point.value is None:
            continue
        if last_value > 0:  # an empty wallet has no growth to measure until money comes in
            growth *= (point.value - pending) / last_value
        net_flows += pending
        last_value, pending, end_point = point.value, Decimal(0), point
    assert end_point.value is not None
    flows = [(day, amount) for day, amount in flows if day <= end_point.day]
    days = (end_point.day - base.day).days
    daily_rate = _daily_rate([(base.day, -base.value), *flows, (end_point.day, end_point.value)], base.day)
    a_year_or_more = days >= DAYS_PER_YEAR
    return Performance(
        start_day=base.day,
        end_day=end_point.day,
        start_value=base.value,
        end_value=end_point.value,
        net_flows=net_flows,
        gain=end_point.value - base.value - net_flows,
        time_weighted=growth - 1,
        time_weighted_per_year=growth ** (Decimal(DAYS_PER_YEAR) / days) - 1 if a_year_or_more and growth > 0 else None,
        money_weighted=None if daily_rate is None else (1 + daily_rate) ** days - 1,
        money_weighted_per_year=(1 + daily_rate) ** DAYS_PER_YEAR - 1 if a_year_or_more and daily_rate is not None else None,
    )


def _daily_rate(flows: Sequence[tuple[date, Decimal]], first_day: date) -> Decimal | None:
    """The daily rate at which the flows (spent negative, received positive) are worth nothing today, by bisection;
    None when no rate within the bounds does."""

    def worth(rate: Decimal) -> Decimal:
        return sum((amount / (1 + rate) ** (day - first_day).days for day, amount in flows), Decimal(0))

    low, high = LOWEST_DAILY_RATE, HIGHEST_DAILY_RATE
    worth_low = worth(low)
    if worth_low * worth(high) > 0:
        return None
    for _ in range(SOLVER_STEPS):
        middle = (low + high) / 2
        worth_middle = worth(middle)
        if worth_low * worth_middle <= 0:
            high = middle
        else:
            low, worth_low = middle, worth_middle
    return (low + high) / 2
