"""Import use cases: turning records read from a broker statement into a wallet's operations.

An import is all or nothing: every record is tried, every problem reported, and the wallet is saved only if every
record went in.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from shadowfolio.domain.errors import DomainError
from shadowfolio.domain.imports import ImportKind, ImportRecord
from shadowfolio.domain.money import Currency
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.history import History


@dataclass(frozen=True)
class NotImported:
    record: ImportRecord
    reason: str


@dataclass
class ImportReport:
    not_imported: list[NotImported] = field(default_factory=list)

    @property
    def imported(self) -> bool:
        """Whether the records were saved: only when every one of them went in."""
        return not self.not_imported


# Records about a security, which need its ticker.
SECURITY_KINDS = {
    ImportKind.BUY,
    ImportKind.SELL,
    ImportKind.IPO_SUBSCRIPTION,
    ImportKind.DIVIDEND,
    ImportKind.DIVIDEND_REVERSED,
    ImportKind.SPIN_OFF,
    ImportKind.CASH_IN_LIEU,
    ImportKind.TAX_REFUND,
    ImportKind.TAX_CHARGED,
}


class Imports:
    def __init__(self, history: History, repo: WalletRepository) -> None:
        self._history = history
        self._repo = repo

    def apply(self, wallet_id: UUID, records: list[ImportRecord], tickers: Mapping[str, str]) -> ImportReport:
        """Record the records' operations in the wallet, in the order given, if every one goes in; report the records
        left out, and why.

        `tickers` gives each security's ticker by ISIN, as statements often identify securities by ISIN only.
        """
        before = self._repo.get(wallet_id)
        report = ImportReport()
        unchanged = _same_ticker_isin_changes(records, tickers)
        for record in records:
            if record.kind is ImportKind.ISIN_CHANGE:
                if record.timestamp not in unchanged:
                    report.not_imported.append(NotImported(record, "an ISIN change to another ticker is not imported yet"))
                continue
            try:
                problem = self._apply(wallet_id, record, tickers)
            except DomainError as error:  # the wallet refuses it, or a provider it needs cannot answer
                problem = str(error)
            if problem is not None:
                report.not_imported.append(NotImported(record, problem))
        if not report.imported and before is not None:
            self._repo.update(before)  # each record was saved as it went in: put the wallet back as it was
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
            case ImportKind.BUY | ImportKind.SELL | ImportKind.IPO_SUBSCRIPTION if ticker:
                self._record_trade(wallet_id, record, ticker)
            case ImportKind.DIVIDEND if ticker:
                self._record_dividend(wallet_id, record, ticker)
            case ImportKind.SPIN_OFF if ticker and record.quantity:
                self._history.record_shares_received(wallet_id, record.timestamp, ticker, record.quantity)
            case ImportKind.CASH_IN_LIEU if ticker and record.amount:
                description = f"Cash for a fraction of a share of {ticker}"
                self._history.record_income(wallet_id, record.timestamp, record.amount, description)
            case ImportKind.TAX_REFUND if ticker and record.amount:
                self._history.record_income(wallet_id, record.timestamp, record.amount, f"Dividend tax refunded on {ticker}")
            case ImportKind.DIVIDEND_REVERSED if ticker and record.amount:
                self._history.record_income(wallet_id, record.timestamp, -record.amount, f"Dividend of {ticker} reversed")
            case ImportKind.TAX_CHARGED if ticker and record.amount:
                self._history.record_fee(wallet_id, record.timestamp, record.amount, f"Dividend tax charged later on {ticker}")
            case ImportKind.FEE if record.amount:
                self._history.record_fee(wallet_id, record.timestamp, record.amount, record.description)
            case ImportKind.INCOME if record.amount != 0:
                self._history.record_income(wallet_id, record.timestamp, record.amount, record.description)
            case ImportKind.UNKNOWN:
                return "unknown row"
            # Nothing to record: an amount of 0.00 (interest, a refund's share), a spin-off giving no whole share, money
            # moving inside the broker, the cash lines of a trade, an action's notice, or a split (the wallet applies
            # splits from market data).
        return None

    def _record_trade(self, wallet_id: UUID, record: ImportRecord, ticker: str) -> None:
        assert record.quantity is not None and record.price is not None and record.price_currency is not None
        record_trade = self._history.record_sell if record.kind is ImportKind.SELL else self._history.record_buy
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
