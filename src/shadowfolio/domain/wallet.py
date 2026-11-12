"""Wallet: a timeline of operations owned by a user. Its cash is derived from the operations."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID


class DomainError(ValueError):
    """A request breaks a business rule."""


class InvalidAmountError(DomainError):
    """An amount that must be positive is zero or negative."""


class InsufficientCashError(DomainError):
    """The wallet does not have enough cash for the operation."""


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"


class OperationType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


@dataclass(frozen=True)
class Operation:
    id: UUID
    type: OperationType
    timestamp: datetime
    amount: Decimal

    @property
    def cash_delta(self) -> Decimal:
        """Signed effect on cash; `amount` itself is always positive."""
        return -self.amount if self.type is OperationType.WITHDRAWAL else self.amount


@dataclass(frozen=True)
class Wallet:
    id: UUID
    owner_id: str
    name: str
    currency: Currency
    operations: tuple[Operation, ...] = ()

    @property
    def cash(self) -> Decimal:
        return sum((op.cash_delta for op in self.operations), Decimal(0))

    def deposit(self, operation_id: UUID, amount: Decimal, at: datetime) -> Self:
        _require_positive(amount)
        return self._append(Operation(operation_id, OperationType.DEPOSIT, at, amount))

    def withdraw(self, operation_id: UUID, amount: Decimal, at: datetime) -> Self:
        _require_positive(amount)
        if amount > self.cash:
            raise InsufficientCashError(f"cannot withdraw {amount}, cash is {self.cash}")
        return self._append(Operation(operation_id, OperationType.WITHDRAWAL, at, amount))

    def _append(self, operation: Operation) -> Self:
        return replace(self, operations=(*self.operations, operation))


def _require_positive(amount: Decimal) -> None:
    if amount <= 0:
        raise InvalidAmountError("amount must be positive")
