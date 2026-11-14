"""Import use cases: turning records read from a broker statement into a wallet's operations."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from shadowfolio.domain.imports import ImportKind, ImportRecord
from shadowfolio.domain.money import Currency
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

    def apply(self, wallet_id: UUID, records: list[ImportRecord], tickers: Mapping[str, str]) -> ImportReport:
        """Record the records' operations in the wallet, in the order given, and report the records left out.

        `tickers` gives each security's ticker by ISIN, as statements often identify securities by ISIN only.
        """
        report = ImportReport()
        for record in records:
            match record.kind:
                case ImportKind.DEPOSIT:
                    self._history.deposit(wallet_id, record.amount, record.timestamp)
                case ImportKind.WITHDRAWAL:
                    self._history.withdraw(wallet_id, record.amount, record.timestamp)
                case ImportKind.BUY | ImportKind.SELL:
                    ticker = tickers.get(record.isin or "")
                    if ticker is None:
                        report.not_imported.append(NotImported(record, f"no ticker for {record.isin}"))
                        continue
                    self._record_trade(wallet_id, record, ticker)
                case ImportKind.FEE:
                    self._history.record_fee(wallet_id, record.timestamp, record.amount, record.description)
                case ImportKind.INCOME if record.amount != 0:
                    self._history.record_income(wallet_id, record.timestamp, record.amount, record.description)
                case ImportKind.INCOME:
                    pass  # e.g. a quarter's interest of 0.00: nothing to record
                case ImportKind.DIVIDEND:
                    ticker = tickers.get(record.isin or "")
                    if ticker is None:
                        report.not_imported.append(NotImported(record, f"no ticker for {record.isin}"))
                        continue
                    self._record_dividend(wallet_id, record, ticker)
                case ImportKind.INTERNAL_TRANSFER | ImportKind.TRADE_SETTLEMENT:
                    pass  # not money in or out of the wallet, or already counted with its trade
                case ImportKind.UNKNOWN:
                    report.not_imported.append(NotImported(record, "unknown row"))
        return report

    def _record_trade(self, wallet_id: UUID, record: ImportRecord, ticker: str) -> None:
        assert record.quantity is not None and record.price is not None and record.price_currency is not None
        record_trade = self._history.record_buy if record.kind is ImportKind.BUY else self._history.record_sell
        record_trade(
            wallet_id,
            ticker,
            record.quantity,
            record.timestamp,
            price=record.price,
            price_currency=Currency(record.price_currency),
            settled_amount=record.amount,
            fees=record.fees or Decimal(0),
        )

    def _record_dividend(self, wallet_id: UUID, record: ImportRecord, ticker: str) -> None:
        assert record.dividend_currency is not None and record.gross is not None
        self._history.record_dividend(
            wallet_id,
            record.timestamp,
            ticker,
            record.dividend_currency,
            record.gross,
            record.tax or Decimal(0),
            record.dividend_fee or Decimal(0),
            record.amount,
        )
