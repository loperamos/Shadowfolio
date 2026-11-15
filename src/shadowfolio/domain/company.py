"""What a company reported about itself: yearly results, cash flows and balance sheet, and shares outstanding, and the
ratios they give at a price."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from shadowfolio.domain.money import Currency

# How far apart one fiscal year's end and the next one's start can be for them to follow each other.
ADJACENT_YEARS = timedelta(days=7)
# How far apart the ends of the same quarter a year apart can be: fiscal years of 52 or 53 weeks move them a little.
A_YEAR_APART = range(357, 372)


class SharesSource(StrEnum):
    """Where a company's share count comes from, the most exact first."""

    COVER = "cover"  # as the company stated it on its latest report's cover
    BALANCE_SHEET = "balance_sheet"  # every class together, at the end of the latest quarter
    DILUTED_AVERAGE = "diluted_average"  # approximate: the latest quarter's average, counting shares options could add


@dataclass(frozen=True)
class FiscalYear:
    """What the company reported for a fiscal year, or a fiscal quarter (see Fundamentals.quarters)."""

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
    shares_source: SharesSource | None = None  # None without a count
    quarters: tuple[FiscalYear, ...] = ()  # each fiscal quarter, oldest first; no EPS (see the company data)
    industry: str | None = None  # as the provider classifies it, e.g. "Semiconductors & Related Devices"

    def revenue_growth(self, year: FiscalYear) -> Decimal | None:
        """How much `year`'s revenue grew on the fiscal year just before it (0.65 for +65%); None without that year or
        either revenue."""
        previous = next((other for other in self.years if timedelta(0) < year.start - other.end <= ADJACENT_YEARS), None)
        if previous is None or year.revenue is None or not previous.revenue:
            return None
        return year.revenue / previous.revenue - 1

    def quarter_revenue_growth(self, quarter: FiscalYear) -> Decimal | None:
        """How much `quarter`'s revenue grew on the same quarter a year before (seasons make the quarter just before a
        poor comparison); None without that quarter or either revenue."""
        previous = next((other for other in self.quarters if (quarter.end - other.end).days in A_YEAR_APART), None)
        if previous is None or quarter.revenue is None or not previous.revenue:
            return None
        return quarter.revenue / previous.revenue - 1

    def pe(self, price: Decimal) -> Decimal | None:
        """Price to earnings: `price` against the last fiscal year's diluted EPS; None without a positive one."""
        eps = self.years[-1].eps_diluted if self.years else None
        return price / eps if eps is not None and eps > 0 else None

    def market_cap(self, price: Decimal) -> Decimal | None:
        """What all the shares outstanding are worth at `price`; None without the share count."""
        return None if self.shares_outstanding is None else price * self.shares_outstanding

    def price_to_sales(self, price: Decimal) -> Decimal | None:
        """The market cap at `price` against the last fiscal year's revenue; None without either."""
        market_cap, revenue = self.market_cap(price), self.years[-1].revenue if self.years else None
        return market_cap / revenue if market_cap is not None and revenue else None

    def free_cash_flow_yield(self, price: Decimal) -> Decimal | None:
        """The last fiscal year's free cash flow against the market cap at `price` (0.025 for 2.5%); None without
        either."""
        market_cap, free_cash_flow = self.market_cap(price), self.years[-1].free_cash_flow if self.years else None
        return free_cash_flow / market_cap if market_cap and free_cash_flow is not None else None


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
