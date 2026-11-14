"""Reading DEGIRO's CSV exports in French (Transactions and Account) into import records.

A recipe rather than a model: columns are read by position and Account rows are recognised by their description.
DEGIRO France writes times in Paris time and numbers with a decimal comma.

Cash moving in another currency waits there until a conversion with euros brings that currency's balance back to
zero: money paid in (a dividend, with its tax withheld and DEGIRO's fee; cash for a fraction of a share; tax paid
back) is converted into euros, and money charged (a fee, or tax, without a dividend) is covered by converting euros.
The items a conversion settles share its euros in proportion to their amounts. A dividend's rows (the dividend, its
tax and DEGIRO's fees, each possibly booked and reversed several times) share its value date and are read together as
one record. Cash moving in euros is settled at once.
"""

import csv
import re
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum, auto
from itertools import groupby
from zoneinfo import ZoneInfo

from shadowfolio.domain.imports import ImportKind, ImportRecord
from shadowfolio.domain.money import to_cents

TIMEZONE = ZoneInfo("Europe/Paris")
DATE_TIME_FORMAT = "%d-%m-%Y %H:%M"
# The account's own currency: the Transactions export gives each trade's value and fees in it.
ACCOUNT_CURRENCY = "EUR"

# Account rows by description; the first pattern that matches wins.
ACCOUNT_PATTERNS: list[tuple[re.Pattern[str], ImportKind]] = [
    (re.compile(pattern), kind)
    for pattern, kind in [
        (r"^(Dépôt flatex|Versement de fonds)$", ImportKind.DEPOSIT),
        (r"^(Retrait flatex|Retrait instantané SEPA)$", ImportKind.WITHDRAWAL),
        # flatex books a processed withdrawal out and back in; the "Retrait flatex" row is the real one.
        (r"^Processed Flatex Withdrawal$", ImportKind.INTERNAL_TRANSFER),
        (r"^(Degiro Cash Sweep Transfer|Virement (vers|depuis) votre Compte Espèces à la flatexDEGIRO Bank)", ImportKind.INTERNAL_TRANSFER),
        # The 2020 cash fund: moving cash into or out of it is internal; its daily value changes are income.
        (r"^Conversion Fonds Monétaires finalisée", ImportKind.INTERNAL_TRANSFER),
        (r"^Variation Fonds Monétaires", ImportKind.INCOME),
        (r"^Frais de connexion aux places boursières", ImportKind.FEE),
        (r"^Ajustement fractionnement:", ImportKind.SPLIT),
        (r"^(Spin-off|Changement ISIN|Modification instrument|Introduction en bourse):", ImportKind.CORPORATE_ACTION_NOTICE),
        (r"^(Flatex Interest|Flatex Interest Income|Compensation Fonds Monétaires DEGIRO)$", ImportKind.INCOME),
    ]
]


# Account rows announcing a corporate action, and what the Transactions rows of that security on that day are.
ACTION_PATTERNS: list[tuple[re.Pattern[str], ImportKind]] = [
    (re.compile(r"^Spin-off:"), ImportKind.SPIN_OFF),
    (re.compile(r"^(Changement ISIN|Modification instrument):"), ImportKind.ISIN_CHANGE),
    (re.compile(r"^Introduction en bourse:"), ImportKind.IPO_SUBSCRIPTION),
]


@dataclass(frozen=True)
class _Announcement:
    """A corporate action as the Account export announces it: when, and the cash it moved (an IPO's price)."""

    kind: ImportKind
    timestamp: datetime
    amount: Decimal


class _Part(Enum):
    """The Account rows of cash that may need converting: a dividend (with its tax and fee), cash for a fraction."""

    DIVIDEND = auto()
    CASH_IN_LIEU = auto()
    TAX = auto()
    FEE = auto()
    CONVERSION = auto()


# Paid cash first, so a tax or fee booked in the same minute finds its dividend.
PART_ORDER = [_Part.DIVIDEND, _Part.CASH_IN_LIEU, _Part.TAX, _Part.FEE, _Part.CONVERSION]
CASH_PATTERNS: list[tuple[re.Pattern[str], _Part]] = [
    (re.compile(pattern), part)
    for pattern, part in [
        (r"^Dividende$", _Part.DIVIDEND),
        (r"^Règlement espèces - Action$", _Part.CASH_IN_LIEU),
        (r"^Impôts sur dividende$", _Part.TAX),
        (r"^Frais d’opération sur titres$", _Part.FEE),
        (r"^Op[ée]ration de change - (Débit|Crédit)$", _Part.CONVERSION),
    ]
]


@dataclass(frozen=True)
class _AccountRow:
    timestamp: datetime
    value_date: str  # as printed: the day the money counts from, shared by a payment's rows
    product: str
    isin: str
    description: str
    currency: str
    amount: Decimal  # signed: negative when money leaves
    order_id: str


