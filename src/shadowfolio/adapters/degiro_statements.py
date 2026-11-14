"""Reading DEGIRO's CSV exports in French (Transactions and Account) into import records."""

from shadowfolio.domain.imports import ImportRecord


class DegiroStatementReader:
    def read(self, transactions: str, account: str) -> list[ImportRecord]:
        """The records in the two exports, each given as its full text (header first)."""
        return []
