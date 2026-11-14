"""Import use cases: turning records read from a broker statement into a wallet's operations.

An import is all or nothing: every record is applied to the wallet in memory, every problem is reported, and the
wallet is saved, once, only if every record went in.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from shadowfolio.domain.errors import DomainError
from shadowfolio.domain.imports import ImportKind, ImportRecord
from shadowfolio.domain.money import Currency
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.wallet_changes import WalletChanges


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


SUPPORTED_CURRENCIES = {currency.value for currency in Currency}
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
    def __init__(self, repo: WalletRepository, changes: WalletChanges) -> None:
        self._repo = repo
        self._changes = changes

    def apply(self, wallet_id: UUID, records: list[ImportRecord], tickers: Mapping[str, str]) -> ImportReport | None:
        """Record the records' operations in the wallet, in the order given, if every one goes in; report the records
        left out, and why. Returns None if the wallet does not exist.

        `tickers` gives each security's ticker by ISIN, as statements often identify securities by ISIN only.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        report = ImportReport()
        unchanged = _same_ticker_isin_changes(records, tickers)
        for record in records:
            if record.kind is ImportKind.ISIN_CHANGE:
                if _isin_change_key(record) not in unchanged:
                    report.not_imported.append(NotImported(record, "an ISIN change to another ticker is not imported yet"))
                continue
            try:
                wallet, problem = self._apply(wallet, record, tickers)
            except DomainError as error:  # the wallet refuses it, or a provider it needs cannot answer
                problem = str(error)
            if problem is not None:
                report.not_imported.append(NotImported(record, problem))
        if report.imported:
            self._repo.update(wallet)
        return report

    def _apply(self, wallet: Wallet, record: ImportRecord, tickers: Mapping[str, str]) -> tuple[Wallet, str | None]:
        """The wallet with one record's operation, if it has one; and the reason it is left out, if it is."""
        changes, at, amount = self._changes, record.timestamp, record.amount
        ticker = tickers.get(record.isin) if record.isin else None
        if record.kind in SECURITY_KINDS and ticker is None:
            return wallet, f"no ticker for {record.isin}"
        match record.kind:
            case ImportKind.DEPOSIT:
                return changes.deposit(wallet, amount, at), None
            case ImportKind.WITHDRAWAL:
                return changes.withdraw(wallet, amount, at), None
            case ImportKind.BUY | ImportKind.SELL | ImportKind.IPO_SUBSCRIPTION if ticker:
                return self._trade(wallet, record, ticker)
            case ImportKind.DIVIDEND if ticker:
                assert record.dividend_currency is not None and record.gross is not None and record.payment_date is not None
                tax, fee = record.tax or Decimal(0), record.dividend_fee or Decimal(0)
                paid = record.payment_date
                return changes.record_dividend(wallet, at, ticker, record.dividend_currency, record.gross, tax, fee, amount, paid), None
            case ImportKind.SPIN_OFF if ticker and record.quantity:
                return changes.record_shares_received(wallet, at, ticker, record.quantity), None
            case ImportKind.CASH_IN_LIEU if ticker and amount:
                return changes.record_income(wallet, at, amount, f"Cash for a fraction of a share of {ticker}"), None
            case ImportKind.TAX_REFUND if ticker and amount:
                return changes.record_income(wallet, at, amount, f"Dividend tax refunded on {ticker}"), None
            case ImportKind.DIVIDEND_REVERSED if ticker and amount:
                return changes.record_income(wallet, at, -amount, f"Dividend of {ticker} reversed"), None
            case ImportKind.TAX_CHARGED if ticker and amount:
                return changes.record_fee(wallet, at, amount, f"Dividend tax charged later on {ticker}"), None
            case ImportKind.FEE if amount:
                return changes.record_fee(wallet, at, amount, record.description), None
            case ImportKind.INCOME if amount != 0:
                return changes.record_income(wallet, at, amount, record.description), None
            case ImportKind.UNKNOWN:
                return wallet, "unknown row"
        # Nothing to record: an amount of 0.00 (interest, a refund's share), a spin-off giving no whole share, money
        # moving inside the broker, the cash lines of a trade, an action's notice, or a split (the wallet applies
        # splits from market data).
        return wallet, None

    def _trade(self, wallet: Wallet, record: ImportRecord, ticker: str) -> tuple[Wallet, str | None]:
        assert record.quantity is not None and record.price is not None and record.price_currency is not None
        if record.price_currency not in SUPPORTED_CURRENCIES:
            return wallet, f"prices in {record.price_currency} are not supported"
        record_trade = self._changes.record_sell if record.kind is ImportKind.SELL else self._changes.record_buy
        trade = record_trade(
            wallet,
            ticker,
            record.quantity,
            record.timestamp,
            price=record.price,
            price_currency=Currency(record.price_currency),
            settled_amount=record.amount,
            fees=record.fees or Decimal(0),
        )
        return trade, None


def _same_ticker_isin_changes(records: list[ImportRecord], tickers: Mapping[str, str]) -> set[tuple[datetime, Decimal | None]]:
    """The ISIN changes that keep a holding under one known ticker, so the wallet sees no change. An ISIN change moves
    shares between identifiers, one record for each side: its two records share the moment and the number of shares."""
    sides: dict[tuple[datetime, Decimal | None], set[str | None]] = {}
    for record in records:
        if record.kind is ImportKind.ISIN_CHANGE:
            sides.setdefault(_isin_change_key(record), set()).add(tickers.get(record.isin or ""))
    return {key for key, tickers_seen in sides.items() if len(tickers_seen) == 1 and None not in tickers_seen}


def _isin_change_key(record: ImportRecord) -> tuple[datetime, Decimal | None]:
    return record.timestamp, record.quantity
