"""HTTP API."""

import os
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.application import wallets
from shadowfolio.domain.wallet import Currency, Wallet
from shadowfolio.ports.wallet_repository import WalletRepository

# Until accounts exist, every wallet belongs to this owner.
LOCAL_OWNER = "local"


class CreateWalletRequest(BaseModel):
    name: str
    currency: Currency
    cash: Decimal


class WalletResponse(BaseModel):
    id: UUID
    name: str
    currency: Currency
    cash: Decimal

    @classmethod
    def from_wallet(cls, wallet: Wallet) -> "WalletResponse":
        return cls(id=wallet.id, name=wallet.name, currency=wallet.currency, cash=wallet.cash)


def create_app(repo: WalletRepository) -> FastAPI:
    app = FastAPI(title="Shadowfolio")

    @app.post("/wallets", status_code=201)
    def create_wallet(request: CreateWalletRequest) -> WalletResponse:
        wallet = wallets.create_wallet(
            repo, LOCAL_OWNER, request.name, request.currency, request.cash
        )
        return WalletResponse.from_wallet(wallet)

    @app.get("/wallets/{wallet_id}")
    def get_wallet(wallet_id: UUID) -> WalletResponse:
        wallet = wallets.get_wallet(repo, wallet_id)
        if wallet is None:
            raise HTTPException(status_code=404, detail="wallet not found")
        return WalletResponse.from_wallet(wallet)

    return app


def create_default_app() -> FastAPI:
    """App wired to the SQLite file at $SHADOWFOLIO_DB (default: ./shadowfolio.db)."""
    path = Path(os.environ.get("SHADOWFOLIO_DB", "shadowfolio.db"))
    return create_app(SqliteWalletRepository(path))
