"""Wallet: a timeline of operations owned by a user. Cash and holdings are derived from it."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from shadowfolio.domain.errors import (
    InsufficientCashError,
    InsufficientSharesError,
    InvalidAmountError,
    InvalidNameError,
    MissingSettledAmountError,
    OperationNotFoundError,
    OperationTypeChangeError,
)
from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Deposit, Operation, Sell, Trade, Withdrawal


@dataclass(frozen=True)
class Wallet:
    id: UUID
    owner_id: str
    name: str
    currency: Currency
    operations: tuple[Operation, ...] = ()  # oldest first

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidNameError("name must not be blank")

    @property
    def cash(self) -> Decimal:
        return sum((op.cash_delta for op in self.operations), Decimal(0))

    @property
    def holdings(self) -> dict[str, Decimal]:
        """Shares held per symbol. Symbols sold out entirely are left out."""
        return _replay(self.operations)

    def copy(self, wallet_id: UUID, name: str, new_operation_id: Callable[[], UUID]) -> Self:
        """A new wallet with the same owner, currency and history. Every operation gets a new id,
        so the copy's history can change independently."""
        operations = tuple(replace(op, id=new_operation_id()) for op in self.operations)
        return replace(self, id=wallet_id, name=name, operations=operations)

    def rename(self, name: str) -> Self:
        return replace(self, name=name)

    # Every method that records an operation can instead replace an existing one of the same kind (`replacing=<its id>`):
    # the new version takes its place in a single check of the timeline, so an edit never fails halfway.

    def deposit(self, operation_id: UUID, amount: Decimal, at: datetime, replacing: UUID | None = None) -> Self:
        _require_positive(amount, "amount")
        return self._with(Deposit(operation_id, at, amount), replacing)

    def withdraw(self, operation_id: UUID, amount: Decimal, at: datetime, replacing: UUID | None = None) -> Self:
        _require_positive(amount, "amount")
        return self._with(Withdrawal(operation_id, at, amount), replacing)

    def buy(
        self,
        operation_id: UUID,
        trade: Trade,
        at: datetime,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Self:
        """Record a buy. `settled_amount` is what left the wallet before fees, in its currency."""
        return self._trade(Buy, operation_id, trade, at, settled_amount, fees, replacing)

    def sell(
        self,
        operation_id: UUID,
        trade: Trade,
        at: datetime,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Self:
        """Record a sell. `settled_amount` is what entered the wallet before fees, in its
        currency."""
        return self._trade(Sell, operation_id, trade, at, settled_amount, fees, replacing)

    def remove_operation(self, operation_id: UUID) -> Self:
        """Remove an operation; what is left must still be a valid timeline."""
        remaining = self._without(operation_id)
        _replay(remaining)
        return replace(self, operations=remaining)

    def _trade(
        self,
        kind: type[Buy] | type[Sell],
        operation_id: UUID,
        trade: Trade,
        at: datetime,
        settled_amount: Decimal | None,
        fees: Decimal,
        replacing: UUID | None,
    ) -> Self:
        """`settled_amount` is required when the price is in another currency than the
        wallet's, and defaults to quantity × price otherwise."""
        _require_positive(trade.quantity, "quantity")
        _require_positive(trade.price, "price")
        if fees < 0:
            raise InvalidAmountError("fees must not be negative")
        if settled_amount is None:
            if trade.price_currency is not self.currency:
                raise MissingSettledAmountError(f"price is in {trade.price_currency}; settled amount in {self.currency} needed")
            settled_amount = trade.quantity * trade.price
        _require_positive(settled_amount, "settled amount")
        return self._with(kind(operation_id, at, trade, settled_amount, fees), replacing)

    def _with(self, operation: Operation, replacing: UUID | None = None) -> Self:
        """Insert the operation at its timestamp, in place of `replacing` if given, and check the whole timeline.

        Operations with equal timestamps keep the order in which they were added.
        """
        if replacing is not None and self._get(replacing).type is not operation.type:
            raise OperationTypeChangeError("the type of an operation cannot change; delete it and add a new one")
        others = self.operations if replacing is None else self._without(replacing)
        timeline = tuple(sorted((*others, operation), key=lambda op: op.timestamp))
        _replay(timeline)
        return replace(self, operations=timeline)

    def _get(self, operation_id: UUID) -> Operation:
        for op in self.operations:
            if op.id == operation_id:
                return op
        raise OperationNotFoundError(f"no operation {operation_id}")

    def _without(self, operation_id: UUID) -> tuple[Operation, ...]:
        remaining = tuple(op for op in self.operations if op.id != operation_id)
        if len(remaining) == len(self.operations):
            raise OperationNotFoundError(f"no operation {operation_id}")
        return remaining


def _replay(timeline: tuple[Operation, ...]) -> dict[str, Decimal]:
    """Apply operations in order and return the holdings, failing if cash or a holding would
    go negative at any point."""
    cash = Decimal(0)
    held: dict[str, Decimal] = {}
    for op in timeline:
        cash += op.cash_delta
        if cash < 0:
            raise InsufficientCashError(f"cash would be {cash} on {op.timestamp.isoformat()}")
        change = op.holding_change
        if change is not None:
            symbol, delta = change
            quantity = held.get(symbol, Decimal(0)) + delta
            if quantity < 0:
                raise InsufficientSharesError(f"would hold {quantity} {symbol} on {op.timestamp.isoformat()}")
            if quantity:
                held[symbol] = quantity
            else:
                held.pop(symbol, None)
    return held


def _require_positive(value: Decimal, name: str) -> None:
    if value <= 0:
        raise InvalidAmountError(f"{name} must be positive")
