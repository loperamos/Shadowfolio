"""Import records: what a broker statement says happened, before it becomes a wallet's operations."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class ImportKind(StrEnum):
    DEPOSIT = "deposit"  # money moved into the account from outside
    WITHDRAWAL = "withdrawal"  # money moved out of the account
    BUY = "buy"
    SELL = "sell"
    # A cash-statement row that only pays for, or receives, a trade already read as a buy or sell.
    TRADE_SETTLEMENT = "trade_settlement"
    # Money moving between accounts that are all the investor's (a broker and its partner bank, a cash fund).
    INTERNAL_TRANSFER = "internal_transfer"
    UNKNOWN = "unknown"  # a row the reader does not recognise


@dataclass(frozen=True)
class ImportRecord:
    """One operation read from a broker statement. Amounts are positive; the kind says which way they go."""

    kind: ImportKind
    timestamp: datetime  # timezone-aware
    amount: Decimal
    currency: str
    description: str  # the statement's own wording, to recognise the row
    # Trades only. `amount` is then the trade's value in `currency` (the account's), before fees.
    isin: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None  # per share, in `price_currency`
    price_currency: str | None = None
    fees: Decimal | None = None  # every fee of the trade, in `currency`
