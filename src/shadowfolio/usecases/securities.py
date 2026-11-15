"""Security use cases: what is known about a listed company, beyond its price."""

from dataclasses import dataclass
from decimal import Decimal

from shadowfolio.domain.company import Fundamentals
from shadowfolio.domain.errors import CompanyDataUnavailableNowError, NewsUnavailableNowError
from shadowfolio.domain.news import Article
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.company_data import CompanyData, CompanyDataUnavailableError
from shadowfolio.ports.news import News, NewsUnavailableError
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError


@dataclass(frozen=True)
class CompanyFigures:
    """The company's fundamentals, and the ratios they give at its latest price (None without one)."""

    fundamentals: Fundamentals
    price: Quote | None
    pe: Decimal | None
    market_cap: Decimal | None


# How many of the latest articles about a security are shown.
NEWS_LIMIT = 10


class Securities:
    def __init__(self, company_data: CompanyData, prices: PriceData, news: News) -> None:
        self._company_data = company_data
        self._prices = prices
        self._news = news

    def news(self, symbol: str) -> list[Article]:
        """The latest articles about the symbol, newest first."""
        try:
            return self._news.latest(symbol, NEWS_LIMIT)
        except NewsUnavailableError as error:
            raise NewsUnavailableNowError(f"could not fetch the news about {symbol} right now: {error}") from error

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
