"""What a company reported about itself: yearly results, cash flows and balance sheet, and shares outstanding, and the
ratios they give at a price."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from shadowfolio.domain.money import Currency

# How far apart one fiscal year's end and the next one's start can be for them to follow each other.
ADJACENT_YEARS = timedelta(days=7)


@dataclass(frozen=True)
class FiscalYear:
    start: date
    end: date
    revenue: Decimal | None  # None when the company did not report it (in a way we read)
    net_income: Decimal | None
    eps_diluted: Decimal | None  # net income per share, counting shares that options and the like could add
    operating_cash_flow: Decimal | None = None  # cash the business brought in over the year
    capital_spending: Decimal | None = None  # cash spent on property, plant and equipment over the year
    cash: Decimal | None = None  # cash and cash equivalents at the year's end
    debt: Decimal | None = None  # long-term debt at the year's end, the part due within a year included

    @property
    def free_cash_flow(self) -> Decimal | None:
        """Operating cash flow less capital spending: the cash left to pay out, invest or save; None without both."""
        if self.operating_cash_flow is None or self.capital_spending is None:
            return None
        return self.operating_cash_flow - self.capital_spending

    @property
    def net_margin(self) -> Decimal | None:
        """The share of revenue kept as net income (0.556 for 55.6%); None without both, or without revenue."""
        if self.net_income is None or not self.revenue:
            return None
        return self.net_income / self.revenue


@dataclass(frozen=True)
class Fundamentals:
    company_name: str
    currency: Currency  # of the amounts reported
    years: tuple[FiscalYear, ...]  # oldest first
    shares_outstanding: Decimal | None
    shares_as_of: date | None

    def revenue_growth(self, year: FiscalYear) -> Decimal | None:
        """How much `year`'s revenue grew on the fiscal year just before it (0.65 for +65%); None without that year or
        either revenue."""
        previous = next((other for other in self.years if timedelta(0) < year.start - other.end <= ADJACENT_YEARS), None)
        if previous is None or year.revenue is None or not previous.revenue:
            return None
        return year.revenue / previous.revenue - 1

    def pe(self, price: Decimal) -> Decimal | None:
        """Price to earnings: `price` against the last fiscal year's diluted EPS; None without a positive one."""
        eps = self.years[-1].eps_diluted if self.years else None
        return price / eps if eps is not None and eps > 0 else None

    def market_cap(self, price: Decimal) -> Decimal | None:
        """What all the shares outstanding are worth at `price`; None without the share count."""
        return None if self.shares_outstanding is None else price * self.shares_outstanding


@dataclass(frozen=True)
class ValueRange:
    """The lowest and highest of a series of daily values, and its latest one, with the days it covers."""

    low: Decimal
    high: Decimal
    current: Decimal
    start: date
    end: date

    @classmethod
    def of(cls, daily: Sequence[tuple[date, Decimal]]) -> "ValueRange | None":
        """The range of `daily` (oldest first); None when it is empty."""
        if not daily:
            return None
        values = [value for _, value in daily]
        return cls(min(values), max(values), values[-1], daily[0][0], daily[-1][0])


def pe_by_day(closes: Sequence[tuple[date, Decimal]], years: Sequence[FiscalYear]) -> list[tuple[date, Decimal]]:
    """Each day's P/E: its close against the diluted EPS of the last fiscal year ended by then. Days without a
    positive one are left out."""
    with_eps = sorted((year for year in years if year.eps_diluted is not None and year.eps_diluted > 0), key=lambda year: year.end)
    daily = []
    for day, close in closes:
        latest = next((year for year in reversed(with_eps) if year.end <= day), None)
        if latest is not None and latest.eps_diluted is not None:
            daily.append((day, close / latest.eps_diluted))
    return daily
