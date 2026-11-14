"""Benchmarks: what a wallet's money would be worth in one security instead, given the same deposits on the same days.

Every deposit buys the security at that day's close, in fractions of a share, and every withdrawal sells the same share
of the benchmark as it took from the wallet (taking 30% of the wallet sells 30% of the benchmark), so the benchmark
never runs out when the wallet did better. Its dividends are reinvested at their payment day's close, after the
wallet's withholding tax. Money waits as cash until there is a close.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from shadowfolio.domain.corporate_actions import DividendEvent
from shadowfolio.domain.money import to_cents
from shadowfolio.domain.valuation import Quote


@dataclass(frozen=True)
class BenchmarkValue:
    day: date
    value: Decimal | None  # in the wallet's currency; None when the day has no close or rate
    flow: Decimal = Decimal(0)  # money put in (positive) or taken out (negative) that day, in the wallet's currency


@dataclass(frozen=True)
class Benchmark:
    symbol: str
    values: tuple[BenchmarkValue, ...]  # one per day, oldest first


def benchmark_values(
    days: Iterable[date],
    flows: Mapping[date, Decimal],
    wallet_values: Mapping[date, Decimal],
    closes: Mapping[date, Quote],
    rates: Mapping[date, Decimal],
    dividends: Iterable[DividendEvent],
    withholding_rate: Decimal,
) -> tuple[BenchmarkValue, ...]:
    """The benchmark's value at the end of each day. `flows` are the money put in (positive) or taken out (negative)
    per day, `wallet_values` the wallet's own value at the end of the days it could be valued, `closes` the security's
    close per day (as `PriceData.closes_between` gives them) and `rates` what one unit
    of its currency is worth in the wallet's that day. Dividends without a payment date are left out: when their cash
    came is unknown."""
    shares = Decimal(0)
    cash = Decimal(0)  # in the wallet's currency
    held: dict[date, Decimal] = {}  # shares at the end of each day
    unpaid = sorted(((d.payable_date, d) for d in dividends if d.payable_date is not None), key=lambda paid: paid[0])
    values = []
    last_wallet_value: Decimal | None = None
    last_price: Decimal | None = None  # of a share, in the wallet's currency
    for day in days:
        flow = flows.get(day, Decimal(0))
        if flow >= 0:
            cash += flow
        else:
            # What the withdrawal takes from the benchmark, at the last known price (its own flow, not the wallet's).
            withdrawn = _withdrawn_share(-flow, wallet_values.get(day), last_wallet_value)
            flow = -withdrawn * (shares * (last_price or Decimal(0)) + cash)
            shares, cash = shares * (1 - withdrawn), cash * (1 - withdrawn)
        last_wallet_value = wallet_values.get(day, last_wallet_value)
        close, rate = closes.get(day), rates.get(day)
        if close is None or rate is None:
            values.append(BenchmarkValue(day, None, flow))
        else:
            # Dividends paid by now, for the shares held before their ex-date (paid late on a day without a close).
            while unpaid and unpaid[0][0] <= day:
                _, dividend = unpaid.pop(0)
                before_ex = held.get(dividend.ex_date - timedelta(days=1), Decimal(0))
                cash += before_ex * dividend.per_share * (1 - withholding_rate) * rate
            price = last_price = close.price * rate
            if cash > 0:
                shares, cash = shares + cash / price, Decimal(0)
            values.append(BenchmarkValue(day, to_cents(shares * price + cash), flow))
        held[day] = shares
    return tuple(values)


def _withdrawn_share(withdrawn: Decimal, value_after: Decimal | None, value_before: Decimal | None) -> Decimal:
    """The share of the wallet a withdrawal took: against its value that day before the withdrawal, or, when that day
    could not be valued, its last known value. All of it when its value is unknown or smaller."""
    before = value_after + withdrawn if value_after is not None else value_before
    if before is None or before <= withdrawn:
        return Decimal(1)
    return withdrawn / before
