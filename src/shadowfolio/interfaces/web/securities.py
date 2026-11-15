"""Routes for what is known about a listed company, beyond its price."""

from datetime import date

from fastapi import APIRouter, HTTPException

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation
from shadowfolio.interfaces.web.schemas import (
    ArticleResponse,
    DividendsResponse,
    EarningsResponse,
    FundamentalsResponse,
    SecurityRangesResponse,
    SecurityStatisticsResponse,
)
from shadowfolio.usecases.securities import Securities


def securities_router(securities: Securities) -> APIRouter:
    router = APIRouter()

    @router.get("/securities/{symbol}/fundamentals", responses=NOT_FOUND | INVALID)
    def security_fundamentals(symbol: str) -> FundamentalsResponse:
        """The company's reported yearly results and shares outstanding, with its P/E and market cap at the latest
        price."""
        symbol = symbol.strip().upper()
        try:
            figures = securities.fundamentals(symbol)
        except DomainError as error:
            raise rule_violation(error) from error
        if figures is None:
            raise HTTPException(status_code=404, detail=f"no fundamentals for {symbol}")
        return FundamentalsResponse.from_figures(figures)

    @router.get("/securities/{symbol}/news", responses=INVALID)
    def security_news(symbol: str) -> list[ArticleResponse]:
        """The latest articles about the symbol, newest first; empty when there are none."""
        try:
            articles = securities.news(symbol.strip().upper())
        except DomainError as error:
            raise rule_violation(error) from error
        return [
            ArticleResponse(headline=a.headline, summary=a.summary, source=a.source, url=a.url, published_at=a.published_at)
            for a in articles
        ]

    @router.get("/securities/{symbol}/statistics", responses=INVALID)
    def security_statistics(symbol: str, start: date | None = None, end: date | None = None) -> SecurityStatisticsResponse:
        """How the price moved: its trend over the last 3, 6 and 12 months, and from `start` to `end` (as for the
        closes) its volatility, deepest fall and beta against the market. A description of the past, not a signal."""
        try:
            statistics = securities.statistics(symbol.strip().upper(), start, end)
        except DomainError as error:
            raise rule_violation(error) from error
        return SecurityStatisticsResponse.from_statistics(statistics)

    @router.get("/securities/{symbol}/earnings", responses=INVALID)
    def security_earnings(symbol: str) -> EarningsResponse:
        """When the company reports results next, from today on: the days prices often jump."""
        try:
            upcoming = securities.next_earnings(symbol.strip().upper())
        except DomainError as error:
            raise rule_violation(error) from error
        return EarningsResponse(next_date=None if upcoming is None else upcoming.day, time=None if upcoming is None else upcoming.time)

    @router.get("/securities/{symbol}/dividends", responses=INVALID)
    def security_dividends(symbol: str) -> DividendsResponse:
        """The next dividend whose ex-date is still to come, and the last 12 months' dividends and their yield."""
        try:
            dividends = securities.dividends(symbol.strip().upper())
        except DomainError as error:
            raise rule_violation(error) from error
        return DividendsResponse.from_dividends(dividends)

    @router.get("/securities/{symbol}/ranges", responses=INVALID)
    def security_ranges(symbol: str, start: date | None = None, end: date | None = None) -> SecurityRangesResponse:
        """Where the price and the P/E stand within their lows and highs from `start` to `end` (as for the closes)."""
        try:
            ranges = securities.ranges(symbol.strip().upper(), start, end)
        except DomainError as error:
            raise rule_violation(error) from error
        return SecurityRangesResponse.from_ranges(ranges)

    return router
