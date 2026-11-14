"""Market data as traded, independent of any wallet."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from shadowfolio.domain.money import Currency


@dataclass(frozen=True)
class MinuteBar:
    """One minute of trading in a symbol, starting at `as_of`: its open, and the highest and lowest prices traded."""

    as_of: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    currency: Currency