@dataclass
class _OpenCash:
    """Cash paid in a security's name (a dividend, whose tax and fee may still follow, or cash for a fraction),
    waiting to be credited in euros."""

    kind: ImportKind
    row: _AccountRow  # the first row
    amount: Decimal  # signed, in the row's currency; for a dividend, before tax and fee
    tax: Decimal = Decimal(0)  # withheld, so positive
    fee: Decimal = Decimal(0)  # charged, so positive

    @property
    def net(self) -> Decimal:
        """In its currency: positive when paid in, negative when charged."""
        return self.amount - self.tax - self.fee


class DegiroStatementReader:
    def read(self, transactions: str, account: str) -> list[ImportRecord]:
        """The records in the two exports, each given as its full text (header first), oldest first."""
        account_rows = _rows(account)
        actions = _announced_actions(account_rows)
        records = [*_transaction_records(_rows(transactions), actions), *_account_records(account_rows)]
        return sorted(records, key=lambda record: record.timestamp)


def _rows(text: str) -> list[list[str]]:
    """The cells of each row after the header."""
    return [cells for cells in csv.reader(text.splitlines()[1:]) if cells]


def _announced_actions(account_rows: list[list[str]]) -> dict[tuple[str, str], list[_Announcement]]:
    """The corporate actions the Account export announces, by day and ISIN (a day can have several, e.g. an IPO
    subscription and then the change to the listed shares)."""
    actions: dict[tuple[str, str], list[_Announcement]] = {}
    for cells in account_rows:
        row = _account_row(cells)
        kind = next((kind for pattern, kind in ACTION_PATTERNS if pattern.search(row.description)), None)
        if kind is not None and not row.order_id:
            actions.setdefault((cells[0], row.isin), []).append(_Announcement(kind, row.timestamp, abs(row.amount)))
    return actions


def _announcement(record: ImportRecord, announcements: list[_Announcement]) -> _Announcement | None:
    """The announcement a Transactions row books: the one at the same minute, or else the day's other one (DEGIRO
    books a spin-off's or a subscription's shares at midnight, but announces them later that day)."""
    same_minute = [a for a in announcements if a.timestamp == record.timestamp]
    others = [a for a in announcements if a.kind in (ImportKind.SPIN_OFF, ImportKind.IPO_SUBSCRIPTION)]
    candidates = same_minute or others
    return candidates[0] if candidates else None


def _transaction_records(rows: list[list[str]], actions: dict[tuple[str, str], list[_Announcement]]) -> list[ImportRecord]:
    """Executions, identified by their order ID, and the rows corporate actions book without one: a split is
    recognised by its shape, other actions by what the Account export announces for that security that day."""
    records = [_transaction(cells) for cells in rows]
    # Corporate-action rows (no order ID), grouped by moment and security.
    groups: dict[tuple[datetime, str], list[int]] = {}
    for index, cells in enumerate(rows):
        if not cells[16]:
            groups.setdefault((records[index].timestamp, cells[3]), []).append(index)
    for indexes in groups.values():
        group = [rows[index] for index in indexes]
        announcements = actions.get((group[0][0], group[0][3]), [])
        for index in indexes:
            if _is_split(group):
                records[index] = replace(records[index], kind=ImportKind.SPLIT)
            elif announcement := _announcement(records[index], announcements):
                records[index] = _as_announced(records[index], announcement)
    return records


def _as_announced(record: ImportRecord, announcement: _Announcement) -> ImportRecord:
    """A corporate-action row of Transactions, as the Account export describes it. The Transactions row of an IPO
    subscription has no price: what was paid, and when, is in the Account export."""
    if announcement.kind is not ImportKind.IPO_SUBSCRIPTION or not record.quantity:
        return replace(record, kind=announcement.kind)
    return replace(
        record,
        kind=ImportKind.IPO_SUBSCRIPTION,
        timestamp=announcement.timestamp,
        amount=announcement.amount,
        price=announcement.amount / record.quantity,
        price_currency=ACCOUNT_CURRENCY,
        fees=Decimal(0),
    )


def _is_split(rows: list[list[str]]) -> bool:
    """A split is booked as two rows of one security at the same moment: the old shares out and the new ones in, for
    the same money."""
    if len(rows) != len(("old shares", "new shares")):
        return False
    first, second = rows
    opposite = (_number(first[6]) > 0) != (_number(second[6]) > 0)
    return opposite and _number(first[11]) + _number(second[11]) == 0


