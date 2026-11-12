"""HTTP routes. Each one translates between HTTP and a use case, nothing more."""

from uuid import UUID

from fastapi import FastAPI, HTTPException

from shadowfolio.domain.wallet import InvalidAmountError
from shadowfolio.interfaces.web.schemas import CreateWalletRequest, DepositRequest, WalletResponse
from shadowfolio.usecases.wallets import Wallets

# Until accounts exist, every wallet belongs to this owner.
LOCAL_OWNER = "local"


def create_app(wallets: Wallets) -> FastAPI:
    app = FastAPI(title="Shadowfolio")

    @app.post("/wallets", status_code=201)
    def create_wallet(request: CreateWalletRequest) -> WalletResponse:
        wallet = wallets.create(LOCAL_OWNER, request.name, request.currency, request.cash)
        return WalletResponse.from_wallet(wallet)

    @app.get("/wallets/{wallet_id}")
    def get_wallet(wallet_id: UUID) -> WalletResponse:
        wallet = wallets.get(wallet_id)
        if wallet is None:
            raise _wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @app.post("/wallets/{wallet_id}/deposits")
    def deposit(wallet_id: UUID, request: DepositRequest) -> WalletResponse:
        try:
            wallet = wallets.deposit(wallet_id, request.amount)
        except InvalidAmountError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if wallet is None:
            raise _wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    return app


def _wallet_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="wallet not found")
