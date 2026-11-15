"""Security use cases: what is known about a listed company, beyond its price."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from shadowfolio.domain.company import Fundamentals, ValueRange, pe_by_day
from shadowfolio.domain.corporate_actions import DividendEvent
from shadowfolio.domain.errors import CompanyDataUnavailableNowError, CorporateActionsUnavailableNowError, NewsUnavailableNowError
from shadowfolio.domain.news import Article
from shadowfolio.domain.statistics import beta, change_since, max_drawdown, volatility
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.company_data import CompanyData, CompanyDataUnavailableError
from shadowfolio.ports.corporate_actions import CorporateActions, CorporateActionsUnavailableError
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
    price_to_sales: Decimal | None
    free_cash_flow_yield: Decimal | None


@dataclass(frozen=True)
class Dividends:
    """A security's dividends: the next announced whose ex-date is still ahead, and those with an ex-date in the last
    year, per share and against the latest price (None without one)."""

    next_ex_dividend: DividendEvent | None
    last_year_per_share: Decimal
    last_year_yield: Decimal | None


# How many of the latest articles about a security are shown.
NEWS_LIMIT = 10
# How far ahead announced dividends are looked for: companies announce them weeks, at most months, before. And how
# long a dividend can be paid after its ex-date: dividends are filed by payment date, so the last year's are looked
# for from this much earlier.
DIVIDENDS_AHEAD = timedelta(days=365)
PAYMENT_LAG = timedelta(days=90)
# The trend: the change over each of these, back from today; and the benchmark that beta is measured against.
THREE_MONTHS, SIX_MONTHS, ONE_YEAR = timedelta(days=91), timedelta(days=182), timedelta(days=365)
# A few days more than a year of closes, so the close a year back is there even after a weekend or a holiday.
TREND_HISTORY = ONE_YEAR + timedelta(days=7)
BETA_BENCHMARK = "SPY"


@dataclass(frozen=True)
class SecurityStatistics:
    """How the price moved: its trend back from today, and over a period how much it swung, its deepest fall and its
    beta against `benchmark_symbol`. Ratios (0.27 for +27%); None when there are not enough closes."""

    three_months: Decimal | None
    six_months: Decimal | None
    one_year: Decimal | None
    volatility: Decimal | None
    max_drawdown: Decimal | None
    beta: Decimal | None
    benchmark_symbol: str


@dataclass(frozen=True)
class SecurityRanges:
    """Where the price and the P/E stand within their lows and highs over a period; None without them."""

    price: ValueRange | None
    pe: ValueRange | None


class Securities:
    def __init__(
        self, company_data: CompanyData, prices: PriceData, news: News, market: Market, corporate_actions: CorporateActions, clock: Clock
    ) -> None:
        self._company_data = company_data
        self._prices = prices
        self._news = news
        self._market = market
        self._corporate_actions = corporate_actions
        self._clock = clock

    def statistics(self, symbol: str, start: date | None = None, end: date | None = None) -> SecurityStatistics:
        """The trend over the last 3, 6 and 12 months, and from `start` to `end` (as for its closes) the volatility, the
        deepest fall and the beta against the benchmark (see domain.statistics)."""
        today = self._clock.now().date()
        closes = _days(self._market.closes(symbol, start, end))
        benchmark = _days(self._market.closes(BETA_BENCHMARK, start, end))
        recent = _days(self._market.closes(symbol, today - TREND_HISTORY, today))
        return SecurityStatistics(
            three_months=change_since(recent, today - THREE_MONTHS),
            six_months=change_since(recent, today - SIX_MONTHS),
            one_year=change_since(recent, today - ONE_YEAR),
            volatility=volatility(closes),
            max_drawdown=max_drawdown(closes),
            beta=beta(closes, benchmark),
            benchmark_symbol=BETA_BENCHMARK,
        )

    def dividends(self, symbol: str) -> Dividends:
        """The next dividend announced whose ex-date is still ahead (from today on; shares held before it starts
        receive it), and those whose ex-date was in the last year, with their yield at the latest price."""
        today = self._clock.now().date()
        try:
            found = self._corporate_actions.dividends(symbol, today - ONE_YEAR - PAYMENT_LAG, today + DIVIDENDS_AHEAD)
        except CorporateActionsUnavailableError as error:
            raise CorporateActionsUnavailableNowError(f"could not fetch {symbol}'s dividends right now; try again later") from error
        upcoming = min((d for d in found if d.ex_date >= today), key=lambda dividend: dividend.ex_date, default=None)
        last_year = sum((d.per_share for d in found if today - ONE_YEAR < d.ex_date <= today), Decimal(0))
        try:
            quote = self._prices.latest_price(symbol)
        except PriceDataUnavailableError:
            quote = None  # the dividends stand without it
        return Dividends(upcoming, last_year, last_year / quote.price if quote is not None and quote.price else None)

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
        """The company's reported results, with its P/E, market cap, price to sales and free cash flow yield at the latest
        price. None if the provider has
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
            return CompanyFigures(fundamentals, quote, None, None, None, None)
        price = quote.price
        return CompanyFigures(
            fundamentals,
            quote,
            fundamentals.pe(price),
            fundamentals.market_cap(price),
            fundamentals.price_to_sales(price),
            fundamentals.free_cash_flow_yield(price),
        )


def _days(closes: list[Quote]) -> list[tuple[date, Decimal]]:
    return [(close.as_of.date(), close.price) for close in closes]
