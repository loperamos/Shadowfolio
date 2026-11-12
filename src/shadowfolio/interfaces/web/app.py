"""HTTP routes. Each one translates between HTTP and a use case, nothing more."""

from uuid import UUID

from fastapi import FastAPI, HTTPException

from shadowfolio.domain.wallet import DomainError
from shadowfolio.interfaces.web.schemas import (
    AmountRequest,
    BuyRequest,
    CreateWalletRequest,
    DepositRequest,
    OperationResponse,
    WalletResponse,
)
from shadowfolio.usecases.wallets import Wallets

# Until accounts exist, every wallet belongs to this owner.
LOCAL_OWNER = "local"


def create_app(wallets: Wallets) -> FastAPI:
    app = FastAPI(title="Shadowfolio")

    @app.post("/wallets", status_code=201)
    def create_wallet(request: CreateWalletRequest) -> WalletResponse:
        try:
            wallet = wallets.create(LOCAL_OWNER, request.name, request.currency, request.cash)
        except DomainError as error:
            raise _rule_violation(error) from error
        return WalletResponse.from_wallet(wallet)

    @app.get("/wallets")
    def list_wallets() -> list[WalletResponse]:
        return [WalletResponse.from_wallet(wallet) for wallet in wallets.list(LOCAL_OWNER)]

    @app.get("/wallets/{wallet_id}")
    def get_wallet(wallet_id: UUID) -> WalletResponse:
        wallet = wallets.get(wallet_id)
        if wallet is None:
            raise _wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @app.get("/wallets/{wallet_id}/operations")
    def list_operations(wallet_id: UUID) -> list[OperationResponse]:
        wallet = wallets.get(wallet_id)
        if wallet is None:
            raise _wallet_not_found()
        return [OperationResponse.from_operation(op) for op in wallet.operations]

    @app.post("/wallets/{wallet_id}/deposits")
    def deposit(wallet_id: UUID, request: DepositRequest) -> WalletResponse:
        try:
            wallet = wallets.deposit(wallet_id, request.amount, request.timestamp)
        except DomainError as error:
            raise _rule_violation(error) from error
        if wallet is None:
            raise _wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @app.post("/wallets/{wallet_id}/withdrawals")
    def withdraw(wallet_id: UUID, request: AmountRequest) -> WalletResponse:
        try:
            wallet = wallets.withdraw(wallet_id, request.amount)
        except DomainError as error:
            raise _rule_violation(error) from error
        if wallet is None:
            raise _wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @app.post("/wallets/{wallet_id}/buys")
    def record_buy(wallet_id: UUID, request: BuyRequest) -> WalletResponse:
        try:
            wallet = wallets.record_buy(
                wallet_id,
                request.to_trade(),
                request.timestamp,
                request.settled_amount,
                request.fees,
            )
        except DomainError as error:
            raise _rule_violation(error) from error
        if wallet is None:
            raise _wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    return app


def _wallet_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="wallet not found")


def _rule_violation(error: DomainError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))
