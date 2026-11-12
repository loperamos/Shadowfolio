"""Wallet: a cash balance owned by a user."""

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID


class InvalidAmountError(ValueError):
    """An amount that must be positive is zero or negative."""


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"


@dataclass(frozen=True)
class Wallet:
    id: UUID
    owner_id: str
    name: str
    currency: Currency
    cash: Decimal

    def deposit(self, amount: Decimal) -> Self:
        if amount <= 0:
            raise InvalidAmountError("deposit amount must be positive")
        return replace(self, cash=self.cash + amount)
