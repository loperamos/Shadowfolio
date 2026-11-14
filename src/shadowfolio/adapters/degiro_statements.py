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

# Account rows by description; the first pattern that matches wins.
ACCOUNT_PATTERNS: list[tuple[re.Pattern[str], ImportKind]] = [
    (re.compile(pattern), kind)
    for pattern, kind in [
        (r"^(Dépôt flatex|Versement de fonds)$", ImportKind.DEPOSIT),
        (r"^(Retrait flatex|Retrait instantané SEPA)$", ImportKind.WITHDRAWAL),
    ]
]


class DegiroStatementReader:
    def read(self, transactions: str, account: str) -> list[ImportRecord]:
        """The records in the two exports, each given as its full text (header first), oldest first."""
        return sorted((_account_record(cells) for cells in _rows(account)), key=lambda record: record.timestamp)


def _rows(text: str) -> list[list[str]]:
    """The cells of each row after the header."""
    return [cells for cells in csv.reader(text.splitlines()[1:]) if cells]


def _account_record(cells: list[str]) -> ImportRecord:
    date, time, _value_date, _product, _isin, description, _fx, currency, amount = cells[:9]
    kind = next((kind for pattern, kind in ACCOUNT_PATTERNS if pattern.search(description)), ImportKind.UNKNOWN)
    return ImportRecord(kind, _timestamp(date, time), abs(_number(amount)), currency, description)


def _timestamp(date: str, time: str) -> datetime:
    return datetime.strptime(f"{date} {time}", DATE_TIME_FORMAT).replace(tzinfo=TIMEZONE)


def _number(text: str) -> Decimal:
    """A French-formatted number: decimal comma, spaces between thousands."""
    return Decimal(re.sub(r"[\s ]", "", text).replace(",", "."))
