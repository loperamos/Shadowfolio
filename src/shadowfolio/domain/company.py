"""What a company reported about itself: yearly results and shares outstanding, and the ratios they give at a price."""

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
