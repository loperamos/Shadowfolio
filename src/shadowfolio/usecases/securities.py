"""Security use cases: what is known about a listed company, beyond its price."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from shadowfolio.domain.company import Fundamentals, ValueRange, pe_by_day
from shadowfolio.domain.errors import CompanyDataUnavailableNowError, NewsUnavailableNowError
from shadowfolio.domain.news import Article
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.company_data import CompanyData, CompanyDataUnavailableError
from shadowfolio.ports.news import News, NewsUnavailableError
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError
from shadowfolio.usecases.market import Market


@dataclass(frozen=True)
class CompanyFigures:
    """The company's fundamentals, and the ratios they give at its latest price (None without one)."""

    fundamentals: Fundamentals
    price: Quote | None
    pe: Decimal | None
    market_cap: Decimal | None


# How many of the latest articles about a security are shown.
NEWS_LIMIT = 10


@dataclass(frozen=True)
class SecurityRanges:
    """Where the price and the P/E stand within their lows and highs over a period; None without them."""

    price: ValueRange | None
    pe: ValueRange | None


class Securities:
    def __init__(self, company_data: CompanyData, prices: PriceData, news: News, market: Market) -> None:
        self._company_data = company_data
        self._prices = prices
        self._news = news
        self._market = market

    def ranges(self, symbol: str, start: date | None = None, end: date | None = None) -> SecurityRanges:
        """The price's and the P/E's lowest, highest and latest values from `start` to `end` (as for its closes). The
        P/E is left out when the company's fundamentals are not available (or cannot be fetched now)."""
        closes = [(close.as_of.date(), close.price) for close in self._market.closes(symbol, start, end)]
        try:
            fundamentals = self._company_data.fundamentals(symbol)
        except CompanyDataUnavailableError:
            fundamentals = None  # the price range stands without it
        pe = None if fundamentals is None else ValueRange.of(pe_by_day(closes, fundamentals.years))
        return SecurityRanges(ValueRange.of(closes), pe)

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
