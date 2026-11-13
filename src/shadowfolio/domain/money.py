"""Currencies and exchange rates."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
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


CENT = Decimal("0.01")


def to_cents(amount: Decimal) -> Decimal:
    """Rounded to cents, half to even (banker's rounding), so rounding errors do not drift one way."""
    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)
