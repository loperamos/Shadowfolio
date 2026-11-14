"""Import records: what a broker statement says happened, before it becomes a wallet's operations."""

from dataclasses import dataclass
from datetime import date, datetime
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
    DIVIDEND_REVERSED = "dividend_reversed"  # a dividend taken back after it was credited (often booked again later)
    FEE = "fee"  # a charge not tied to one trade
    SPLIT = "split"  # a stock split's rows; the wallet applies splits from market data
    SPIN_OFF = "spin_off"  # shares received from a company splitting off part of its business
    CASH_IN_LIEU = "cash_in_lieu"  # cash paid instead of a fraction of a share
    TAX_REFUND = "tax_refund"  # dividend tax paid back later
    TAX_CHARGED = "tax_charged"  # dividend tax charged later, apart from its dividend
    IPO_SUBSCRIPTION = "ipo_subscription"  # shares subscribed in an IPO, at the offer price
    ISIN_CHANGE = "isin_change"  # a holding moved from one identifier to another: one record for each side
    # A cash-statement row announcing a corporate action whose shares the trades statement books.
    CORPORATE_ACTION_NOTICE = "corporate_action_notice"
    INCOME = "income"  # interest, compensations; its amount is signed (negative for interest charged)
    # Money moving between accounts that are all the investor's (a broker and its partner bank, a cash fund).
    INTERNAL_TRANSFER = "internal_transfer"
    UNKNOWN = "unknown"  # a row the reader does not recognise


@dataclass(frozen=True)
class TradeDetails:
    """What a record that moves shares adds: a trade, or a corporate action's shares."""

    quantity: Decimal  # positive
    price: Decimal  # per share, in `price_currency`
    price_currency: str
    fees: Decimal  # every fee of the trade, in the record's currency
    venue: str | None = None  # the MIC of the venue it was executed on, when the statement gives it


@dataclass(frozen=True)
class DividendDetails:
    """What a dividend record adds, in the dividend's own currency, as the statement gives it."""

    currency: str
    gross: Decimal  # before tax
    tax: Decimal  # withheld
    fee: Decimal  # the broker's
    payment_date: date


@dataclass(frozen=True)
class ImportRecord:
    """One operation read from a broker statement. Amounts are positive (the kind says which way they go), except
    for income, which can be either."""

    kind: ImportKind
    timestamp: datetime  # timezone-aware
    # In `currency` (the account's): for a trade, its value before fees; for a dividend, what was credited.
    amount: Decimal
    currency: str
    description: str  # the statement's own wording, to recognise the row
    isin: str | None = None  # the security, for records about one
    trade: TradeDetails | None = None  # records that move shares
    dividend: DividendDetails | None = None  # dividends
