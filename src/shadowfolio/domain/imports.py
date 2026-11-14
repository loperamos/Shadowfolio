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
    DIVIDEND = "dividend"
    FEE = "fee"  # a charge not tied to one trade
    SPLIT = "split"  # a stock split's rows; the wallet applies splits from market data
    SPIN_OFF = "spin_off"  # shares received from a company splitting off part of its business
    # A cash-statement row announcing a corporate action whose shares the trades statement books.
    CORPORATE_ACTION_NOTICE = "corporate_action_notice"
    INCOME = "income"  # interest, compensations; its amount is signed (negative for interest charged)
    # Money moving between accounts that are all the investor's (a broker and its partner bank, a cash fund).
    INTERNAL_TRANSFER = "internal_transfer"
    UNKNOWN = "unknown"  # a row the reader does not recognise


@dataclass(frozen=True)
class ImportRecord:
    """One operation read from a broker statement. Amounts are positive (the kind says which way they go), except
    for income, which can be either."""

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
    # Dividends only: `amount` is then what was credited in `currency` (the account's), and these are in the
    # dividend's own currency: before tax, the tax withheld, and the broker's fee.
    dividend_currency: str | None = None
    gross: Decimal | None = None
    tax: Decimal | None = None
    dividend_fee: Decimal | None = None
