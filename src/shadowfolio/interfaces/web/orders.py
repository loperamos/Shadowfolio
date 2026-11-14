"""Routes for orders placed now: placing, listing (which fills the due ones first), cancelling, and the fill job."""

from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError, OrderNotFoundError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, order_not_found, rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import FillSummaryResponse, OrderResponse, PlaceOrderRequest
from shadowfolio.usecases.orders import Orders


def orders_router(orders: Orders) -> APIRouter:
    router = APIRouter()

    @router.post("/wallets/{wallet_id}/orders", status_code=201, responses=NOT_FOUND | INVALID)
    def place_order(wallet_id: UUID, request: PlaceOrderRequest) -> OrderResponse:
        """Place a market order now: it fills at the first price after it, so one placed while the market is closed
        waits for the next open."""
        try:
            placed = orders.place(wallet_id, request.side, request.symbol, request.quantity, request.reason)
        except DomainError as error:
            raise rule_violation(error) from error
        if placed is None:
            raise wallet_not_found()
        wallet, order = placed
        return OrderResponse.from_order(order, wallet)

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

    @router.post("/orders/fill")
    def fill_all_orders() -> FillSummaryResponse:
        """Fill every wallet's due orders. Called by the job that runs while the market is open (or by hand)."""
        summary = orders.fill_all()
        return FillSummaryResponse(wallets=summary.wallets, filled=summary.filled)

    return router
