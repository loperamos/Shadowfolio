"""A security's price history as it is shown: in today's shares, whatever splits happened since."""

from collections.abc import Iterable, Sequence
from dataclasses import replace
from decimal import Decimal

from shadowfolio.domain.corporate_actions import SplitEvent
from shadowfolio.domain.valuation import Quote


def split_adjusted(closes: Sequence[Quote], splits: Iterable[SplitEvent]) -> list[Quote]:
    """`closes` as if every later split had already happened: a close before a split's ex-date is divided by its ratio
    (new shares per old one), and its volume multiplied by it, so a price history reads continuously in today's
    shares, as finance sites show it. Only for showing a history: a wallet's own trades keep the prices they were made
    at."""
    adjusted = []
    for close in closes:
        factor, shares = Decimal(1), Decimal(1)  # what a price, and a count of shares, are multiplied by
        for split in splits:
            if close.as_of.date() < split.ex_date:
                factor *= split.old_rate / split.new_rate
                shares *= split.new_rate / split.old_rate
        volume = None if close.volume is None else close.volume * shares
        adjusted.append(close if factor == 1 else replace(close, price=close.price * factor, volume=volume))
    return adjusted
