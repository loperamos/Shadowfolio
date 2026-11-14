"""Reading DEGIRO's CSV exports in French (Transactions and Account) into import records.

A recipe rather than a model, in two steps:

1. Classify: every row of both exports gets exactly one DEGIRO row type (`RowType`), from its order ID and, for
   Account rows, its description (`ACCOUNT_ROW_TYPES`). Columns are read by position; times are Paris time and
   numbers use a decimal comma.
2. Assemble: the classified rows become import records, in three ways:
   - most rows are an operation of their own, or part of one already counted: one row, one record;
   - a corporate action's Transactions rows (no order ID) are a split by their shape, or else what the Account
     export announces for that security and day;
   - cash moving in another currency (a dividend with its tax and DEGIRO's fees, cash for a fraction of a share, tax
     paid back or charged later, other securities fees) waits there until a conversion with euros brings that
     currency's balance back to zero; the items it settles share its euros in proportion to their amounts. A
     dividend's rows, possibly booked and reversed several times, share its value date and become one record.
"""

import csv
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum, auto
from itertools import groupby
from zoneinfo import ZoneInfo

from shadowfolio.domain.imports import ImportKind, ImportRecord
from shadowfolio.domain.money import to_cents

TIMEZONE = ZoneInfo("Europe/Paris")
DATE_FORMAT = "%d-%m-%Y"
DATE_TIME_FORMAT = f"{DATE_FORMAT} %H:%M"
# The account's own currency: the Transactions export gives each trade's value and fees in it.
ACCOUNT_CURRENCY = "EUR"


class RowType(Enum):
    """What a DEGIRO row is. Every row of both exports gets exactly one."""

    # Transactions export
    EXECUTION = auto()  # a trade, with its order ID
    CORPORATE_ACTION = auto()  # shares moved by a corporate action: no order ID
    # Account export: a row of its own
    DEPOSIT = auto()
    WITHDRAWAL = auto()
    INTERNAL_TRANSFER = auto()  # between DEGIRO, the flatex bank cash account and the 2020 cash fund
    FUND_VALUE_CHANGE = auto()  # the 2020 cash fund's daily value change
    INTEREST = auto()  # interest on cash, and compensations
    CONNECTION_FEE = auto()  # the yearly fee for each exchange traded on
    SPLIT_ADJUSTMENT = auto()
    TRADE_CASH = auto()  # a trade's payment, fee or currency conversion: carries its order ID
    # Account export: announcing a corporate action whose shares the Transactions export moves
    SPIN_OFF_NOTICE = auto()
    ISIN_CHANGE_NOTICE = auto()
    IPO_NOTICE = auto()
    # Account export: cash that may be in another currency, waiting for a conversion
    DIVIDEND = auto()
    DIVIDEND_TAX = auto()
    SECURITIES_FEE = auto()  # DEGIRO's fee on a dividend or another securities operation
    CASH_IN_LIEU = auto()  # cash paid instead of a fraction of a share
    CONVERSION = auto()  # one side of a currency conversion not tied to a trade
    UNKNOWN = auto()


# Account rows without an order ID, by description; the first pattern that matches wins.
ACCOUNT_ROW_TYPES: list[tuple[re.Pattern[str], RowType]] = [
    (re.compile(pattern), row_type)
    for pattern, row_type in [
        (r"^(Dépôt flatex|Versement de fonds)$", RowType.DEPOSIT),
        (r"^(Retrait flatex|Retrait instantané SEPA)$", RowType.WITHDRAWAL),
        # flatex books a processed withdrawal out and back in; the "Retrait flatex" row is the real one.
        (r"^Processed Flatex Withdrawal$", RowType.INTERNAL_TRANSFER),
        (r"^(Degiro Cash Sweep Transfer|Virement (vers|depuis) votre Compte Espèces à la flatexDEGIRO Bank)", RowType.INTERNAL_TRANSFER),
        (r"^Conversion Fonds Monétaires finalisée", RowType.INTERNAL_TRANSFER),
        (r"^Variation Fonds Monétaires", RowType.FUND_VALUE_CHANGE),
        (r"^(Flatex Interest|Flatex Interest Income|Compensation Fonds Monétaires DEGIRO)$", RowType.INTEREST),
        (r"^Frais de connexion aux places boursières", RowType.CONNECTION_FEE),
        (r"^Ajustement fractionnement:", RowType.SPLIT_ADJUSTMENT),
        (r"^Spin-off:", RowType.SPIN_OFF_NOTICE),
        (r"^(Changement ISIN|Modification instrument):", RowType.ISIN_CHANGE_NOTICE),
        (r"^Introduction en bourse:", RowType.IPO_NOTICE),
        (r"^Dividende$", RowType.DIVIDEND),
        (r"^Impôts sur dividende$", RowType.DIVIDEND_TAX),
        (r"^Frais d’opération sur titres$", RowType.SECURITIES_FEE),
        (r"^Règlement espèces - Action$", RowType.CASH_IN_LIEU),
        (r"^Op[ée]ration de change - (Débit|Crédit)$", RowType.CONVERSION),
    ]
]

