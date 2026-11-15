"""Routes for what is known about a listed company, beyond its price."""

from fastapi import APIRouter, HTTPException

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation
from shadowfolio.interfaces.web.schemas import ArticleResponse, FundamentalsResponse
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

    return router
