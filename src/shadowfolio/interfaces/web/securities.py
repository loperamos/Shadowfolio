"""Routes for what is known about a listed company, beyond its price."""

from datetime import date

from fastapi import APIRouter, HTTPException

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation
from shadowfolio.interfaces.web.schemas import (
    ArticleResponse,
    CalendarResponse,
    DividendResponse,
    FundamentalsResponse,
    SecurityRangesResponse,
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

    @router.get("/securities/{symbol}/calendar", responses=INVALID)
    def security_calendar(symbol: str) -> CalendarResponse:
        """What is announced ahead: the next dividend whose ex-date is still to come."""
        try:
            dividend = securities.next_ex_dividend(symbol.strip().upper())
        except DomainError as error:
            raise rule_violation(error) from error
        if dividend is None:
            return CalendarResponse(next_ex_dividend=None)
        return CalendarResponse(
            next_ex_dividend=DividendResponse(
                ex_date=dividend.ex_date, payable_date=dividend.payable_date, per_share=dividend.per_share, currency=dividend.currency
            )
        )

    @router.get("/securities/{symbol}/ranges", responses=INVALID)
    def security_ranges(symbol: str, start: date | None = None, end: date | None = None) -> SecurityRangesResponse:
        """Where the price and the P/E stand within their lows and highs from `start` to `end` (as for the closes)."""
        try:
            ranges = securities.ranges(symbol.strip().upper(), start, end)
        except DomainError as error:
            raise rule_violation(error) from error
        return SecurityRangesResponse.from_ranges(ranges)

    return router