# Rows that are a record of their own, and its kind (an execution is a buy or a sell, by the sign of its quantity).
# Income keeps the row's sign; the other amounts are positive.
OWN_RECORD_KINDS = {
    RowType.DEPOSIT: ImportKind.DEPOSIT,
    RowType.WITHDRAWAL: ImportKind.WITHDRAWAL,
    RowType.INTERNAL_TRANSFER: ImportKind.INTERNAL_TRANSFER,
    RowType.FUND_VALUE_CHANGE: ImportKind.INCOME,
    RowType.INTEREST: ImportKind.INCOME,
    RowType.CONNECTION_FEE: ImportKind.FEE,
    RowType.SPLIT_ADJUSTMENT: ImportKind.SPLIT,
    RowType.TRADE_CASH: ImportKind.TRADE_SETTLEMENT,
    RowType.SPIN_OFF_NOTICE: ImportKind.CORPORATE_ACTION_NOTICE,
    RowType.ISIN_CHANGE_NOTICE: ImportKind.CORPORATE_ACTION_NOTICE,
    RowType.IPO_NOTICE: ImportKind.CORPORATE_ACTION_NOTICE,
    RowType.UNKNOWN: ImportKind.UNKNOWN,
}
# What the corporate action a notice announces is.
ANNOUNCED_KINDS = {
    RowType.SPIN_OFF_NOTICE: ImportKind.SPIN_OFF,
    RowType.ISIN_CHANGE_NOTICE: ImportKind.ISIN_CHANGE,
    RowType.IPO_NOTICE: ImportKind.IPO_SUBSCRIPTION,
}
# Rows of cash that may wait for a conversion, in the order read within a minute: paid cash first, so a tax or fee
# booked in the same minute finds its dividend.
WAITING_CASH_ORDER = [RowType.DIVIDEND, RowType.CASH_IN_LIEU, RowType.DIVIDEND_TAX, RowType.SECURITIES_FEE, RowType.CONVERSION]


@dataclass(frozen=True)
class _Row:
    """A row of either export, read and classified. Transactions rows also have a quantity, price and fees."""

    type: RowType
    timestamp: datetime
    date: str  # as printed
    value_date: str  # Account only, as printed: the day the money counts from, shared by a payment's rows
    product: str
    isin: str
    description: str
    currency: str
    amount: Decimal  # signed: negative when money leaves; for Transactions, in the account's currency
    order_id: str
    quantity: Decimal = Decimal(0)  # signed
    price: Decimal = Decimal(0)
    price_currency: str = ""
    fees: Decimal = Decimal(0)  # every fee of a trade, in the account's currency


class DegiroStatementReader:
    def read(self, transactions: str, account: str) -> list[ImportRecord]:
        """The records in the two exports, each given as its full text (header first), oldest first."""
        trades = [_transactions_row(cells) for cells in _cells(transactions)]
        # Oldest first; rows of the same minute keep DEGIRO's order, which lists them newest first.
        cash = sorted(reversed([_account_row(cells) for cells in _cells(account)]), key=lambda row: row.timestamp)
        records = [
            *_own_records(row for row in trades if row.type is RowType.EXECUTION),
            *_corporate_action_records([row for row in trades if row.type is RowType.CORPORATE_ACTION], cash),
            *_own_records(row for row in cash if row.type in OWN_RECORD_KINDS),
            *_waiting_cash_records([row for row in cash if row.type in WAITING_CASH_ORDER]),
        ]
        return sorted(records, key=lambda record: record.timestamp)


# Step 1: classify ------------------------------------------------------------------------------------------------


def _cells(text: str) -> list[list[str]]:
    """The cells of each row after the header."""
    return [cells for cells in csv.reader(text.splitlines()[1:]) if cells]


