"""Sync use cases: keeping wallets up to date with corporate actions (splits now; dividends later).

Each wallet records, per symbol, the period whose corporate actions have been applied (a high-water mark). Trades are
only accepted inside it; recording one outside first extends it. A daily sync extends every period to today.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

from shadowfolio.domain.corporate_actions import CheckedPeriod
from shadowfolio.domain.errors import CorporateActionsUnavailableNowError
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.corporate_actions import CorporateActions, CorporateActionsUnavailableError
from shadowfolio.ports.wallet_repository import WalletRepository

# Each daily sync looks this far back again, in case the provider published an action late. Applying is idempotent.
LATE_PUBLICATION_LOOKBACK = timedelta(days=7)


@dataclass(frozen=True)
class SyncSummary:
    wallets: int  # wallets checked
    splits_added: int


class Sync:
    def __init__(self, repo: WalletRepository, clock: Clock, corporate_actions: CorporateActions) -> None:
        self._repo = repo
        self._clock = clock
        self._corporate_actions = corporate_actions

    def ensure_checked(self, wallet: Wallet, symbol: str, day: date) -> Wallet:
        """The wallet with `symbol` checked from `day` (or earlier) to today; unchanged if it already was.

        Does not save it: the caller saves it together with the operation that needed it, so both land or neither.
        Fails, changing nothing, when the provider cannot be reached.
        """
        period = wallet.checked.get(symbol)
        if period is not None and period.covers(day):
            return wallet
        start = min(day, period.start) if period else day
        return self._check(wallet, symbol, start, start)

    def all_wallets(self) -> SyncSummary:
        """Extend every wallet's checked periods to today, adding the splits found. For the daily job."""
        wallets = splits_added = 0
        for wallet_id in self._repo.all_ids():
            wallet = self._repo.get(wallet_id)
            if wallet is None:
                continue
            wallets += 1
            updated = wallet
            for symbol, first_trade in sorted(_first_trade_dates(wallet).items()):
                period = wallet.checked.get(symbol)
                if period is None:  # traded before periods were recorded: check its whole history once
                    updated = self._check(updated, symbol, first_trade, first_trade)
                else:
                    fetch_from = max(period.start, period.end - LATE_PUBLICATION_LOOKBACK)
                    updated = self._check(updated, symbol, period.start, fetch_from)
            added = len(updated.operations) - len(wallet.operations)
            if updated != wallet:
                self._repo.update(updated)
            splits_added += added
        return SyncSummary(wallets=wallets, splits_added=splits_added)

    def _check(self, wallet: Wallet, symbol: str, start: date, fetch_from: date) -> Wallet:
        """Apply `symbol`'s splits from `fetch_from` to today, and mark it checked from `start` to today."""
        today = self._clock.now().date()
        try:
            events = self._corporate_actions.splits(symbol, fetch_from, today)
        except CorporateActionsUnavailableError as error:
            raise CorporateActionsUnavailableNowError(f"could not check splits of {symbol} right now; try again later") from error
        for event in events:
            wallet = wallet.apply_split(uuid4(), event, datetime.combine(event.ex_date, time(), tzinfo=UTC))
        return wallet.mark_checked(symbol, CheckedPeriod(start, today))


def _first_trade_dates(wallet: Wallet) -> dict[str, date]:
    """For each symbol the wallet ever traded, the date of its first trade."""
    first: dict[str, date] = {}
    for op in wallet.operations:  # oldest first
        change = op.holding_change
        if change is not None:
            first.setdefault(change[0], op.timestamp.date())
    return first
