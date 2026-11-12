"""Request and response bodies of the HTTP API."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from shadowfolio.domain.wallet import Currency, Wallet


class CreateWalletRequest(BaseModel):
    name: str
    currency: Currency
    cash: Decimal


class DepositRequest(BaseModel):
    amount: Decimal


class WalletResponse(BaseModel):
    id: UUID
    name: str
    currency: Currency
    cash: Decimal

    @classmethod
    def from_wallet(cls, wallet: Wallet) -> "WalletResponse":
        return cls(id=wallet.id, name=wallet.name, currency=wallet.currency, cash=wallet.cash)