def _transactions_row(cells: list[str]) -> _Row:
    date, time, product, isin, _exchange, _venue, quantity, price, price_currency = cells[:9]
    amount, autofx_fee, brokerage_fee, order_id = cells[11], cells[13], cells[14], cells[16]
    return _Row(
        type=RowType.EXECUTION if order_id else RowType.CORPORATE_ACTION,
        timestamp=_timestamp(date, time),
        date=date,
        value_date="",
        product=product,
        isin=isin,
        description=product,
        currency=ACCOUNT_CURRENCY,
        amount=_number(amount),
        order_id=order_id,
        quantity=_number(quantity),
        price=_number(price),
        price_currency=price_currency,
        fees=abs(_number(autofx_fee)) + abs(_number(brokerage_fee)),
    )


def _account_row(cells: list[str]) -> _Row:
    date, time, value_date, product, isin, description, _fx, currency, amount = cells[:9]
    order_id = cells[11]
    # Every cash line of a trade carries its order ID: the payment, its fees, its currency conversion.
    row_type = (
        RowType.TRADE_CASH if order_id else next((t for pattern, t in ACCOUNT_ROW_TYPES if pattern.search(description)), RowType.UNKNOWN)
    )
    return _Row(row_type, _timestamp(date, time), date, value_date, product, isin, description, currency, _number(amount), order_id)


# Step 2a: one row, one record ------------------------------------------------------------------------------------


def _own_records(rows: Iterable[_Row]) -> list[ImportRecord]:
    return [_own_record(row) for row in rows]


def _own_record(row: _Row) -> ImportRecord:
    if row.type is RowType.EXECUTION:
        return _trade_record(row, ImportKind.BUY if row.quantity > 0 else ImportKind.SELL)
    kind = OWN_RECORD_KINDS[row.type]
    amount = row.amount if kind is ImportKind.INCOME else abs(row.amount)
    return ImportRecord(kind, row.timestamp, amount, row.currency, row.description)


def _trade_record(row: _Row, kind: ImportKind) -> ImportRecord:
    return ImportRecord(
        kind=kind,
        timestamp=row.timestamp,
        amount=abs(row.amount),
        currency=ACCOUNT_CURRENCY,
        description=row.product,
        isin=row.isin,
        quantity=abs(row.quantity),
        price=row.price,
        price_currency=row.price_currency,
        fees=row.fees,
    )


# Step 2b: corporate actions -------------------------------------------------------------------------------------


def _corporate_action_records(rows: list[_Row], account: list[_Row]) -> list[ImportRecord]:
    """A corporate action's Transactions rows: a split by its shape (two rows of one security at one moment, the old
    shares out and the new ones in, for the same money); otherwise what the Account export announces for that
    security that day; otherwise unknown."""
    notices: dict[tuple[str, str], list[_Row]] = {}
    for row in account:
        if row.type in ANNOUNCED_KINDS:
            notices.setdefault((row.date, row.isin), []).append(row)
    groups: dict[tuple[datetime, str], list[_Row]] = {}
    for row in rows:
        groups.setdefault((row.timestamp, row.isin), []).append(row)
    records = []
    for group in groups.values():
        for row in group:
            notice = _notice(row, notices.get((row.date, row.isin), []))
            if _is_split(group):
                records.append(_trade_record(row, ImportKind.SPLIT))
            elif notice is not None:
                records.append(_as_announced(row, notice))
            else:
                records.append(_trade_record(row, ImportKind.UNKNOWN))
    return records


def _is_split(rows: list[_Row]) -> bool:
    if len(rows) != len(("old shares", "new shares")):
        return False
    first, second = rows
    return (first.quantity > 0) != (second.quantity > 0) and first.amount + second.amount == 0


def _notice(row: _Row, notices: list[_Row]) -> _Row | None:
    """The notice a Transactions row books: the one at the same minute, or else the day's spin-off or subscription
    (DEGIRO books their shares at midnight, but announces them later that day)."""
    same_minute = [notice for notice in notices if notice.timestamp == row.timestamp]
    booked_at_midnight = [notice for notice in notices if notice.type in (RowType.SPIN_OFF_NOTICE, RowType.IPO_NOTICE)]
    candidates = same_minute or booked_at_midnight
    return candidates[0] if candidates else None


def _as_announced(row: _Row, notice: _Row) -> ImportRecord:
    """A corporate action's Transactions row, as announced. An IPO subscription's row has no price: what was paid,
    and when, is in the Account export."""
    kind = ANNOUNCED_KINDS[notice.type]
    if kind is not ImportKind.IPO_SUBSCRIPTION or not row.quantity:
        return _trade_record(row, kind)
    paid = abs(notice.amount)
    return replace(
        _trade_record(row, kind),
        timestamp=notice.timestamp,
        amount=paid,
        price=paid / abs(row.quantity),
        price_currency=ACCOUNT_CURRENCY,
        fees=Decimal(0),
    )


