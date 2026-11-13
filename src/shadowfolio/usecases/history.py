"""History use cases: recording, correcting and removing what happened in a wallet (cash movements and past trades).

Each returns the updated wallet, or None if the wallet does not exist; an unknown operation raises OperationNotFoundError.
"""

from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.errors import FutureTimestampError, FxRateUnavailableError, MissingPriceCurrencyError, PriceUnavailableError
from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import PriceSource, Trade
from shadowfolio.domain.valuation import CENT
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.fx_rates import FxRates
from shadowfolio.ports.price_data import PriceData
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.sync import Sync


class History:
    def __init__(self, repo: WalletRepository, clock: Clock, prices: PriceData, fx_rates: FxRates, sync: Sync) -> None:
        self._repo = repo
        self._clock = clock
        self._prices = prices
        self._fx_rates = fx_rates
        self._sync = sync

    # Every recording method can instead replace an existing operation (`replacing=<its id>`), keeping its id.

    def deposit(self, wallet_id: UUID, amount: Decimal, timestamp: datetime | None = None, replacing: UUID | None = None) -> Wallet | None:
        """Add cash to a wallet, now or at a past timestamp."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.deposit(replacing or uuid4(), amount, self._at(timestamp), replacing)
        self._repo.update(updated)
        return updated

    def withdraw(self, wallet_id: UUID, amount: Decimal, timestamp: datetime | None = None, replacing: UUID | None = None) -> Wallet | None:
        """Take cash out of a wallet, now or at a past timestamp."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.withdraw(replacing or uuid4(), amount, self._at(timestamp), replacing)
        self._repo.update(updated)
        return updated

    def record_buy(
        self,
        wallet_id: UUID,
        symbol: str,
        quantity: Decimal,
        timestamp: datetime,
        price: Decimal | None = None,
        price_currency: Currency | None = None,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Wallet | None:
        """Record a buy that already happened: with the price the broker reported, or without one to price it from market data."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        at = self._at(timestamp)
        # Splits first, so the trade is checked against the shares really held then. Saved with the trade.
        wallet = self._sync.ensure_checked(wallet, symbol, at.date())
        trade, settled_amount = self._priced(wallet, symbol, quantity, at, price, price_currency, settled_amount)
        updated = wallet.buy(replacing or uuid4(), trade, at, settled_amount, fees, replacing)
        self._repo.update(updated)
        return updated

    def record_sell(
        self,
        wallet_id: UUID,
        symbol: str,
        quantity: Decimal,
        timestamp: datetime,
        price: Decimal | None = None,
        price_currency: Currency | None = None,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Wallet | None:
        """Record a sell that already happened: with the price the broker reported, or without one to price it from market data."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        at = self._at(timestamp)
        # Splits first, so the trade is checked against the shares really held then. Saved with the trade.
        wallet = self._sync.ensure_checked(wallet, symbol, at.date())
        trade, settled_amount = self._priced(wallet, symbol, quantity, at, price, price_currency, settled_amount)
        updated = wallet.sell(replacing or uuid4(), trade, at, settled_amount, fees, replacing)
        self._repo.update(updated)
        return updated

    def delete_operation(self, wallet_id: UUID, operation_id: UUID) -> Wallet | None:
        """Remove an operation; the rest of the history must still hold together."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.remove_operation(operation_id)
        self._repo.update(updated)
        return updated

    def _priced(
        self,
        wallet: Wallet,
        symbol: str,
        quantity: Decimal,
        at: datetime,
        price: Decimal | None,
        price_currency: Currency | None,
        settled_amount: Decimal | None,
    ) -> tuple[Trade, Decimal | None]:
        """The trade and its settled amount. Without a price, both come from market data at `at` (the first traded
        price at or after it, and that day's exchange rate), and the trade is marked as priced with hindsight."""
        if price is not None:
            if price_currency is None:
                raise MissingPriceCurrencyError("a price needs its currency")
            return Trade(symbol, quantity, price, price_currency), settled_amount
        quote = self._prices.price_at(symbol, at)
        if quote is None:
            raise PriceUnavailableError(f"no market price for {symbol} at or after {at.isoformat()}")
        rate = Decimal(1)
        if quote.currency is not wallet.currency:
            fx = self._fx_rates.rate_on(quote.currency, wallet.currency, at.date())
            if fx is None:
                raise FxRateUnavailableError(f"no {quote.currency}→{wallet.currency} rate for {at.date().isoformat()}")
            rate = fx.rate
        settled = (quantity * quote.price * rate).quantize(CENT, rounding=ROUND_HALF_EVEN)
        return Trade(symbol, quantity, quote.price, quote.currency, PriceSource.MARKET), settled

    def _at(self, timestamp: datetime | None) -> datetime:
        """The operation's time: now if not given; a given time must not be in the future."""
        now = self._clock.now()
        if timestamp is None:
            return now
        if timestamp > now:
            raise FutureTimestampError("operations cannot be dated in the future")
        return timestamp
