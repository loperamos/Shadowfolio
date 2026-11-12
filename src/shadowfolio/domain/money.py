"""Currencies and exchange rates."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"


@dataclass(frozen=True)
class FxRate:
    """How many units of the quote currency one unit of the base currency buys, on a date."""

    base: Currency
    quote: Currency
    rate: Decimal
    as_of: date
