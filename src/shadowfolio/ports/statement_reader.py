"""Reading a broker's statement exports into import records."""

from abc import ABC, abstractmethod

from shadowfolio.domain.imports import ImportRecord


class UnsupportedStatementError(Exception):
    """A file is not the export the reader expects."""


class StatementReader(ABC):
    @abstractmethod
    def read(self, transactions: str, account: str) -> list[ImportRecord]:
        """The records in a broker's two exports (its trades and its cash movements), each given as its full text,
        oldest first.

        Raises UnsupportedStatementError when a file is not the export expected.
        """
