"""Routes for creating, changing settings of, copying, deleting and reading wallets."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from shadowfolio.domain.errors import DomainError
from shadowfolio.domain.rules import Rules
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import (
    CopyWalletRequest,
    CreateWalletRequest,
    OperationResponse,
    RulesRequest,
    UpdateWalletRequest,
    WalletResponse,
)
from shadowfolio.usecases.wallets import Wallets


def wallets_router(wallets: Wallets, current_user: Callable[[Request], str]) -> APIRouter:
    router = APIRouter()

    @router.post("/wallets", status_code=201, responses=INVALID)
    def create_wallet(request: CreateWalletRequest, user_id: str = Depends(current_user)) -> WalletResponse:
        try:
            wallet = wallets.create(user_id, request.name, request.currency, request.cash)
        except DomainError as error:
            raise rule_violation(error) from error
        return WalletResponse.from_wallet(wallet)

    @router.post("/wallets/{wallet_id}/copies", status_code=201, responses=NOT_FOUND | INVALID)
    def copy_wallet(wallet_id: UUID, request: CopyWalletRequest) -> WalletResponse:
        try:
            copy = wallets.copy(wallet_id, request.name, request.before)
        except DomainError as error:
            raise rule_violation(error) from error
        if copy is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(copy)

    @router.patch("/wallets/{wallet_id}", responses=NOT_FOUND | INVALID)
    def update_wallet(wallet_id: UUID, request: UpdateWalletRequest) -> WalletResponse:
        try:
            wallet = wallets.update(wallet_id, request.name, request.withholding_rate)
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.put("/wallets/{wallet_id}/rules", responses=NOT_FOUND | INVALID)
    def set_wallet_rules(wallet_id: UUID, request: RulesRequest) -> WalletResponse:
        """Replace the wallet's rules, checked when an order is placed: a buy that would break one is refused."""
        try:
            wallet = wallets.set_rules(
                wallet_id,
                Rules(request.max_position_weight, request.min_cash_weight, tuple(request.allowed_symbols), request.max_orders_per_month),
            )
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.delete("/wallets/{wallet_id}", status_code=204, responses=NOT_FOUND | INVALID)
    def delete_wallet(wallet_id: UUID) -> Response:
        if not wallets.delete(wallet_id):
            raise wallet_not_found()
        return Response(status_code=204)

    @router.get("/wallets")
    def list_wallets(user_id: str = Depends(current_user)) -> list[WalletResponse]:
        return [WalletResponse.from_wallet(wallet) for wallet in wallets.list(user_id)]

    @router.get("/wallets/{wallet_id}", responses=NOT_FOUND | INVALID)
    def get_wallet(wallet_id: UUID) -> WalletResponse:
        wallet = wallets.get(wallet_id)
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.get("/wallets/{wallet_id}/operations", responses=NOT_FOUND | INVALID)
    def list_operations(wallet_id: UUID) -> list[OperationResponse]:
        wallet = wallets.get(wallet_id)
        if wallet is None:
            raise wallet_not_found()
        return [OperationResponse.from_operation(op, had_effect=wallet.had_effect(op)) for op in wallet.operations]

    return router
