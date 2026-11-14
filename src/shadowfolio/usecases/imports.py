"""Import use cases: turning records read from a broker statement into a wallet's operations."""

from dataclasses import dataclass, field
from uuid import UUID

from shadowfolio.domain.imports import ImportKind, ImportRecord
from shadowfolio.usecases.history import History


@dataclass(frozen=True)
class NotImported:
    record: ImportRecord
    reason: str


@dataclass
class ImportReport:
    not_imported: list[NotImported] = field(default_factory=list)


class Imports:
    def __init__(self, history: History) -> None:
        self._history = history

    def apply(self, wallet_id: UUID, records: list[ImportRecord]) -> ImportReport:
        """Record the records' operations in the wallet, in the order given, and report the records left out."""
        report = ImportReport()
        for record in records:
            match record.kind:
                case ImportKind.DEPOSIT:
                    self._history.deposit(wallet_id, record.amount, record.timestamp)
                case ImportKind.WITHDRAWAL:
                    self._history.withdraw(wallet_id, record.amount, record.timestamp)
                case ImportKind.UNKNOWN:
                    report.not_imported.append(NotImported(record, "unknown row"))
        return report
