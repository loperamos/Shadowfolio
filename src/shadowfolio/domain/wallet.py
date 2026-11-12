"""Wallet: a timeline of operations owned by a user. Cash and holdings are derived from it."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID


class DomainError(ValueError):
    """A request breaks a business rule."""


class InvalidAmountError(DomainError):
    """An amount, quantity or price is out of range."""


class InsufficientCashError(DomainError):
    """The wallet would not have enough cash at some point of its timeline."""


class MissingSettledAmountError(DomainError):
    """A trade in a foreign currency needs the amount settled in the wallet's currency."""


class FutureTimestampError(DomainError):
    """An operation is dated after now."""


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"


class OperationType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    BUY = "buy"


@dataclass(frozen=True)
class Trade:
    """What was traded, as the broker reports it. The price is in the listing's currency."""

    symbol: str
    quantity: Decimal
    price: Decimal
    price_currency: Currency


@dataclass(frozen=True)
class Operation:
    """`amount` is always positive and in the wallet's currency; for a trade it is the settled
    amount before fees. `fees` are in the wallet's currency too."""

    id: UUID
    type: OperationType
    timestamp: datetime
    amount: Decimal
    fees: Decimal = Decimal(0)
    trade: Trade | None = None

    @property
    def cash_delta(self) -> Decimal:
        """Signed effect on cash."""
        if self.type is OperationType.DEPOSIT:
            return self.amount - self.fees
        return -self.amount - self.fees


@dataclass(frozen=True)
class Wallet:
    id: UUID
    owner_id: str
    name: str
    currency: Currency
    operations: tuple[Operation, ...] = ()  # oldest first

    @property
    def cash(self) -> Decimal:
        return sum((op.cash_delta for op in self.operations), Decimal(0))

    @property
    def holdings(self) -> dict[str, Decimal]:
        """Shares held per symbol."""
        held: dict[str, Decimal] = {}
        for op in self.operations:
            if op.trade is not None:
                held[op.trade.symbol] = held.get(op.trade.symbol, Decimal(0)) + op.trade.quantity
        return held

    def deposit(self, operation_id: UUID, amount: Decimal, at: datetime) -> Self:
        _require_positive(amount, "amount")
        return self._with(Operation(operation_id, OperationType.DEPOSIT, at, amount))

    def withdraw(self, operation_id: UUID, amount: Decimal, at: datetime) -> Self:
        _require_positive(amount, "amount")
        return self._with(Operation(operation_id, OperationType.WITHDRAWAL, at, amount))

    def buy(
        self,
        operation_id: UUID,
        trade: Trade,
        at: datetime,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
    ) -> Self:
        """Record a buy. `settled_amount` is what left the wallet before fees, in its currency;
        it is required when the price is in another currency, and defaults to quantity × price
        otherwise."""
        _require_positive(trade.quantity, "quantity")
        _require_positive(trade.price, "price")
        if fees < 0:
            raise InvalidAmountError("fees must not be negative")
        if settled_amount is None:
            if trade.price_currency is not self.currency:
                raise MissingSettledAmountError(
                    f"price is in {trade.price_currency}; settled amount in {self.currency} needed"
                )
            settled_amount = trade.quantity * trade.price
        _require_positive(settled_amount, "settled amount")
        return self._with(
            Operation(operation_id, OperationType.BUY, at, settled_amount, fees, trade)
        )

    def _with(self, operation: Operation) -> Self:
        """Insert the operation at its timestamp and check the whole timeline.

        Operations with equal timestamps keep the order in which they were added.
        """
        timeline = tuple(sorted((*self.operations, operation), key=lambda op: op.timestamp))
        cash = Decimal(0)
        for op in timeline:
            cash += op.cash_delta
            if cash < 0:
                raise InsufficientCashError(f"cash would be {cash} on {op.timestamp.isoformat()}")
        return replace(self, operations=timeline)


def _require_positive(value: Decimal, name: str) -> None:
    if value <= 0:
        raise InvalidAmountError(f"{name} must be positive")
