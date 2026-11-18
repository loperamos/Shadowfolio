"""Wallet use cases: creating, changing settings (name, withholding tax, rules), copying, deleting and reading wallets."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.money import Currency
from shadowfolio.domain.rules import Rules
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.users import Users

# Who owned the wallets made before sign-in existed: no user (see Wallets.hand_over).
UNOWNED = "local"


class Wallets:
    def __init__(self, repo: WalletRepository, clock: Clock, users: Users) -> None:
        self._repo = repo
        self._clock = clock
        self._users = users

    def create(self, owner_id: str, name: str, currency: Currency, cash: Decimal) -> Wallet:
        """Create a wallet, if the owner's plan allows another. Non-zero starting cash is recorded as its first deposit."""
        self._check_room(owner_id)
        wallet = Wallet(id=uuid4(), owner_id=owner_id, name=name, currency=currency)
        if cash != 0:
            wallet = wallet.deposit(uuid4(), cash, self._clock.now())
        self._repo.add(wallet)
        return wallet

    def update(self, wallet_id: UUID, name: str | None = None, withholding_rate: Decimal | None = None) -> Wallet | None:
        """Change the given settings, leaving the others as they are. Returns None if the wallet does not exist.

        A new withholding rate works out every dividend again; it is refused if the lower cash would not cover the
        withdrawals and buys that followed.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet
        if name is not None:
            updated = updated.rename(name)
        if withholding_rate is not None:
            updated = updated.set_withholding_rate(withholding_rate)
        self._repo.update(updated)
        return updated

    def hand_over(self, from_owner: str, to_owner: str) -> int:
        """Give every wallet of `from_owner` to `to_owner` (e.g. the ones made before sign-in to their user). Returns
        how many; none once done."""
        found = self._repo.list_by_owner(from_owner)
        for wallet in found:
            self._repo.update(wallet.handed_to(to_owner))
        return len(found)

    def set_rules(self, wallet_id: UUID, rules: Rules) -> Wallet | None:
        """Replace the wallet's rules for orders, its allowed symbols as market data writes them, once each. Returns
        None if the wallet does not exist."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        symbols = tuple(dict.fromkeys(symbol.strip().upper() for symbol in rules.allowed_symbols))
        updated = wallet.set_rules(replace(rules, allowed_symbols=symbols))
        self._repo.update(updated)
        return updated

    def copy(self, wallet_id: UUID, name: str, before: datetime | None = None) -> Wallet | None:
        """A new wallet with the same currency and history under another name, or its history up to `before`
        (see Wallet.copy), if the owner's plan allows another. Returns None if the wallet does not exist."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        self._check_room(wallet.owner_id)
        copy = wallet.copy(uuid4(), name, uuid4, before)
        self._repo.add(copy)
        return copy

    def delete(self, wallet_id: UUID) -> bool:
        """Delete the wallet and its history. Returns False if it does not exist."""
        if self._repo.get(wallet_id) is None:
            return False
        self._repo.delete(wallet_id)
        return True

    def get(self, wallet_id: UUID) -> Wallet | None:
        return self._repo.get(wallet_id)

    def list(self, owner_id: str) -> list[Wallet]:
        return self._repo.list_by_owner(owner_id)

    def _check_room(self, owner_id: str) -> None:
        """Raise PlanLimitError if the owner's plan does not allow another wallet."""
        self._users.user(owner_id).check_new_wallet(len(self._repo.list_by_owner(owner_id)))
