"""Orders: requests to buy or sell, placed now, that the fill model turns into trades when market prices allow.

A market order fills at the first price after it was placed (the open of the next minute bar), so never with a price
from before it: one placed while the market is closed waits for the next open. Cash and shares are checked when it
fills; an order the wallet cannot cover then is rejected, with the reason.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from shadowfolio.domain.errors import InvalidAmountError, OrderNotOpenError


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    OPEN = "open"  # waiting for a price
    FILLED = "filled"  # became the trade with the order's id
    CANCELLED = "cancelled"
    REJECTED = "rejected"  # the wallet could not cover it when it would have filled


@dataclass(frozen=True)
class Order:
    id: UUID  # also the id of the trade it fills as
    side: OrderSide
    symbol: str
    quantity: Decimal
    placed_at: datetime
    reason: str = ""  # why it was placed, kept as a decision log
    status: OrderStatus = OrderStatus.OPEN
    closed_at: datetime | None = None  # when it filled (the price's time), was cancelled or rejected
    rejection: str | None = None  # why it was rejected

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise InvalidAmountError("quantity must be positive")

    @property
    def is_open(self) -> bool:
        return self.status is OrderStatus.OPEN

    def filled(self, at: datetime) -> Self:
        return self._closed(OrderStatus.FILLED, at)

    def cancelled(self, at: datetime) -> Self:
        if not self.is_open:
            raise OrderNotOpenError("only an open order can be cancelled")
        return self._closed(OrderStatus.CANCELLED, at)

    def rejected(self, at: datetime, reason: str) -> Self:
        return replace(self._closed(OrderStatus.REJECTED, at), rejection=reason)

    def _closed(self, status: OrderStatus, at: datetime) -> Self:
        return replace(self, status=status, closed_at=at)
