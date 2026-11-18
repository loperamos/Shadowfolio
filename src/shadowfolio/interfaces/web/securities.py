"""Routes for what is known about a listed company, beyond its price."""

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation
from shadowfolio.interfaces.web.schemas import (
    ArticleResponse,
    DividendsResponse,
    EarningsResponse,
    FundamentalsResponse,
    SecurityRangesResponse,
    SecurityStatisticsResponse,
    SecuritySummaryResponse,
)
from shadowfolio.usecases.securities import Securities


def securities_router(securities: Securities, current_user: Callable[[Request], str]) -> APIRouter:
    router = APIRouter()

    @router.get("/securities/{symbol}/fundamentals", responses=NOT_FOUND | INVALID)
    def security_fundamentals(symbol: str, user_id: str = Depends(current_user)) -> FundamentalsResponse:
        """The company's reported yearly results and shares outstanding, with its P/E and market cap at the latest
        price."""
        symbol = symbol.strip().upper()
        try:
            figures = securities.fundamentals(user_id, symbol)
        except DomainError as error:
            raise rule_violation(error) from error
        if figures is None:
            raise HTTPException(status_code=404, detail=f"no fundamentals for {symbol}")
        return FundamentalsResponse.from_figures(figures)

    @router.get("/securities/{symbol}/news", responses=INVALID)
    def security_news(symbol: str, user_id: str = Depends(current_user)) -> list[ArticleResponse]:
        """The latest articles about the symbol, newest first; empty when there are none."""
        try:
            articles = securities.news(user_id, symbol.strip().upper())
        except DomainError as error:
            raise rule_violation(error) from error
        return [
            ArticleResponse(headline=a.headline, summary=a.summary, source=a.source, url=a.url, published_at=a.published_at)
            for a in articles
        ]

    @router.get("/securities/{symbol}/summary")
    def security_summary(
        symbol: str, start: date | None = None, end: date | None = None, user_id: str = Depends(current_user)
    ) -> SecuritySummaryResponse:
        """What compares securities, in one place: valuation, dividends, growth, trend and risk from `start` to `end`,
        and the next earnings date. A part that cannot be fetched right now is left out, and `unavailable` says why."""
        return SecuritySummaryResponse.from_summary(securities.summary(user_id, symbol.strip().upper(), start, end))

    @router.get("/securities/{symbol}/statistics", responses=INVALID)
    def security_statistics(
        symbol: str, start: date | None = None, end: date | None = None, user_id: str = Depends(current_user)
    ) -> SecurityStatisticsResponse:
        """How the price moved: its trend over the last 3, 6 and 12 months, and from `start` to `end` (as for the
        closes) its volatility, deepest fall and beta against the market. A description of the past, not a signal."""
        try:
            statistics = securities.statistics(user_id, symbol.strip().upper(), start, end)
        except DomainError as error:
            raise rule_violation(error) from error
        return SecurityStatisticsResponse.from_statistics(statistics)

    @router.get("/securities/{symbol}/earnings", responses=INVALID)
    def security_earnings(symbol: str, user_id: str = Depends(current_user)) -> EarningsResponse:
        """When the company reports results next, from today on: the days prices often jump."""
        try:
            upcoming = securities.next_earnings(user_id, symbol.strip().upper())
        except DomainError as error:
            raise rule_violation(error) from error
        return EarningsResponse(next_date=None if upcoming is None else upcoming.day, time=None if upcoming is None else upcoming.time)

    @router.get("/securities/{symbol}/dividends", responses=INVALID)
    def security_dividends(symbol: str, user_id: str = Depends(current_user)) -> DividendsResponse:
        """The next dividend whose ex-date is still to come, and the last 12 months' dividends and their yield."""
        try:
            dividends = securities.dividends(user_id, symbol.strip().upper())
        except DomainError as error:
            raise rule_violation(error) from error
        return DividendsResponse.from_dividends(dividends)

    @router.get("/securities/{symbol}/ranges", responses=INVALID)
    def security_ranges(
        symbol: str, start: date | None = None, end: date | None = None, user_id: str = Depends(current_user)
    ) -> SecurityRangesResponse:
        """Where the price and the P/E stand within their lows and highs from `start` to `end` (as for the closes)."""
        try:
            ranges = securities.ranges(user_id, symbol.strip().upper(), start, end)
        except DomainError as error:
            raise rule_violation(error) from error
        return SecurityRangesResponse.from_ranges(ranges)

    return router