def _transaction(cells: list[str]) -> ImportRecord:
    date, time, product, isin, _exchange, _venue, quantity, price, price_currency = cells[:9]
    amount, autofx_fee, brokerage_fee, order_id = cells[11], cells[13], cells[14], cells[16]
    shares = _number(quantity)
    return ImportRecord(
        # Without an order ID, a corporate action: read as unknown unless recognised (see _transaction_records).
        kind=(ImportKind.BUY if shares > 0 else ImportKind.SELL) if order_id else ImportKind.UNKNOWN,
        timestamp=_timestamp(date, time),
        amount=abs(_number(amount)),
        currency=ACCOUNT_CURRENCY,
        description=product,
        isin=isin,
        quantity=abs(shares),
        price=_number(price),
        price_currency=price_currency,
        fees=abs(_number(autofx_fee)) + abs(_number(brokerage_fee)),
    )


def _account_records(rows: list[list[str]]) -> list[ImportRecord]:
    # Oldest first; rows of the same minute keep DEGIRO's order, which lists them newest first.
    account_rows = sorted(reversed([_account_row(cells) for cells in rows]), key=lambda row: row.timestamp)
    records: list[ImportRecord] = []
    waiting: dict[str, list[_OpenCash]] = {}  # by currency
    for _, same_minute in groupby(account_rows, key=lambda row: row.timestamp):
        minute = sorted(same_minute, key=_part_order)
        for row in minute:
            part = None if row.order_id else _part(row)
            dividend = _waiting_dividend(waiting, row) if part in (_Part.DIVIDEND, _Part.TAX, _Part.FEE) else None
            if part is _Part.DIVIDEND and dividend:  # booked again, or reversed (a negative amount)
                dividend.amount += row.amount
            elif part is _Part.DIVIDEND:
                new_dividend = _with_earlier_parts(_OpenCash(ImportKind.DIVIDEND, row, row.amount), waiting)
                waiting.setdefault(row.currency, []).append(new_dividend)
            elif part is _Part.TAX and dividend:
                dividend.tax -= row.amount  # withheld (negative row), or given back (positive row)
            elif part is _Part.FEE and dividend:
                dividend.fee -= row.amount
            elif part is _Part.CASH_IN_LIEU:
                waiting.setdefault(row.currency, []).append(_OpenCash(ImportKind.CASH_IN_LIEU, row, row.amount))
            elif part is _Part.TAX:  # apart from its dividend: paid back, or charged, later
                kind = ImportKind.TAX_REFUND if row.amount > 0 else ImportKind.TAX_CHARGED
                waiting.setdefault(row.currency, []).append(_OpenCash(kind, row, row.amount))
            elif part is _Part.FEE:  # on another securities operation, or given back
                waiting.setdefault(row.currency, []).append(_OpenCash(ImportKind.FEE, row, row.amount))
            elif part is _Part.CONVERSION:
                continue  # read as a pair below
            elif part is None:
                records.append(_simple_record(row))
            else:
                records.append(_unknown(row))
        conversion = [row for row in minute if not row.order_id and _part(row) is _Part.CONVERSION]
        if conversion:
            records += _converted(conversion, waiting)
        in_euros = waiting.pop(ACCOUNT_CURRENCY, [])  # no conversion needed
        records += _credited(in_euros, sum((item.net for item in in_euros), Decimal(0)), ACCOUNT_CURRENCY)
    records += [_unknown(item.row) for items in waiting.values() for item in items]
    return records


def _account_row(cells: list[str]) -> _AccountRow:
    date, time, value_date, product, isin, description, _fx, currency, amount = cells[:9]
    return _AccountRow(_timestamp(date, time), value_date, product, isin, description, currency, _number(amount), cells[11])


def _part(row: _AccountRow) -> _Part | None:
    return next((part for pattern, part in CASH_PATTERNS if pattern.search(row.description)), None)


def _part_order(row: _AccountRow) -> int:
    part = None if row.order_id else _part(row)
    return PART_ORDER.index(part) if part else len(PART_ORDER)


def _with_earlier_parts(dividend: _OpenCash, waiting: dict[str, list[_OpenCash]]) -> _OpenCash:
    """The dividend with the fees and taxes of its payment booked before it (e.g. an old fee given back just before the
    dividend is booked again), taken out of what waits on its own."""
    row = dividend.row
    parts = [
        item
        for item in waiting.get(row.currency, [])
        if item.row.value_date == row.value_date
        and (item.kind is ImportKind.FEE or (item.kind in (ImportKind.TAX_REFUND, ImportKind.TAX_CHARGED) and item.row.isin == row.isin))
    ]
    for part in parts:
        if part.kind is ImportKind.FEE:
            dividend.fee -= part.amount
        else:
            dividend.tax -= part.amount
    waiting[row.currency] = [item for item in waiting.get(row.currency, []) if all(item is not part for part in parts)]
    return dividend


def _waiting_dividend(waiting: dict[str, list[_OpenCash]], row: _AccountRow) -> _OpenCash | None:
    """The waiting dividend a row belongs to: same currency and value date, and the same security when the row names
    one (DEGIRO's fee rows do not)."""
    candidates = [
        item
        for item in waiting.get(row.currency, [])
        if item.kind is ImportKind.DIVIDEND and item.row.value_date == row.value_date and (not row.isin or item.row.isin == row.isin)
    ]
    return candidates[-1] if candidates else None


