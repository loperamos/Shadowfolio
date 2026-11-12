"""Routes for market information."""

from fastapi import APIRouter, HTTPException

from shadowfolio.interfaces.web.schemas import QuoteResponse
from shadowfolio.usecases.market import Market


def market_router(market: Market) -> APIRouter:
    router = APIRouter()

    @router.get("/market/quotes/{symbol}")
    def latest_quote(symbol: str) -> QuoteResponse:
        quote = market.latest_quote(symbol)
        if quote is None:
            raise HTTPException(status_code=404, detail=f"no price for {symbol}")
        return QuoteResponse(symbol=symbol, price=quote.price, currency=quote.currency, as_of=quote.as_of)

    return router
