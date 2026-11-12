"""Valuation use cases: what a wallet is worth at market prices."""

from uuid import UUID

from shadowfolio.domain.errors import PriceUnavailableError
from shadowfolio.domain.valuation import WalletValuation, value_wallet
from shadowfolio.ports.price_data import PriceData
from shadowfolio.ports.wallet_repository import WalletRepository


class Valuation:
    def __init__(self, repo: WalletRepository, prices: PriceData) -> None:
        self._repo = repo
        self._prices = prices

    def current(self, wallet_id: UUID) -> WalletValuation | None:
        """The wallet valued at the latest prices. Returns None if the wallet does not exist.

        Fails if any held symbol has no price, rather than returning a partial value.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        quotes = {}
        for symbol in wallet.holdings:
            quote = self._prices.latest_price(symbol)
            if quote is None:
                raise PriceUnavailableError(f"no price for {symbol}")
            quotes[symbol] = quote
        return value_wallet(wallet, quotes)
