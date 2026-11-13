"""Valuation use cases: what a wallet is worth at market prices, in its own currency, now or at the end of a past day."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from shadowfolio.domain.errors import FutureTimestampError, FxRateUnavailableError, PriceUnavailableError
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.valuation import Quote, WalletValuation, value_wallet
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.fx_rates import FxRates, FxRatesUnavailableError
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError
from shadowfolio.ports.wallet_repository import WalletRepository


class Valuation:
    def __init__(self, repo: WalletRepository, clock: Clock, prices: PriceData, fx_rates: FxRates) -> None:
        self._repo = repo
        self._clock = clock
        self._prices = prices
        self._fx_rates = fx_rates

    def current(self, wallet_id: UUID) -> WalletValuation | None:
        """The wallet valued at the latest prices and exchange rates. Returns None if the wallet does not exist.

        Fails if any held symbol has no price, or any needed currency has no rate, rather than returning a partial value.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        return self._value(
            wallet,
            lambda symbol: self._prices.latest_price(symbol),
            lambda currency: self._fx_rates.latest_rate(currency, wallet.currency),
            "",
        )

    def on(self, wallet_id: UUID, day: date) -> WalletValuation | None:
        """The wallet as it was at the end of `day` (every operation dated that day, in UTC, included), valued at that
        day's closing prices and exchange rates, or the last ones before it (weekends, holidays). Returns None if the
        wallet does not exist. Fails the same way as `current`, and for a day after today.
        """
        if day > self._clock.now().date():
            raise FutureTimestampError("cannot value a wallet on a day that has not happened yet")
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        past = wallet.as_of(datetime.combine(day + timedelta(days=1), time(), tzinfo=UTC))
        return self._value(
            past,
            lambda symbol: self._prices.close_on(symbol, day),
            lambda currency: self._fx_rates.rate_on(currency, wallet.currency, day),
            f" on or before {day.isoformat()}",
        )

    def _value(
        self,
        wallet: Wallet,
        quote_of: Callable[[str], Quote | None],
        rate_of: Callable[[Currency], FxRate | None],
        when: str,  # added to messages, e.g. " on or before 2024-06-24"
    ) -> WalletValuation:
        quotes: dict[str, Quote] = {}
        for symbol in wallet.holdings:
            try:
                quote = quote_of(symbol)
            except PriceDataUnavailableError as error:
                raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error
            if quote is None:
                raise PriceUnavailableError(f"no price for {symbol}{when}")
            quotes[symbol] = quote
        rates: dict[Currency, FxRate] = {}
        for currency in {q.currency for q in quotes.values()} - {wallet.currency}:
            try:
                rate = rate_of(currency)
            except FxRatesUnavailableError as error:
                raise FxRateUnavailableError(f"could not fetch the {currency}→{wallet.currency} rate right now; try again later") from error
            if rate is None:
                raise FxRateUnavailableError(f"no {currency}→{wallet.currency} rate{when}")
            rates[currency] = rate
        return value_wallet(wallet, quotes, rates)
