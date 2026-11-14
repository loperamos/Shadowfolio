"""Import use cases: turning records read from a broker statement into a wallet's operations."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
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


# Records about a security, which need its ticker.
SECURITY_KINDS = {ImportKind.BUY, ImportKind.SELL, ImportKind.DIVIDEND, ImportKind.SPIN_OFF}


class Imports:
    def __init__(self, history: History) -> None:
        self._history = history

    def apply(self, wallet_id: UUID, records: list[ImportRecord], tickers: Mapping[str, str]) -> ImportReport:
        """Record the records' operations in the wallet, in the order given, and report the records left out.

        `tickers` gives each security's ticker by ISIN, as statements often identify securities by ISIN only.
        """
        report = ImportReport()
        unchanged = _same_ticker_isin_changes(records, tickers)
        for record in records:
            if record.kind is ImportKind.ISIN_CHANGE:
                if record.timestamp not in unchanged:
                    report.not_imported.append(NotImported(record, "an ISIN change to another ticker is not imported yet"))
                continue
            problem = self._apply(wallet_id, record, tickers)
            if problem is not None:
                report.not_imported.append(NotImported(record, problem))
        return report

    def _apply(self, wallet_id: UUID, record: ImportRecord, tickers: Mapping[str, str]) -> str | None:
        """Record one record's operation, if it has one; the reason it is left out, if it is."""
        ticker = tickers.get(record.isin) if record.isin else None
        if record.kind in SECURITY_KINDS and ticker is None:
            return f"no ticker for {record.isin}"
        match record.kind:
            case ImportKind.DEPOSIT:
                self._history.deposit(wallet_id, record.amount, record.timestamp)
            case ImportKind.WITHDRAWAL:
                self._history.withdraw(wallet_id, record.amount, record.timestamp)
            case ImportKind.BUY | ImportKind.SELL if ticker:
                self._record_trade(wallet_id, record, ticker)
            case ImportKind.DIVIDEND if ticker:
                self._record_dividend(wallet_id, record, ticker)
            case ImportKind.SPIN_OFF if ticker and record.quantity:
                self._history.record_shares_received(wallet_id, record.timestamp, ticker, record.quantity)
            case ImportKind.FEE:
                self._history.record_fee(wallet_id, record.timestamp, record.amount, record.description)
            case ImportKind.INCOME if record.amount != 0:
                self._history.record_income(wallet_id, record.timestamp, record.amount, record.description)
            case ImportKind.UNKNOWN:
                return "unknown row"
            # Nothing to record: interest of 0.00, a spin-off giving no whole share, money moving inside the broker,
            # the cash lines of a trade, an action's notice, or a split (the wallet applies splits from market data).
        return None

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


def _same_ticker_isin_changes(records: list[ImportRecord], tickers: Mapping[str, str]) -> set[datetime]:
    """When the ISIN changes recorded at each moment keep the holding under one known ticker, so the wallet sees no
    change. (An ISIN change moves a holding between identifiers, one record for each side.)"""
    sides: dict[datetime, set[str | None]] = {}
    for record in records:
        if record.kind is ImportKind.ISIN_CHANGE:
            sides.setdefault(record.timestamp, set()).add(tickers.get(record.isin or ""))
    return {moment for moment, tickers_seen in sides.items() if len(tickers_seen) == 1 and None not in tickers_seen}
