"""Benchmarks: what a wallet's money would be worth in one security instead, given the same deposits on the same days.

Every deposit buys the security at that day's close, and every withdrawal sells it, in fractions of a share; its
dividends are reinvested at their payment day's close, after the wallet's withholding tax. Money waits as cash until
there is a close; a withdrawal larger than what the benchmark holds leaves it with negative cash.
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


@dataclass(frozen=True)
class Benchmark:
    symbol: str
    values: tuple[BenchmarkValue, ...]  # one per day, oldest first


def benchmark_values(
    days: Iterable[date],
    flows: Mapping[date, Decimal],
    closes: Mapping[date, Quote],
    rates: Mapping[date, Decimal],
    dividends: Iterable[DividendEvent],
    withholding_rate: Decimal,
) -> tuple[BenchmarkValue, ...]:
    """The benchmark's value at the end of each day. `flows` are the money put in (positive) or taken out (negative)
    per day, `closes` the security's close per day (as `PriceData.closes_between` gives them) and `rates` what one unit
    of its currency is worth in the wallet's that day. Dividends without a payment date are left out: when their cash
    came is unknown."""
    shares = Decimal(0)
    cash = Decimal(0)  # in the wallet's currency
    held: dict[date, Decimal] = {}  # shares at the end of each day
    unpaid = sorted(((d.payable_date, d) for d in dividends if d.payable_date is not None), key=lambda paid: paid[0])
    values = []
    for day in days:
        cash += flows.get(day, Decimal(0))
        close, rate = closes.get(day), rates.get(day)
        if close is None or rate is None:
            values.append(BenchmarkValue(day, None))
        else:
            # Dividends paid by now, for the shares held before their ex-date (paid late on a day without a close).
            while unpaid and unpaid[0][0] <= day:
                _, dividend = unpaid.pop(0)
                before_ex = held.get(dividend.ex_date - timedelta(days=1), Decimal(0))
                cash += before_ex * dividend.per_share * (1 - withholding_rate) * rate
            price = close.price * rate
            if cash > 0:
                shares, cash = shares + cash / price, Decimal(0)
            elif cash < 0:
                sold = min(shares, -cash / price)
                shares, cash = shares - sold, cash + sold * price
            values.append(BenchmarkValue(day, to_cents(shares * price + cash)))
        held[day] = shares
    return tuple(values)
