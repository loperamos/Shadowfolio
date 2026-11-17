"""Routes for orders placed now: placing, listing (which fills the due ones first), cancelling, and the fill job."""

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from shadowfolio.domain.errors import DomainError, OrderNotFoundError
from shadowfolio.domain.orders import OrderSide
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, order_not_found, rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import (
    FillSummaryResponse,
    OrderEstimateResponse,
    OrderOutcomeResponse,
    OrderResponse,
    PlaceOrderRequest,
)
from shadowfolio.usecases.comparison import DEFAULT_BENCHMARK
from shadowfolio.usecases.orders import Orders


def orders_router(orders: Orders, job_check: Callable[[Request], None]) -> APIRouter:
    router = APIRouter()

    @router.post("/wallets/{wallet_id}/orders", status_code=201, responses=NOT_FOUND | INVALID)
    def place_order(wallet_id: UUID, request: PlaceOrderRequest) -> OrderResponse:
        """Place an order now. At market it fills at the first price after it, so one placed while the market is closed
        waits for the next open; with a limit price, on the first later minute that reaches it."""
        try:
            placed = orders.place(wallet_id, request.side, request.symbol, request.quantity, request.reason, request.limit_price)
        except DomainError as error:
            raise rule_violation(error) from error
        if placed is None:
            raise wallet_not_found()
        wallet, order = placed
        return OrderResponse.from_order(order, wallet)

    @router.get("/wallets/{wallet_id}/orders/estimate", responses=NOT_FOUND | INVALID)
    def estimate_order(
        wallet_id: UUID, side: OrderSide, symbol: str, quantity: Decimal, limit_price: Decimal | None = None
    ) -> OrderEstimateResponse:
        """What an order would come to if placed now, in the wallet's currency: at its limit price, or a market order at
        the latest price, at the latest exchange rate, as the buying power counts open orders. A fill may differ."""
        try:
            estimate = orders.estimate(wallet_id, side, symbol, quantity, limit_price)
        except DomainError as error:
            raise rule_violation(error) from error
        if estimate is None:
            raise wallet_not_found()
        return OrderEstimateResponse.from_estimate(estimate)

    @router.get("/wallets/{wallet_id}/orders/outcomes", responses=NOT_FOUND | INVALID)
    def order_outcomes(wallet_id: UUID, benchmark: str = DEFAULT_BENCHMARK) -> list[OrderOutcomeResponse]:
        """How each filled order turned out: its symbol's return from the fill price to the latest, next to the
        benchmark's over the same time. Apart from the orders, so a slow price never holds them up."""
        try:
            outcomes = orders.outcomes(wallet_id, benchmark)
        except DomainError as error:
            raise rule_violation(error) from error
        if outcomes is None:
            raise wallet_not_found()
        return [OrderOutcomeResponse.from_outcome(outcome) for outcome in outcomes]

    @router.get("/wallets/{wallet_id}/orders", responses=NOT_FOUND)
    def list_orders(wallet_id: UUID) -> list[OrderResponse]:
        """The wallet's orders in the order they were placed, the due ones filled first."""
        wallet = orders.list(wallet_id)
        if wallet is None:
            raise wallet_not_found()
        return [OrderResponse.from_order(order, wallet) for order in wallet.orders]

    @router.post("/wallets/{wallet_id}/orders/{order_id}/cancel", responses=NOT_FOUND | INVALID)
    def cancel_order(wallet_id: UUID, order_id: UUID) -> OrderResponse:
        """Cancel an open order; one that has filled, or was cancelled or rejected, cannot be."""
        try:
            cancelled = orders.cancel(wallet_id, order_id)
        except OrderNotFoundError as error:
            raise order_not_found() from error
        except DomainError as error:
            raise rule_violation(error) from error
        if cancelled is None:
            raise wallet_not_found()
        wallet, order = cancelled
        return OrderResponse.from_order(order, wallet)

    @router.post("/orders/fill", dependencies=[Depends(job_check)])
    def fill_all_orders() -> FillSummaryResponse:
        """Fill every wallet's due orders. Called by the job that runs while the market is open (or by hand)."""
        summary = orders.fill_all()
        return FillSummaryResponse(wallets=summary.wallets, filled=summary.filled)

    return router
