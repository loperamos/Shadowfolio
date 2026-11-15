"""Routes for what is known about a listed company, beyond its price."""

from fastapi import APIRouter, HTTPException

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation
from shadowfolio.interfaces.web.schemas import FundamentalsResponse
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

    return router
