"""Operations: things that happened in a wallet at a point in time."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from shadowfolio.domain.money import Currency


class OperationType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    BUY = "buy"
    SELL = "sell"


# Operations that bring cash into the wallet; all others take it out.
_CASH_IN = {OperationType.DEPOSIT, OperationType.SELL}


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
        """Signed effect on cash. Fees always reduce it."""
        signed = self.amount if self.type in _CASH_IN else -self.amount
        return signed - self.fees

    @property
    def share_delta(self) -> Decimal:
        """Signed effect on the traded symbol's holding; zero for cash operations."""
        if self.trade is None:
            return Decimal(0)
        return -self.trade.quantity if self.type is OperationType.SELL else self.trade.quantity
