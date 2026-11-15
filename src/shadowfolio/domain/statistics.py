"""How a price has moved: its trend over the last months, and how much it swings. These describe the past, as context
for understanding a security; they are not signals (published predictors lose most of their edge once known, as
McLean and Pontiff 2016 found).

Each takes daily closes, oldest first, as (day, close) on trading days only.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

TRADING_DAYS_PER_YEAR = 252
Closes = Sequence[tuple[date, Decimal]]


def daily_returns(closes: Closes) -> dict[date, Decimal]:
    """Each trading day's move on the one before (0.02 for +2%), by day."""
    return {day: close / previous - 1 for (_, previous), (day, close) in zip(closes, closes[1:], strict=False) if previous}


def volatility(closes: Closes) -> Decimal | None:
    """How much the price swings: the standard deviation of daily moves, over a year (times the square root of its
    trading days). 0.37 for 37%; None with fewer than two moves."""
    moves = list(daily_returns(closes).values())
    if len(moves) < 2:
        return None
    mean = sum(moves, Decimal(0)) / len(moves)
    variance = sum(((move - mean) ** 2 for move in moves), Decimal(0)) / (len(moves) - 1)
    return variance.sqrt() * Decimal(TRADING_DAYS_PER_YEAR).sqrt()


def max_drawdown(closes: Closes) -> Decimal | None:
    """The deepest fall from a high to a later low, as a negative ratio (-0.35 for a fall of 35%); 0 when it never fell,
    None without closes."""
    if not closes:
        return None
    peak, deepest = closes[0][1], Decimal(0)
    for _, close in closes:
        peak = max(peak, close)
        if peak:
            deepest = min(deepest, close / peak - 1)
    return deepest


def beta(closes: Closes, benchmark: Closes) -> Decimal | None:
    """How much the price moves when the benchmark does, on the days both moved: 2 for twice as much, 0.5 for half.
    None with fewer than two such days, or when the benchmark did not move at all."""
    own, market = daily_returns(closes), daily_returns(benchmark)
    days = sorted(own.keys() & market.keys())
    if len(days) < 2:
        return None
    own_mean = sum((own[day] for day in days), Decimal(0)) / len(days)
    market_mean = sum((market[day] for day in days), Decimal(0)) / len(days)
    covariance = sum(((own[day] - own_mean) * (market[day] - market_mean) for day in days), Decimal(0))
    variance = sum(((market[day] - market_mean) ** 2 for day in days), Decimal(0))
    return covariance / variance if variance else None


def change_since(closes: Closes, since: date) -> Decimal | None:
    """How much the latest close changed on the last close on or before `since` (0.27 for +27%); None without one."""
    before = [close for day, close in closes if day <= since]
    if not closes or not before or not before[-1]:
        return None
    return closes[-1][1] / before[-1] - 1