# Step 2c: cash waiting in another currency ----------------------------------------------------------------------


@dataclass
class _Waiting:
    """Cash in a currency, waiting to be settled in euros: a dividend (whose tax and fees may still follow), cash for
    a fraction, tax paid back or charged later, or a securities fee."""

    kind: ImportKind
    row: _Row  # the first row
    amount: Decimal  # signed, in the row's currency; for a dividend, before tax and fee
    tax: Decimal = Decimal(0)  # withheld, so positive
    fee: Decimal = Decimal(0)  # charged, so positive

    @property
    def net(self) -> Decimal:
        """In its currency: positive when paid in, negative when charged."""
        return self.amount - self.tax - self.fee


@dataclass
class _Pockets:
    """What waits in each currency."""

    by_currency: dict[str, list[_Waiting]] = field(default_factory=dict)

    def add(self, item: _Waiting) -> None:
        self.by_currency.setdefault(item.row.currency, []).append(item)

    def dividend(self, row: _Row) -> _Waiting | None:
        """The waiting dividend a row belongs to: same currency and value date, and the same security when the row
        names one (DEGIRO's fee rows do not)."""
        candidates = [
            item
            for item in self.by_currency.get(row.currency, [])
            if item.kind is ImportKind.DIVIDEND and item.row.value_date == row.value_date and (not row.isin or item.row.isin == row.isin)
        ]
        return candidates[-1] if candidates else None

    def take(self, currency: str, predicate: Callable[[_Waiting], bool]) -> list[_Waiting]:
        """Remove and return the items of `currency` matching `predicate`, in order."""
        items = self.by_currency.get(currency, [])
        taken = [item for item in items if predicate(item)]
        self.by_currency[currency] = [item for item in items if all(item is not other for other in taken)]
        return taken


def _waiting_cash_records(rows: list[_Row]) -> list[ImportRecord]:
    pockets = _Pockets()
    records: list[ImportRecord] = []
    for _, same_minute in groupby(rows, key=lambda row: row.timestamp):
        minute = sorted(same_minute, key=lambda row: WAITING_CASH_ORDER.index(row.type))
        for row in minute:
            dividend = pockets.dividend(row) if row.type in (RowType.DIVIDEND, RowType.DIVIDEND_TAX, RowType.SECURITIES_FEE) else None
            match row.type:
                case RowType.DIVIDEND if dividend:  # booked again, or reversed (a negative amount)
                    dividend.amount += row.amount
                case RowType.DIVIDEND:
                    pockets.add(_with_earlier_parts(_Waiting(ImportKind.DIVIDEND, row, row.amount), pockets))
                case RowType.DIVIDEND_TAX if dividend:
                    dividend.tax -= row.amount  # withheld (negative row), or given back (positive row)
                case RowType.SECURITIES_FEE if dividend:
                    dividend.fee -= row.amount
                case RowType.CASH_IN_LIEU:
                    pockets.add(_Waiting(ImportKind.CASH_IN_LIEU, row, row.amount))
                case RowType.DIVIDEND_TAX:  # apart from its dividend: paid back, or charged, later
                    pockets.add(_Waiting(ImportKind.TAX_REFUND if row.amount > 0 else ImportKind.TAX_CHARGED, row, row.amount))
                case RowType.SECURITIES_FEE:  # on another securities operation, or given back
                    pockets.add(_Waiting(ImportKind.FEE, row, row.amount))
        conversion = [row for row in minute if row.type is RowType.CONVERSION]
        if conversion:
            records += _converted(conversion, pockets)
        in_euros = pockets.take(ACCOUNT_CURRENCY, lambda item: True)  # no conversion needed
        records += _credited(in_euros, sum((item.net for item in in_euros), Decimal(0)))
    records += [_unknown(item.row) for items in pockets.by_currency.values() for item in items]
    return records


def _with_earlier_parts(dividend: _Waiting, pockets: _Pockets) -> _Waiting:
    """The dividend with the fees and taxes of its payment booked before it (e.g. an old fee given back just before the
    dividend is booked again), taken out of what waits on its own."""
    row = dividend.row
    parts = pockets.take(
        row.currency,
        lambda item: (
            item.row.value_date == row.value_date
            and (
                item.kind is ImportKind.FEE or (item.kind in (ImportKind.TAX_REFUND, ImportKind.TAX_CHARGED) and item.row.isin == row.isin)
            )
        ),
    )
    for part in parts:
        if part.kind is ImportKind.FEE:
            dividend.fee -= part.amount
        else:
            dividend.tax -= part.amount
    return dividend


