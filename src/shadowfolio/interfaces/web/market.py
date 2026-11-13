"""Routes for market information."""

from fastapi import APIRouter, HTTPException

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation
from shadowfolio.interfaces.web.schemas import QuoteResponse
from shadowfolio.usecases.market import Market


def market_router(market: Market) -> APIRouter:
    router = APIRouter()

    @router.get("/market/quotes/{symbol}", responses=NOT_FOUND | INVALID)
    def latest_quote(symbol: str) -> QuoteResponse:
        try:
            quote = market.latest_quote(symbol)
        except DomainError as error:
            raise rule_violation(error) from error
        if quote is None:
            raise HTTPException(status_code=404, detail=f"no price for {symbol}")
        return QuoteResponse(
            symbol=symbol, price=quote.price, currency=quote.currency, as_of=quote.as_of, previous_close=quote.previous_close
        )

    return router
