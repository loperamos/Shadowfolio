"""Security use cases: what is known about a listed company, beyond its price."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from shadowfolio.domain.company import Fundamentals, ValueRange, pe_by_day
from shadowfolio.domain.corporate_actions import DividendEvent
from shadowfolio.domain.earnings import EarningsDate
from shadowfolio.domain.errors import (
    CompanyDataUnavailableNowError,
    CorporateActionsUnavailableNowError,
    DomainError,
    EarningsCalendarUnavailableNowError,
    MissingDataKeyError,
    NewsUnavailableNowError,
)
from shadowfolio.domain.news import Article
from shadowfolio.domain.statistics import average_daily_value, average_daily_volume, beta, change_since, max_drawdown, volatility
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.company_data import CompanyData, CompanyDataUnavailableError
from shadowfolio.ports.corporate_actions import CorporateActionsUnavailableError
from shadowfolio.ports.earnings_calendar import EarningsCalendar, EarningsCalendarUnavailableError
from shadowfolio.ports.market_data import MarketDataSource
from shadowfolio.ports.news import NewsUnavailableError
from shadowfolio.ports.price_data import PriceDataUnavailableError
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
# How far ahead the next earnings date is looked for: companies report every quarter.
EARNINGS_AHEAD = timedelta(days=120)
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
    average_daily_volume: Decimal | None  # shares, over the period
    average_daily_value: Decimal | None  # in the price's currency, over the period


@dataclass(frozen=True)
class SecuritySummary:
    """What compares securities, gathered from the parts the security page shows; a part that could not be fetched is
    None, and `unavailable` says why, so the others still come."""

    symbol: str
    price: Quote | None
    figures: CompanyFigures | None  # None too when the provider has no fundamentals for the symbol (e.g. a fund)
    dividends: Dividends | None
    statistics: SecurityStatistics | None
    next_earnings: EarningsDate | None
    unavailable: tuple[str, ...]


@dataclass(frozen=True)
class SecurityRanges:
    """Where the price and the P/E stand within their lows and highs over a period; None without them."""

    price: ValueRange | None
    pe: ValueRange | None


class Securities:
    def __init__(
        self, company_data: CompanyData, market_data: MarketDataSource, market: Market, earnings_calendar: EarningsCalendar, clock: Clock
    ) -> None:
        """Prices, dividends and news come from the market data of the user who is looking; company data is the same
        for everyone (public filings)."""
        self._company_data = company_data
        self._market_data = market_data
        self._market = market
        self._earnings_calendar = earnings_calendar
        self._clock = clock

    def summary(self, user_id: str, symbol: str, start: date | None = None, end: date | None = None) -> SecuritySummary:
        """The latest price, the fundamentals' ratios, the dividends, the trend and risk from `start` to `end`, and the
        next earnings date: each part as its own use case gives it, or None with the reason it could not be fetched."""
        unavailable: list[str] = []

        def fetched[T](part: Callable[[], T]) -> T | None:
            try:
                return part()
            except DomainError as error:
                unavailable.append(str(error))
                return None

        try:
            price = self._market_data.for_user(user_id).prices.latest_price(symbol)
        except PriceDataUnavailableError:
            price = None
            unavailable.append(f"could not fetch the price of {symbol} right now; try again later")
        except MissingDataKeyError as error:
            price = None
            unavailable.append(str(error))
        figures = fetched(lambda: self.fundamentals(user_id, symbol))
        dividends = fetched(lambda: self.dividends(user_id, symbol))
        statistics = fetched(lambda: self.statistics(user_id, symbol, start, end))
        upcoming = fetched(lambda: self.next_earnings(symbol))
        return SecuritySummary(symbol, price, figures, dividends, statistics, upcoming, tuple(unavailable))

    def next_earnings(self, symbol: str) -> EarningsDate | None:
        """The next day, from today on, the company reports results; None when none is known."""
        today = self._clock.now().date()
        try:
            found = self._earnings_calendar.earnings(symbol, today, today + EARNINGS_AHEAD)
        except EarningsCalendarUnavailableError as error:
            raise EarningsCalendarUnavailableNowError(f"could not fetch when {symbol} reports next right now: {error}") from error
        return found[0] if found else None

    def statistics(self, user_id: str, symbol: str, start: date | None = None, end: date | None = None) -> SecurityStatistics:
        """The trend over the last 3, 6 and 12 months, and from `start` to `end` (as for its closes) the volatility, the
        deepest fall, the beta against the benchmark and how much trades on an average day (see domain.statistics)."""
        today = self._clock.now().date()
        quotes = self._market.closes(user_id, symbol, start, end)
        closes = _days(quotes)
        traded = [(quote.price, quote.volume) for quote in quotes if quote.volume is not None]
        benchmark = _days(self._market.closes(user_id, BETA_BENCHMARK, start, end))
        recent = _days(self._market.closes(user_id, symbol, today - TREND_HISTORY, today))
        return SecurityStatistics(
            three_months=change_since(recent, today - THREE_MONTHS),
            six_months=change_since(recent, today - SIX_MONTHS),
            one_year=change_since(recent, today - ONE_YEAR),
            volatility=volatility(closes),
            max_drawdown=max_drawdown(closes),
            beta=beta(closes, benchmark),
            benchmark_symbol=BETA_BENCHMARK,
            average_daily_volume=average_daily_volume([volume for _, volume in traded]),
            average_daily_value=average_daily_value(traded),
        )

    def dividends(self, user_id: str, symbol: str) -> Dividends:
        """The next dividend announced whose ex-date is still ahead (from today on; shares held before it starts
        receive it), and those whose ex-date was in the last year, with their yield at the latest price."""
        today = self._clock.now().date()
        data = self._market_data.for_user(user_id)
        try:
            found = data.corporate_actions.dividends(symbol, today - ONE_YEAR - PAYMENT_LAG, today + DIVIDENDS_AHEAD)
        except CorporateActionsUnavailableError as error:
            raise CorporateActionsUnavailableNowError(f"could not fetch {symbol}'s dividends right now; try again later") from error
        upcoming = min((d for d in found if d.ex_date >= today), key=lambda dividend: dividend.ex_date, default=None)
        last_year = sum((d.per_share for d in found if today - ONE_YEAR < d.ex_date <= today), Decimal(0))
        try:
            quote = data.prices.latest_price(symbol)
        except PriceDataUnavailableError:
            quote = None  # the dividends stand without it
        return Dividends(upcoming, last_year, last_year / quote.price if quote is not None and quote.price else None)

    def ranges(self, user_id: str, symbol: str, start: date | None = None, end: date | None = None) -> SecurityRanges:
        """The price's and the P/E's lowest, highest and latest values from `start` to `end` (as for its closes). The
        P/E is left out when the company's fundamentals are not available (or cannot be fetched now)."""
        closes = [(close.as_of.date(), close.price) for close in self._market.closes(user_id, symbol, start, end)]
        try:
            fundamentals = self._company_data.fundamentals(symbol)
        except CompanyDataUnavailableError:
            fundamentals = None  # the price range stands without it
        pe = None if fundamentals is None else ValueRange.of(pe_by_day(closes, fundamentals.years))
        return SecurityRanges(ValueRange.of(closes), pe)

    def news(self, user_id: str, symbol: str) -> list[Article]:
        """The latest articles about the symbol, newest first."""
        news = self._market_data.for_user(user_id).news
        try:
            return news.latest(symbol, NEWS_LIMIT)
        except NewsUnavailableError as error:
            raise NewsUnavailableNowError(f"could not fetch the news about {symbol} right now: {error}") from error

    def fundamentals(self, user_id: str, symbol: str) -> CompanyFigures | None:
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
            quote = self._market_data.for_user(user_id).prices.latest_price(symbol)
        except (PriceDataUnavailableError, MissingDataKeyError):
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
