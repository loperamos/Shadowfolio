"""Changes to a wallet's history, made on a wallet value and returning the changed wallet, without saving it.

History loads, changes and saves one operation at a time; an import makes many changes to one wallet in memory and
saves them together. Recording a trade or received shares first applies the symbol's splits (Sync), and a trade
without a price is priced from market data.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.errors import FutureTimestampError, FxRateUnavailableError, MissingPriceCurrencyError, PriceUnavailableError
from shadowfolio.domain.money import Currency, to_cents
from shadowfolio.domain.operations import PriceSource, Trade
from shadowfolio.domain.orders import OrderSide
from shadowfolio.domain.valuation import Quote
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.fx_rates import FxRates, FxRatesUnavailableError
from shadowfolio.ports.market_data import MarketDataSource
from shadowfolio.ports.price_data import PriceDataUnavailableError
from shadowfolio.usecases.sync import Sync


class WalletChanges:
    def __init__(self, clock: Clock, market_data: MarketDataSource, fx_rates: FxRates, sync: Sync) -> None:
        """Prices come from each wallet's owner's market data."""
        self._clock = clock
        self._market_data = market_data
        self._fx_rates = fx_rates
        self._sync = sync

    # Every recording method can instead replace an existing operation (`replacing=<its id>`), keeping its id.

    def deposit(self, wallet: Wallet, amount: Decimal, timestamp: datetime | None = None, replacing: UUID | None = None) -> Wallet:
        return wallet.deposit(replacing or uuid4(), amount, self._at(timestamp), replacing)

    def withdraw(self, wallet: Wallet, amount: Decimal, timestamp: datetime | None = None, replacing: UUID | None = None) -> Wallet:
        return wallet.withdraw(replacing or uuid4(), amount, self._at(timestamp), replacing)

    def record_fee(self, wallet: Wallet, timestamp: datetime, amount: Decimal, description: str) -> Wallet:
        return wallet.pay_fee(uuid4(), self._at(timestamp), amount, description)

    def record_income(self, wallet: Wallet, timestamp: datetime, amount: Decimal, description: str) -> Wallet:
        return wallet.record_income(uuid4(), self._at(timestamp), amount, description)

    def record_shares_received(self, wallet: Wallet, timestamp: datetime, symbol: str, quantity: Decimal) -> Wallet:
        """Shares received without buying them (e.g. in a spin-off), at no cost."""
        at = self._at(timestamp)
        wallet = self._sync.ensure_checked(wallet, symbol, at.date())  # splits first, as for a trade
        return wallet.receive_shares(uuid4(), at, symbol, quantity, Decimal(0))

    def record_dividend(
        self,
        wallet: Wallet,
        timestamp: datetime,
        symbol: str,
        currency: str,
        gross: Decimal,
        tax: Decimal,
        fee: Decimal,
        amount: Decimal,
        payment_date: date,
    ) -> Wallet:
        """A dividend as a broker statement reports it: gross, tax and fee in its currency, `amount`, what was credited
        in the wallet's currency, and the payment it is for."""
        return wallet.record_dividend(uuid4(), self._at(timestamp), symbol, currency, gross, tax, fee, amount, payment_date)

    def record_buy(
        self,
        wallet: Wallet,
        symbol: str,
        quantity: Decimal,
        timestamp: datetime,
        price: Decimal | None = None,
        price_currency: Currency | None = None,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Wallet:
        """A buy that already happened: with the price the broker reported, or without one to price it from market data."""
        at = self._at(timestamp)
        # Splits first, so the trade is checked against the shares really held then.
        wallet = self._sync.ensure_checked(wallet, symbol, at.date())
        trade, settled_amount = self._priced(wallet, symbol, quantity, at, price, price_currency, settled_amount)
        return wallet.buy(replacing or uuid4(), trade, at, settled_amount, fees, replacing)

    def record_sell(
        self,
        wallet: Wallet,
        symbol: str,
        quantity: Decimal,
        timestamp: datetime,
        price: Decimal | None = None,
        price_currency: Currency | None = None,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Wallet:
        """A sell that already happened: with the price the broker reported, or without one to price it from market data."""
        at = self._at(timestamp)
        wallet = self._sync.ensure_checked(wallet, symbol, at.date())
        trade, settled_amount = self._priced(wallet, symbol, quantity, at, price, price_currency, settled_amount)
        return wallet.sell(replacing or uuid4(), trade, at, settled_amount, fees, replacing)

    def fill(self, wallet: Wallet, operation_id: UUID, side: OrderSide, symbol: str, quantity: Decimal, price: Quote) -> Wallet:
        """An order filled at `price` (its time is the fill's): a trade, with that day's exchange rate, marked as filled
        from an order (no hindsight). Splits first, as for any trade."""
        at = price.as_of
        wallet = self._sync.ensure_checked(wallet, symbol, at.date())
        trade = Trade(symbol, quantity, price.price, price.currency, PriceSource.ORDER)
        trading = wallet.buy if side is OrderSide.BUY else wallet.sell
        return trading(operation_id, trade, at, self._settled(wallet, trade, at))

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
        try:
            quote = self._market_data.for_user(wallet.owner_id).prices.price_at(symbol, at)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error
        if quote is None:
            raise PriceUnavailableError(f"no market price for {symbol} at or after {at.isoformat()}")
        trade = Trade(symbol, quantity, quote.price, quote.currency, PriceSource.MARKET)
        return trade, self._settled(wallet, trade, at)

    def _settled(self, wallet: Wallet, trade: Trade, at: datetime) -> Decimal:
        """What the trade comes to in the wallet's currency, at the exchange rate of its day."""
        rate = Decimal(1)
        if trade.price_currency is not wallet.currency:
            try:
                fx = self._fx_rates.rate_on(trade.price_currency, wallet.currency, at.date())
            except FxRatesUnavailableError as error:
                raise FxRateUnavailableError(
                    f"could not fetch the {trade.price_currency}→{wallet.currency} rate right now; try again later"
                ) from error
            if fx is None:
                raise FxRateUnavailableError(f"no {trade.price_currency}→{wallet.currency} rate for {at.date().isoformat()}")
            rate = fx.rate
        return to_cents(trade.quantity * trade.price * rate)

    def _at(self, timestamp: datetime | None) -> datetime:
        """The operation's time: now if not given; a given time must not be in the future."""
        now = self._clock.now()
        if timestamp is None:
            return now
        if timestamp > now:
            raise FutureTimestampError("operations cannot be dated in the future")
        return timestamp
