"""What a company reported about itself: yearly results and shares outstanding, and the ratios they give at a price."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from shadowfolio.domain.money import Currency


@dataclass(frozen=True)
class FiscalYear:
    start: date
    end: date
    revenue: Decimal | None  # None when the company did not report it (in a way we read)
    net_income: Decimal | None
    eps_diluted: Decimal | None  # net income per share, counting shares that options and the like could add


@dataclass(frozen=True)
class Fundamentals:
    company_name: str
    currency: Currency  # of the amounts reported
    years: tuple[FiscalYear, ...]  # oldest first
    shares_outstanding: Decimal | None
    shares_as_of: date | None

    def pe(self, price: Decimal) -> Decimal | None:
        """Price to earnings: `price` against the last fiscal year's diluted EPS; None without a positive one."""
        eps = self.years[-1].eps_diluted if self.years else None
        return price / eps if eps is not None and eps > 0 else None

    def market_cap(self, price: Decimal) -> Decimal | None:
        """What all the shares outstanding are worth at `price`; None without the share count."""
        return None if self.shares_outstanding is None else price * self.shares_outstanding
