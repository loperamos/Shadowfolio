"""Operations: things that happened in a wallet at a point in time.

Each kind is its own class and knows its own effect on the wallet. Amounts, quantities and
fees are always positive, as on a statement; the kind decides the sign.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from shadowfolio.domain.money import Currency


class OperationType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Trade:
    """What was traded, as the broker reports it. The price is in the listing's currency."""

    symbol: str
    quantity: Decimal
    price: Decimal
    price_currency: Currency


@dataclass(frozen=True)
class BaseOperation(ABC):
    """What every operation has and must answer. Each kind subclasses it."""

    type: ClassVar[OperationType]

    id: UUID
    timestamp: datetime

    @property
    @abstractmethod
    def cash_delta(self) -> Decimal:
        """Signed effect on the wallet's cash, in the wallet's currency."""

    @property
    @abstractmethod
    def holding_change(self) -> tuple[str, Decimal] | None:
        """The symbol whose holding changes and the signed quantity, or None."""


@dataclass(frozen=True)
class Deposit(BaseOperation):
    type: ClassVar[OperationType] = OperationType.DEPOSIT

    amount: Decimal

    @property
    def cash_delta(self) -> Decimal:
        return self.amount

    @property
    def holding_change(self) -> tuple[str, Decimal] | None:
        return None


@dataclass(frozen=True)
class Withdrawal(BaseOperation):
    type: ClassVar[OperationType] = OperationType.WITHDRAWAL

    amount: Decimal

    @property
    def cash_delta(self) -> Decimal:
        return -self.amount

    @property
    def holding_change(self) -> tuple[str, Decimal] | None:
        return None


@dataclass(frozen=True)
class _TradeOperation(BaseOperation, ABC):
    """`settled_amount` is the cash that moved before fees, in the wallet's currency.
    `fees` are in the wallet's currency too."""

    trade: Trade
    settled_amount: Decimal
    fees: Decimal


@dataclass(frozen=True)
class Buy(_TradeOperation):
    type: ClassVar[OperationType] = OperationType.BUY

    @property
    def cash_delta(self) -> Decimal:
        return -self.settled_amount - self.fees

    @property
    def holding_change(self) -> tuple[str, Decimal] | None:
        return self.trade.symbol, self.trade.quantity


@dataclass(frozen=True)
class Sell(_TradeOperation):
    type: ClassVar[OperationType] = OperationType.SELL

    @property
    def cash_delta(self) -> Decimal:
        return self.settled_amount - self.fees

    @property
    def holding_change(self) -> tuple[str, Decimal] | None:
        return self.trade.symbol, -self.trade.quantity


# Every concrete kind. Code that handles each kind matches on this, so mypy reports a kind
# that is not handled.
Operation = Deposit | Withdrawal | Buy | Sell
