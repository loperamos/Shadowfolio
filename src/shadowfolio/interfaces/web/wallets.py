"""Routes for creating and reading wallets."""

from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import (
    CreateWalletRequest,
    OperationResponse,
    WalletResponse,
)
from shadowfolio.usecases.wallets import Wallets

# Until accounts exist, every wallet belongs to this owner.
LOCAL_OWNER = "local"


def wallets_router(wallets: Wallets) -> APIRouter:
    router = APIRouter()

    @router.post("/wallets", status_code=201)
    def create_wallet(request: CreateWalletRequest) -> WalletResponse:
        try:
            wallet = wallets.create(LOCAL_OWNER, request.name, request.currency, request.cash)
        except DomainError as error:
            raise rule_violation(error) from error
        return WalletResponse.from_wallet(wallet)

    @router.get("/wallets")
    def list_wallets() -> list[WalletResponse]:
        return [WalletResponse.from_wallet(wallet) for wallet in wallets.list(LOCAL_OWNER)]

    @router.get("/wallets/{wallet_id}")
    def get_wallet(wallet_id: UUID) -> WalletResponse:
        wallet = wallets.get(wallet_id)
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.get("/wallets/{wallet_id}/operations")
    def list_operations(wallet_id: UUID) -> list[OperationResponse]:
        wallet = wallets.get(wallet_id)
        if wallet is None:
            raise wallet_not_found()
        return [OperationResponse.from_operation(op) for op in wallet.operations]

    return router
