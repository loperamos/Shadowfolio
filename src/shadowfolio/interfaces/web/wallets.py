"""Routes for creating, copying, deleting and reading wallets."""

from uuid import UUID

from fastapi import APIRouter, Response

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import CopyWalletRequest, CreateWalletRequest, OperationResponse, WalletResponse
from shadowfolio.usecases.wallets import Wallets

# Until accounts exist, every wallet belongs to this owner.
LOCAL_OWNER = "local"


def wallets_router(wallets: Wallets) -> APIRouter:
    router = APIRouter()

    @router.post("/wallets", status_code=201, responses=INVALID)
    def create_wallet(request: CreateWalletRequest) -> WalletResponse:
        try:
            wallet = wallets.create(LOCAL_OWNER, request.name, request.currency, request.cash)
        except DomainError as error:
            raise rule_violation(error) from error
        return WalletResponse.from_wallet(wallet)

    @router.post("/wallets/{wallet_id}/copies", status_code=201, responses=NOT_FOUND | INVALID)
    def copy_wallet(wallet_id: UUID, request: CopyWalletRequest) -> WalletResponse:
        copy = wallets.copy(wallet_id, request.name)
        if copy is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(copy)

    @router.delete("/wallets/{wallet_id}", status_code=204, responses=NOT_FOUND | INVALID)
    def delete_wallet(wallet_id: UUID) -> Response:
        if not wallets.delete(wallet_id):
            raise wallet_not_found()
        return Response(status_code=204)

    @router.get("/wallets")
    def list_wallets() -> list[WalletResponse]:
        return [WalletResponse.from_wallet(wallet) for wallet in wallets.list(LOCAL_OWNER)]

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
        return [OperationResponse.from_operation(op) for op in wallet.operations]

    return router
