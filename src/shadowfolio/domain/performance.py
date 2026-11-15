"""How a wallet, or a benchmark, did over a period: its gain, and two standard returns.

- The time-weighted return ignores when and how much money was put in or taken out: it chains each day's growth, so it
  measures the choices made (what was held), and compares wallets and benchmarks fairly.
- The money-weighted return (an internal rate of return) includes them: the steady rate at which the money put in
  would have grown into the end value, so it measures the actual result, timing included.

Both run from the value at the end of the day before the period (or its first valued day) to its last valued day.
Days that could not be valued are skipped: money moved on them counts at the next valued day.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, timedelta
from decimal import Decimal

from shadowfolio.domain.operations import Buy, Fee, Operation, Sell

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
    chained = _chained(points, start, end)
    if not chained:
        return None
    base = chained[0].point
    end_link = next(link for link in reversed(chained) if link.growth is not None)
    end_point, growth = end_link.point, end_link.growth
    assert base.value is not None and end_point.value is not None and growth is not None
    # From the owner's side: money in is spent (negative), the end value received.
    flows = [(link.point.day, -link.point.flow) for link in chained[1:] if link.point.flow and link.point.day <= end_point.day]
    net_flows = sum((link.point.flow for link in chained[1:] if link.point.day <= end_point.day), Decimal(0))
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


def cumulative_returns(points: Sequence[DayValue], start: date, end: date) -> tuple[tuple[date, Decimal | None], ...]:
    """The time-weighted return from the start of the period to the end of each of its days, from 0 on the day it
    starts from (see `performance`); None for days that could not be valued. Empty when none could."""
    return tuple((link.point.day, None if link.growth is None else link.growth - 1) for link in _chained(points, start, end))


@dataclass(frozen=True)
class _Link:
    point: DayValue
    growth: Decimal | None  # since the start, at the end of this day; None when it could not be valued


def _chained(points: Sequence[DayValue], start: date, end: date) -> list[_Link]:
    """The period's days from the one it starts from (the day before `start`, or its first valued day), each with the
    growth since then: each valued day's value, less the money moved since the previous valued day, against that
    day's value."""
    in_period = [point for point in points if start - timedelta(days=1) <= point.day <= end]
    valued = [index for index, point in enumerate(in_period) if point.value is not None]
    if not valued:
        return []
    base = in_period[valued[0]]
    assert base.value is not None
    links = [_Link(base, Decimal(1))]
    last_value, growth, pending = base.value, Decimal(1), Decimal(0)
    for point in in_period[valued[0] + 1 :]:
        pending += point.flow
        if point.value is None:
            links.append(_Link(point, None))
            continue
        if last_value > 0:  # an empty wallet has no growth to measure until money comes in
            growth *= (point.value - pending) / last_value
        last_value, pending = point.value, Decimal(0)
        links.append(_Link(point, growth))
    return links


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


@dataclass(frozen=True)
class TradingActivity:
    """How much a wallet traded over a period, and what that cost, against what it was worth on average."""

    bought: Decimal  # spent on buys, before fees, in the wallet's currency
    sold: Decimal  # received from sells, before fees
    fees: Decimal  # on trades, and charged on their own
    average_value: Decimal | None  # over the period's valued days; None when none was valued

    @property
    def turnover(self) -> Decimal | None:
        """The smaller of buys and sells against the average value, as funds report it (SEC Form N-1A): the share of
        the wallet replaced, without counting new money invested or money taken out."""
        return min(self.bought, self.sold) / self.average_value if self.average_value else None

    @property
    def fees_ratio(self) -> Decimal | None:
        """Fees against the average value, as a ratio (0.003 for 0.3%)."""
        return self.fees / self.average_value if self.average_value else None


def trading_activity(operations: Iterable[Operation], values: Sequence[DayValue], start: date, end: date) -> TradingActivity:
    """What the operations dated from `start` to `end` (both included, in UTC) bought, sold and paid in fees, and the
    average of the daily values in that period."""
    bought = sold = fees = Decimal(0)
    for op in operations:
        if not start <= op.timestamp.astimezone(UTC).date() <= end:
            continue
        if isinstance(op, Buy):
            bought += op.settled_amount
            fees += op.fees
        elif isinstance(op, Sell):
            sold += op.settled_amount
            fees += op.fees
        elif isinstance(op, Fee):
            fees += op.amount
    valued = [point.value for point in values if start <= point.day <= end and point.value is not None]
    average = sum(valued, Decimal(0)) / len(valued) if valued else None
    return TradingActivity(bought, sold, fees, average)
