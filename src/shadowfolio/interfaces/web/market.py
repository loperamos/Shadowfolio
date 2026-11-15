"""Routes for market information."""

from datetime import date

from fastapi import APIRouter, HTTPException

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation
from shadowfolio.interfaces.web.schemas import DailyCloseResponse, QuoteResponse
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
        return QuoteResponse.from_quote(symbol, quote)

    @router.get("/market/closes/{symbol}", responses=INVALID)
    def daily_closes(symbol: str, start: date | None = None, end: date | None = None) -> list[DailyCloseResponse]:
        """The symbol's close on each trading day from `start` (default: ten years before `end`) to `end` (default:
        today); empty when market data has none."""
        try:
            closes = market.closes(symbol.strip().upper(), start, end)
        except DomainError as error:
            raise rule_violation(error) from error
        return [
            DailyCloseResponse(day=close.as_of.date(), close=close.price, currency=close.currency, volume=close.volume) for close in closes
        ]

    return router
