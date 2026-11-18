"""A user's own keys for market-data providers: data fetched with one is only ever shown to its owner.

Each provider takes its own shape of key: Alpaca a key id and a secret key, Finnhub a single key. A key is shown back
only by a hint, the end of the part its owner can recognise (Alpaca's key id, which its dashboard shows; else the key).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from shadowfolio.domain.errors import InvalidProviderKeyError

# How many characters of a key are shown back.
HINT_LENGTH = 4


class DataProvider(StrEnum):
    ALPACA = "alpaca"  # prices, dividends, splits and news
    FINNHUB = "finnhub"  # when companies report results


# The providers whose keys come in two parts, a key id and a secret.
WITH_KEY_ID = frozenset({DataProvider.ALPACA})
# The keys market data needs: prices, dividends, splits and news come from Alpaca.
NEEDED = (DataProvider.ALPACA,)
NAMES = {DataProvider.ALPACA: "Alpaca", DataProvider.FINNHUB: "Finnhub"}


@dataclass(frozen=True)
class KeyCheck:
    """Whether a saved key works with its provider, in words for its owner."""

    works: bool
    message: str


@dataclass(frozen=True)
class ProviderKey:
    owner_id: str
    provider: DataProvider
    key_id: str | None  # for providers in WITH_KEY_ID; None for the others
    secret: str
    saved_at: datetime

    def __post_init__(self) -> None:
        name = NAMES[self.provider]
        if self.provider in WITH_KEY_ID:
            if not (self.key_id and self.key_id.strip() and self.secret.strip()):
                raise InvalidProviderKeyError(f"{name} needs a key id and a secret key")
        elif self.key_id is not None:
            raise InvalidProviderKeyError(f"{name} takes a single key, without a key id")
        elif not self.secret.strip():
            raise InvalidProviderKeyError("the key must not be blank")

    @property
    def hint(self) -> str:
        return (self.key_id or self.secret)[-HINT_LENGTH:]