def _converted(conversion: list[_Row], pockets: _Pockets) -> list[ImportRecord]:
    """What a conversion settles: the items waiting in its other currency, for the euros it moved. (Its rows are
    labelled "Débit" and "Crédit" inconsistently; the currencies and signs are what count.)"""
    euros = [row for row in conversion if row.currency == ACCOUNT_CURRENCY]
    other = [row for row in conversion if row.currency != ACCOUNT_CURRENCY]
    if len(euros) != 1 or len(other) != 1:
        return [_unknown(row) for row in conversion]
    euro, foreign = euros[0], other[0]
    items = _settled_by(pockets.by_currency.get(foreign.currency, []), -foreign.amount)
    if not items:  # nothing waiting: a leftover balance (e.g. a cent of rounding from a trade), converted as it is
        description = f"Leftover {foreign.currency} balance converted"
        return [ImportRecord(ImportKind.INCOME, euro.timestamp, euro.amount, ACCOUNT_CURRENCY, description)]
    pockets.take(foreign.currency, lambda item: any(item is settled for settled in items))
    return _credited(items, euro.amount)


def _settled_by(items: list[_Waiting], converted: Decimal) -> list[_Waiting]:
    """The waiting items a conversion of `converted` (positive when it takes money out of that currency) settles: the
    oldest ones adding up to exactly that, or else all of them."""
    total = Decimal(0)
    for count, item in enumerate(items, start=1):
        total += item.net
        if total == converted:
            return items[:count]
    return list(items)


def _credited(items: list[_Waiting], amount: Decimal) -> list[ImportRecord]:
    """The items as records sharing `amount` (signed, in euros) in proportion to their own amounts."""
    if not items:
        return []
    total = sum((item.net for item in items), Decimal(0))
    shares = [to_cents(amount * item.net / total) for item in items[:-1]]
    shares.append(amount - sum(shares, Decimal(0)))  # the last takes what rounding left
    return [_settled_record(item, abs(share)) for item, share in zip(items, shares, strict=True)]


def _settled_record(item: _Waiting, amount: Decimal) -> ImportRecord:
    row = item.row
    if item.kind is ImportKind.FEE and item.net > 0:
        return ImportRecord(ImportKind.INCOME, row.timestamp, amount, ACCOUNT_CURRENCY, f"{row.description} (given back)")
    if item.kind is ImportKind.FEE:
        return ImportRecord(ImportKind.FEE, row.timestamp, amount, ACCOUNT_CURRENCY, row.description)
    if item.kind is ImportKind.DIVIDEND and item.net < 0:  # reversed after it was converted
        return ImportRecord(ImportKind.DIVIDEND_REVERSED, row.timestamp, amount, ACCOUNT_CURRENCY, row.product, isin=row.isin)
    if item.kind is not ImportKind.DIVIDEND:
        return ImportRecord(item.kind, row.timestamp, amount, ACCOUNT_CURRENCY, row.product, isin=row.isin or None)
    return ImportRecord(
        kind=ImportKind.DIVIDEND,
        timestamp=row.timestamp,
        amount=amount,
        currency=ACCOUNT_CURRENCY,
        description=row.product,
        isin=row.isin,
        dividend_currency=row.currency,
        gross=item.amount,
        tax=item.tax,
        dividend_fee=item.fee,
        payment_date=_date(row.value_date),
    )


def _unknown(row: _Row) -> ImportRecord:
    return ImportRecord(ImportKind.UNKNOWN, row.timestamp, abs(row.amount), row.currency, row.description)


# Parsing --------------------------------------------------------------------------------------------------------


def _timestamp(date: str, time: str) -> datetime:
    """DEGIRO's Paris time, in UTC."""
    return datetime.strptime(f"{date} {time}", DATE_TIME_FORMAT).replace(tzinfo=TIMEZONE).astimezone(UTC)


def _date(text: str) -> date:
    """A calendar date as DEGIRO prints it (DD-MM-YYYY)."""
    day, month, year = (int(part) for part in text.split("-"))
    return date(year, month, day)


def _number(text: str) -> Decimal:
    """A French-formatted number: decimal comma, spaces (of any width) between thousands. An empty cell is zero."""
    cleaned = re.sub(r"\s", "", text).replace(",", ".")
    return Decimal(cleaned) if cleaned else Decimal(0)
