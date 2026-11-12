"""Wallet: a timeline of operations owned by a user. Cash and holdings are derived from it."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from shadowfolio.domain.errors import InsufficientCashError, InsufficientSharesError, InvalidAmountError, MissingSettledAmountError
from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Deposit, Operation, Sell, Trade, Withdrawal


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
        """Shares held per symbol. Symbols sold out entirely are left out."""
        return _replay(self.operations)

    def copy(self, wallet_id: UUID, name: str, new_operation_id: Callable[[], UUID]) -> Self:
        """A new wallet with the same owner, currency and history. Every operation gets a new id,
        so the copy's history can change independently."""
        operations = tuple(replace(op, id=new_operation_id()) for op in self.operations)
        return replace(self, id=wallet_id, name=name, operations=operations)

    def deposit(self, operation_id: UUID, amount: Decimal, at: datetime) -> Self:
        _require_positive(amount, "amount")
        return self._with(Deposit(operation_id, at, amount))

    def withdraw(self, operation_id: UUID, amount: Decimal, at: datetime) -> Self:
        _require_positive(amount, "amount")
        return self._with(Withdrawal(operation_id, at, amount))

    def buy(
        self, operation_id: UUID, trade: Trade, at: datetime, settled_amount: Decimal | None = None, fees: Decimal = Decimal(0)
    ) -> Self:
        """Record a buy. `settled_amount` is what left the wallet before fees, in its currency."""
        return self._trade(Buy, operation_id, trade, at, settled_amount, fees)

    def sell(
        self, operation_id: UUID, trade: Trade, at: datetime, settled_amount: Decimal | None = None, fees: Decimal = Decimal(0)
    ) -> Self:
        """Record a sell. `settled_amount` is what entered the wallet before fees, in its
        currency."""
        return self._trade(Sell, operation_id, trade, at, settled_amount, fees)

    def _trade(
        self, kind: type[Buy] | type[Sell], operation_id: UUID, trade: Trade, at: datetime, settled_amount: Decimal | None, fees: Decimal
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
        return self._with(kind(operation_id, at, trade, settled_amount, fees))

    def _with(self, operation: Operation) -> Self:
        """Insert the operation at its timestamp and check the whole timeline.

        Operations with equal timestamps keep the order in which they were added.
        """
        timeline = tuple(sorted((*self.operations, operation), key=lambda op: op.timestamp))
        _replay(timeline)
        return replace(self, operations=timeline)


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
