"""Wallet: a timeline of operations owned by a user. Its cash is derived from the operations."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID


class InvalidAmountError(ValueError):
    """An amount that must be positive is zero or negative."""


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"


class OperationType(StrEnum):
    DEPOSIT = "deposit"


@dataclass(frozen=True)
class Operation:
    id: UUID
    type: OperationType
    timestamp: datetime
    amount: Decimal


@dataclass(frozen=True)
class Wallet:
    id: UUID
    owner_id: str
    name: str
    currency: Currency
    operations: tuple[Operation, ...] = ()

    @property
    def cash(self) -> Decimal:
        return sum((op.amount for op in self.operations), Decimal(0))

    def deposit(self, operation_id: UUID, amount: Decimal, at: datetime) -> Self:
        if amount <= 0:
            raise InvalidAmountError("deposit amount must be positive")
        operation = Operation(operation_id, OperationType.DEPOSIT, at, amount)
        return replace(self, operations=(*self.operations, operation))
