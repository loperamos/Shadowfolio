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
from shadowfolio.domain.imports import ImportKind, ImportRecord, TradeDetails
from shadowfolio.domain.money import Currency
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.security_lookup import SecurityLookup, SecurityLookupUnavailableError
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
LOOKUP_UNAVAILABLE = "could not look up tickers right now; try again later"
# Records that are only cash; one of 0.00 records nothing.
CASH_KINDS = {
    ImportKind.FEE,
    ImportKind.INCOME,
    ImportKind.CASH_IN_LIEU,
    ImportKind.TAX_REFUND,
    ImportKind.TAX_CHARGED,
    ImportKind.DIVIDEND_REVERSED,
}
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
    def __init__(self, repo: WalletRepository, changes: WalletChanges, lookup: SecurityLookup) -> None:
        self._repo = repo
        self._changes = changes
        self._lookup = lookup

    def apply(self, wallet_id: UUID, records: list[ImportRecord]) -> ImportReport | None:
        """Record the records' operations in the wallet, in the order given, if every one goes in; report the records
        left out, and why. Returns None if the wallet does not exist.

        Statements often identify securities by ISIN only: their tickers are looked up, with the venue each traded on.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        report = ImportReport()
        try:
            tickers = _with_exchanged_identifiers(records, self._lookup.tickers(_securities(records)))
        except SecurityLookupUnavailableError:
            problems = [NotImported(r, LOOKUP_UNAVAILABLE) for r in records if r.kind in SECURITY_KINDS]
            return ImportReport(problems)
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
        if _nothing_to_record(record):
            return wallet, None
        ticker = tickers.get(record.isin) if record.isin else None
        if record.kind in SECURITY_KINDS and ticker is None:
            return wallet, f"no ticker for {record.isin}"
        match record.kind:
            case ImportKind.DEPOSIT:
                return changes.deposit(wallet, amount, at), None
            case ImportKind.WITHDRAWAL:
                return changes.withdraw(wallet, amount, at), None
            case ImportKind.BUY | ImportKind.SELL | ImportKind.IPO_SUBSCRIPTION if ticker and record.trade:
                return self._trade(wallet, record, ticker, record.trade)
            case ImportKind.DIVIDEND if ticker and (d := record.dividend):
                return changes.record_dividend(wallet, at, ticker, d.currency, d.gross, d.tax, d.fee, amount, d.payment_date), None
            case ImportKind.SPIN_OFF if ticker and record.trade:
                return changes.record_shares_received(wallet, at, ticker, record.trade.quantity), None
            case ImportKind.CASH_IN_LIEU if ticker:
                return changes.record_income(wallet, at, amount, f"Cash for a fraction of a share of {ticker}"), None
            case ImportKind.TAX_REFUND if ticker:
                return changes.record_income(wallet, at, amount, f"Dividend tax refunded on {ticker}"), None
            case ImportKind.DIVIDEND_REVERSED if ticker:
                return changes.record_income(wallet, at, -amount, f"Dividend of {ticker} reversed"), None
            case ImportKind.TAX_CHARGED if ticker:
                return changes.record_fee(wallet, at, amount, f"Dividend tax charged later on {ticker}"), None
            case ImportKind.FEE:
                return changes.record_fee(wallet, at, amount, record.description), None
            case ImportKind.INCOME:
                return changes.record_income(wallet, at, amount, record.description), None
            case ImportKind.UNKNOWN:
                return wallet, "unknown row"
            case ImportKind.BUY | ImportKind.SELL | ImportKind.IPO_SUBSCRIPTION | ImportKind.DIVIDEND | ImportKind.SPIN_OFF:
                return wallet, "incomplete record"  # a reader bug: a trade without its details, or a dividend without its own
        # Nothing to record: money moving inside the broker, the cash lines of a trade, an action's notice, or a split
        # (the wallet applies splits from market data).
        return wallet, None

    def _trade(self, wallet: Wallet, record: ImportRecord, ticker: str, trade: TradeDetails) -> tuple[Wallet, str | None]:
        if trade.price_currency not in SUPPORTED_CURRENCIES:
            return wallet, f"prices in {trade.price_currency} are not supported"
        record_trade = self._changes.record_sell if record.kind is ImportKind.SELL else self._changes.record_buy
        changed = record_trade(
            wallet,
            ticker,
            trade.quantity,
            record.timestamp,
            price=trade.price,
            price_currency=Currency(trade.price_currency),
            settled_amount=record.amount,
            fees=trade.fees,
        )
        return changed, None


def _nothing_to_record(record: ImportRecord) -> bool:
    """Whether the record changes nothing in the wallet: a spin-off giving no whole share, or 0.00 of cash (a
    quarter's interest, a refund's share of a cent)."""
    if record.kind is ImportKind.SPIN_OFF:
        return record.trade is not None and not record.trade.quantity
    return record.kind in CASH_KINDS and record.amount == 0


def _securities(records: list[ImportRecord]) -> dict[str, str | None]:
    """Each security the records name, by ISIN, with the venue it was traded on when a record says."""
    securities: dict[str, str | None] = {}
    for record in records:
        if record.isin and (record.kind in SECURITY_KINDS or record.kind is ImportKind.ISIN_CHANGE):
            venue = record.trade.venue if record.trade else None
            securities[record.isin] = securities.get(record.isin) or venue
    return securities


def _with_exchanged_identifiers(records: list[ImportRecord], tickers: Mapping[str, str]) -> dict[str, str]:
    """`tickers`, plus the ticker of identifiers the lookup does not know (e.g. a broker's temporary line for a
    spin-off or an IPO subscription) taken from the one they are exchanged for in an ISIN change."""
    known = dict(tickers)
    sides: dict[tuple[datetime, Decimal | None], set[str]] = {}
    for record in records:
        if record.kind is ImportKind.ISIN_CHANGE and record.isin:
            sides.setdefault(_isin_change_key(record), set()).add(record.isin)
    for isins in sides.values():
        found = {known[isin] for isin in isins if isin in known}
        if len(found) == 1:
            known |= {isin: next(iter(found)) for isin in isins if isin not in known}
    return known


def _same_ticker_isin_changes(records: list[ImportRecord], tickers: Mapping[str, str]) -> set[tuple[datetime, Decimal | None]]:
    """The ISIN changes that keep a holding under one known ticker, so the wallet sees no change. An ISIN change moves
    shares between identifiers, one record for each side: its two records share the moment and the number of shares."""
    sides: dict[tuple[datetime, Decimal | None], set[str | None]] = {}
    for record in records:
        if record.kind is ImportKind.ISIN_CHANGE:
            sides.setdefault(_isin_change_key(record), set()).add(tickers.get(record.isin or ""))
    return {key for key, tickers_seen in sides.items() if len(tickers_seen) == 1 and None not in tickers_seen}


def _isin_change_key(record: ImportRecord) -> tuple[datetime, Decimal | None]:
    return record.timestamp, record.trade.quantity if record.trade else None
