"""Valuation use cases: what a wallet is worth at market prices, in its own currency."""

from uuid import UUID

from shadowfolio.domain.errors import FxRateUnavailableError, PriceUnavailableError
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.valuation import Quote, WalletValuation, value_wallet
from shadowfolio.ports.fx_rates import FxRates
from shadowfolio.ports.price_data import PriceData
from shadowfolio.ports.wallet_repository import WalletRepository


class Valuation:
    def __init__(self, repo: WalletRepository, prices: PriceData, fx_rates: FxRates) -> None:
        self._repo = repo
        self._prices = prices
        self._fx_rates = fx_rates

    def current(self, wallet_id: UUID) -> WalletValuation | None:
        """The wallet valued at the latest prices and exchange rates. Returns None if the wallet does not exist.

        Fails if any held symbol has no price, or any needed currency has no rate, rather than returning a partial value.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        quotes: dict[str, Quote] = {}
        for symbol in wallet.holdings:
            quote = self._prices.latest_price(symbol)
            if quote is None:
                raise PriceUnavailableError(f"no price for {symbol}")
            quotes[symbol] = quote
        rates: dict[Currency, FxRate] = {}
        for currency in {q.currency for q in quotes.values()} - {wallet.currency}:
            rate = self._fx_rates.latest_rate(currency, wallet.currency)
            if rate is None:
                raise FxRateUnavailableError(f"no {currency}→{wallet.currency} rate")
            rates[currency] = rate
        return value_wallet(wallet, quotes, rates)
