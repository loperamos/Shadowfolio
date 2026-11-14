"""Reading DEGIRO's CSV exports in French (Transactions and Account) into import records.

A recipe rather than a model: columns are read by position and Account rows are recognised by their description.
DEGIRO France writes times in Paris time and numbers with a decimal comma.

A dividend in another currency takes several Account rows: the dividend, the tax withheld, DEGIRO's fee, and later a
currency conversion (a debit in that currency and a credit in euros) that brings that currency's balance back to
zero. They are read together as one dividend credited with the conversion's euros; dividends converted together
share those euros in proportion to what each left after tax and fee.
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
        (r"^(Variation Fonds Monétaires|Conversion Fonds Monétaires finalisée)", ImportKind.INTERNAL_TRANSFER),
        (r"^Frais de connexion aux places boursières", ImportKind.FEE),
        (r"^Ajustement fractionnement:", ImportKind.SPLIT),
        (r"^Spin-off:", ImportKind.CORPORATE_ACTION_NOTICE),
        (r"^(Flatex Interest|Flatex Interest Income|Compensation Fonds Monétaires DEGIRO)$", ImportKind.INCOME),
    ]
]


# Account rows announcing a corporate action, and what the Transactions rows of that security on that day are.
ACTION_PATTERNS: list[tuple[re.Pattern[str], ImportKind]] = [(re.compile(r"^Spin-off:"), ImportKind.SPIN_OFF)]


class _Part(Enum):
    """The Account rows that make up a dividend."""

    DIVIDEND = auto()
    TAX = auto()
    FEE = auto()
    CONVERSION = auto()


DIVIDEND_PATTERNS: list[tuple[re.Pattern[str], _Part]] = [
    (re.compile(pattern), part)
    for pattern, part in [
        (r"^Dividende$", _Part.DIVIDEND),
        (r"^Impôts sur dividende$", _Part.TAX),
        (r"^Frais d’opération sur titres$", _Part.FEE),
        (r"^Op[ée]ration de change - (Débit|Crédit)$", _Part.CONVERSION),
    ]
]


@dataclass(frozen=True)
class _AccountRow:
    timestamp: datetime
    product: str
    isin: str
    description: str
    currency: str
    amount: Decimal  # signed: negative when money leaves
    order_id: str


@dataclass
class _OpenDividend:
    """A dividend whose tax and fee may still follow, waiting for the conversion that credits it in euros."""

    row: _AccountRow
    tax: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)

    @property
    def net(self) -> Decimal:
        return self.row.amount - self.tax - self.fee


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


def _announced_actions(account_rows: list[list[str]]) -> dict[tuple[str, str], ImportKind]:
    """The corporate actions the Account export announces, by day and ISIN."""
    actions = {}
    for cells in account_rows:
        date, isin, description, order_id = cells[0], cells[4], cells[5], cells[11]
        kind = next((kind for pattern, kind in ACTION_PATTERNS if pattern.search(description)), None)
        if kind is not None and not order_id:
            actions[(date, isin)] = kind
    return actions


def _transaction_records(rows: list[list[str]], actions: dict[tuple[str, str], ImportKind]) -> list[ImportRecord]:
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
        kind = ImportKind.SPLIT if _is_split(group) else actions.get((group[0][0], group[0][3]))
        for index in indexes:
            if kind is not None:
                records[index] = replace(records[index], kind=kind)
    return records


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
    open_dividends: dict[str, list[_OpenDividend]] = {}
    for _, same_minute in groupby(account_rows, key=lambda row: row.timestamp):
        minute = list(same_minute)
        conversion = [row for row in minute if not row.order_id and _part(row) is _Part.CONVERSION]
        for row in minute:
            part = None if row.order_id else _part(row)
            if part is _Part.DIVIDEND:
                open_dividends.setdefault(row.currency, []).append(_OpenDividend(row))
            elif part is _Part.TAX and (dividend := _last(open_dividends, row.currency, row.isin)):
                dividend.tax += abs(row.amount)
            elif part is _Part.FEE and (dividend := _last(open_dividends, row.currency)):
                dividend.fee += abs(row.amount)
            elif part is _Part.CONVERSION:
                continue  # read as a pair below
            elif part is None:
                records.append(_simple_record(row))
            else:
                records.append(_unknown(row))
        if conversion:
            records += _converted(conversion, open_dividends)
    records += [_unknown(dividend.row) for dividends in open_dividends.values() for dividend in dividends]
    return records


def _account_row(cells: list[str]) -> _AccountRow:
    date, time, _value_date, product, isin, description, _fx, currency, amount = cells[:9]
    return _AccountRow(_timestamp(date, time), product, isin, description, currency, _number(amount), cells[11])


def _part(row: _AccountRow) -> _Part | None:
    return next((part for pattern, part in DIVIDEND_PATTERNS if pattern.search(row.description)), None)


def _last(open_dividends: dict[str, list[_OpenDividend]], currency: str, isin: str | None = None) -> _OpenDividend | None:
    """The latest open dividend in this currency (and of this security, if given)."""
    candidates = [d for d in open_dividends.get(currency, []) if isin is None or d.row.isin == isin]
    return candidates[-1] if candidates else None


def _converted(conversion: list[_AccountRow], open_dividends: dict[str, list[_OpenDividend]]) -> list[ImportRecord]:
    """The dividends a conversion credits: its debit is in their currency, its credit is what they bring in euros."""
    debits = [row for row in conversion if row.amount < 0]
    credits = [row for row in conversion if row.amount > 0]
    dividends = open_dividends.pop(debits[0].currency, []) if len(debits) == len(credits) == 1 else []
    if not dividends:
        return [_unknown(row) for row in conversion]
    credit = credits[0]
    total = sum((d.net for d in dividends), Decimal(0))
    shares = [to_cents(credit.amount * d.net / total) for d in dividends[:-1]]
    shares.append(credit.amount - sum(shares, Decimal(0)))  # the last takes what rounding left
    return [
        ImportRecord(
            kind=ImportKind.DIVIDEND,
            timestamp=d.row.timestamp,
            amount=share,
            currency=credit.currency,
            description=d.row.product,
            isin=d.row.isin,
            dividend_currency=d.row.currency,
            gross=d.row.amount,
            tax=d.tax,
            dividend_fee=d.fee,
        )
        for d, share in zip(dividends, shares, strict=True)
    ]


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
