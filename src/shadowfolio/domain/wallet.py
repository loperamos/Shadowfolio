"""Wallet: a cash balance owned by a user."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


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
