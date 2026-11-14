"""Import records: what a broker statement says happened, before it becomes a wallet's operations."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class ImportKind(StrEnum):
    DEPOSIT = "deposit"  # money moved into the account from outside
    WITHDRAWAL = "withdrawal"  # money moved out of the account
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