def _converted(conversion: list[_AccountRow], waiting: dict[str, list[_OpenCash]]) -> list[ImportRecord]:
    """What a conversion settles: the items waiting in its other currency, for the euros it moved. (Its rows are
    labelled "Débit" and "Crédit" inconsistently; the currencies and signs are what count.)"""
    euros = [row for row in conversion if row.currency == ACCOUNT_CURRENCY]
    other = [row for row in conversion if row.currency != ACCOUNT_CURRENCY]
    if len(euros) != 1 or len(other) != 1:
        return [_unknown(row) for row in conversion]
    euro, foreign = euros[0], other[0]
    items = _settled_by(waiting.get(foreign.currency, []), -foreign.amount)
    if not items:  # nothing waiting: a leftover balance (e.g. a cent of rounding from a trade), converted as it is
        description = f"Leftover {foreign.currency} balance converted"
        return [ImportRecord(ImportKind.INCOME, euro.timestamp, euro.amount, ACCOUNT_CURRENCY, description)]
    waiting[foreign.currency] = waiting[foreign.currency][len(items) :]  # the oldest ones were settled
    return _credited(items, euro.amount, ACCOUNT_CURRENCY)


def _settled_by(items: list[_OpenCash], converted: Decimal) -> list[_OpenCash]:
    """The waiting items a conversion of `converted` (positive when it takes money out of that currency) settles: the
    oldest ones adding up to exactly that, or else all of them."""
    total = Decimal(0)
    for count, item in enumerate(items, start=1):
        total += item.net
        if total == converted:
            return items[:count]
    return list(items)


def _credited(items: list[_OpenCash], amount: Decimal, currency: str) -> list[ImportRecord]:
    """The items as records sharing `amount` (signed, in `currency`) in proportion to their own amounts."""
    if not items:
        return []
    total = sum((item.net for item in items), Decimal(0))
    shares = [to_cents(amount * item.net / total) for item in items[:-1]]
    shares.append(amount - sum(shares, Decimal(0)))  # the last takes what rounding left
    return [_cash_record(item, abs(share), currency) for item, share in zip(items, shares, strict=True)]


def _cash_record(item: _OpenCash, amount: Decimal, currency: str) -> ImportRecord:
    if item.kind is ImportKind.FEE and item.net > 0:
        return ImportRecord(ImportKind.INCOME, item.row.timestamp, amount, currency, f"{item.row.description} (given back)")
    if item.kind is ImportKind.FEE:
        return ImportRecord(ImportKind.FEE, item.row.timestamp, amount, currency, item.row.description)
    if item.kind is ImportKind.DIVIDEND and item.net < 0:  # reversed after it was converted
        return ImportRecord(ImportKind.DIVIDEND_REVERSED, item.row.timestamp, amount, currency, item.row.product, isin=item.row.isin)
    if item.kind is not ImportKind.DIVIDEND:
        return ImportRecord(item.kind, item.row.timestamp, amount, currency, item.row.product, isin=item.row.isin or None)
    return ImportRecord(
        kind=ImportKind.DIVIDEND,
        timestamp=item.row.timestamp,
        amount=amount,
        currency=currency,
        description=item.row.product,
        isin=item.row.isin,
        dividend_currency=item.row.currency,
        gross=item.amount,
        tax=item.tax,
        dividend_fee=item.fee,
    )


def _simple_record(row: _AccountRow) -> ImportRecord:
    """A row that is an operation of its own, or, with an order ID, part of a trade."""
    if row.order_id:  # every cash line of a trade carries its order ID: the payment, its fees, its currency conversion
        kind = ImportKind.TRADE_SETTLEMENT
    else:
        kind = next((kind for pattern, kind in ACCOUNT_PATTERNS if pattern.search(row.description)), ImportKind.UNKNOWN)
    amount = row.amount if kind is ImportKind.INCOME else abs(row.amount)
    return ImportRecord(kind, row.timestamp, amount, row.currency, row.description)


def _unknown(row: _AccountRow) -> ImportRecord:
    return ImportRecord(ImportKind.UNKNOWN, row.timestamp, abs(row.amount), row.currency, row.description)


def _timestamp(date: str, time: str) -> datetime:
    return datetime.strptime(f"{date} {time}", DATE_TIME_FORMAT).replace(tzinfo=TIMEZONE)


def _number(text: str) -> Decimal:
    """A French-formatted number: decimal comma, spaces (of any width) between thousands. An empty cell is zero."""
    cleaned = re.sub(r"\s", "", text).replace(",", ".")
    return Decimal(cleaned) if cleaned else Decimal(0)
