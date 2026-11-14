"""Import use cases: turning records read from a broker statement into a wallet's operations."""

from uuid import UUID

from shadowfolio.domain.imports import ImportKind, ImportRecord
from shadowfolio.usecases.history import History


class Imports:
    def __init__(self, history: History) -> None:
        self._history = history

    def apply(self, wallet_id: UUID, records: list[ImportRecord]) -> None:
        """Record the records' operations in the wallet, in the order given."""
        for record in records:
            match record.kind:
                case ImportKind.DEPOSIT:
                    self._history.deposit(wallet_id, record.amount, record.timestamp)
                case ImportKind.WITHDRAWAL:
                    self._history.withdraw(wallet_id, record.amount, record.timestamp)
