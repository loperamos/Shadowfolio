"""Security use cases: what is known about a listed company, beyond its price."""

from dataclasses import dataclass
from decimal import Decimal

from shadowfolio.domain.company import Fundamentals
from shadowfolio.domain.errors import CompanyDataUnavailableNowError
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.company_data import CompanyData, CompanyDataUnavailableError
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError


@dataclass(frozen=True)
class CompanyFigures:
    """The company's fundamentals, and the ratios they give at its latest price (None without one)."""

    fundamentals: Fundamentals
    price: Quote | None
    pe: Decimal | None
    market_cap: Decimal | None


class Securities:
    def __init__(self, company_data: CompanyData, prices: PriceData) -> None:
        self._company_data = company_data
        self._prices = prices

    def fundamentals(self, symbol: str) -> CompanyFigures | None:
        """The company's reported results, with its P/E and market cap at the latest price. None if the provider has
        no fundamentals for the symbol; the ratios are None when there is no price (or it cannot be fetched now)."""
        try:
            fundamentals = self._company_data.fundamentals(symbol)
        except CompanyDataUnavailableError as error:
            raise CompanyDataUnavailableNowError(f"could not fetch the fundamentals of {symbol} right now: {error}") from error
        if fundamentals is None:
            return None
        try:
            quote = self._prices.latest_price(symbol)
        except PriceDataUnavailableError:
            quote = None  # the reported figures stand without it
        if quote is None or quote.currency is not fundamentals.currency:
            return CompanyFigures(fundamentals, quote, None, None)
        return CompanyFigures(fundamentals, quote, fundamentals.pe(quote.price), fundamentals.market_cap(quote.price))
