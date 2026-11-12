"""Request and response bodies of the HTTP API."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from shadowfolio.domain.wallet import Currency, Operation, OperationType, Wallet


class CreateWalletRequest(BaseModel):
    name: str
    currency: Currency
    cash: Decimal


class AmountRequest(BaseModel):
    amount: Decimal


class WalletResponse(BaseModel):
    id: UUID
    name: str
    currency: Currency
    cash: Decimal

    @classmethod
    def from_wallet(cls, wallet: Wallet) -> "WalletResponse":
        return cls(id=wallet.id, name=wallet.name, currency=wallet.currency, cash=wallet.cash)


class OperationResponse(BaseModel):
    id: UUID
    type: OperationType
    timestamp: datetime
    amount: Decimal

    @classmethod
    def from_operation(cls, operation: Operation) -> "OperationResponse":
        return cls(
            id=operation.id,
            type=operation.type,
            timestamp=operation.timestamp,
            amount=operation.amount,
        )
