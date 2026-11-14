"""Reading DEGIRO's CSV exports in French (Transactions and Account) into import records.

A recipe rather than a model: columns are read by position and Account rows are recognised by their description.
DEGIRO France writes times in Paris time and numbers with a decimal comma.
"""

import csv
import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from shadowfolio.domain.imports import ImportKind, ImportRecord

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
    ]
]


class DegiroStatementReader:
    def read(self, transactions: str, account: str) -> list[ImportRecord]:
        """The records in the two exports, each given as its full text (header first), oldest first."""
        records = [*(_trade(cells) for cells in _rows(transactions)), *(_account_record(cells) for cells in _rows(account))]
        return sorted(records, key=lambda record: record.timestamp)


def _rows(text: str) -> list[list[str]]:
    """The cells of each row after the header."""
    return [cells for cells in csv.reader(text.splitlines()[1:]) if cells]


def _trade(cells: list[str]) -> ImportRecord:
    """A Transactions row: an execution, identified by its order ID."""
    date, time, product, isin, _exchange, _venue, quantity, price, price_currency = cells[:9]
    amount, autofx_fee, brokerage_fee, order_id = cells[11], cells[13], cells[14], cells[16]
    shares = _number(quantity)
    return ImportRecord(
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


def _account_record(cells: list[str]) -> ImportRecord:
    date, time, _value_date, _product, _isin, description, _fx, currency, amount = cells[:9]
    order_id = cells[11]
    if order_id:  # every cash line of a trade carries its order ID: the payment, its fees, its currency conversion
        kind = ImportKind.TRADE_SETTLEMENT
    else:
        kind = next((kind for pattern, kind in ACCOUNT_PATTERNS if pattern.search(description)), ImportKind.UNKNOWN)
    return ImportRecord(kind, _timestamp(date, time), abs(_number(amount)), currency, description)


def _timestamp(date: str, time: str) -> datetime:
    return datetime.strptime(f"{date} {time}", DATE_TIME_FORMAT).replace(tzinfo=TIMEZONE)


def _number(text: str) -> Decimal:
    """A French-formatted number: decimal comma, spaces (of any width) between thousands. An empty cell is zero."""
    cleaned = re.sub(r"\s", "", text).replace(",", ".")
    return Decimal(cleaned) if cleaned else Decimal(0)
