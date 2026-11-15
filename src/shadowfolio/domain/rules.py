"""The owner's rules for a wallet: limits its orders keep within, checked when an order is placed.

They make a wallet's investment policy machine-readable, as CFA Institute's investment policy statements describe it,
and they are the boundary an agent trading the wallet works within. A rule guards the decision to trade: it is checked
when a buy is placed, not when it fills, and never for past operations entered by hand or imported.
"""

from dataclasses import dataclass
from decimal import Decimal

from shadowfolio.domain.errors import InvalidRuleError, RuleBrokenError

# How shares of the wallet read in messages, e.g. 21.00%.
PERCENT = Decimal(100)


@dataclass(frozen=True)
class Rules:
    """Each rule is a share of the wallet's whole value, cash included (0.2 for 20%); None for no limit."""

    max_position_weight: Decimal | None = None  # the most one holding may reach after a buy, above 0 and up to 100%
    min_cash_weight: Decimal | None = None  # what to keep in cash after a buy, from 0 and below 100%

    def __post_init__(self) -> None:
        if self.max_position_weight is not None and not Decimal(0) < self.max_position_weight <= Decimal(1):
            raise InvalidRuleError("the largest position must be above 0% and at most 100%")
        if self.min_cash_weight is not None and not Decimal(0) <= self.min_cash_weight < Decimal(1):
            raise InvalidRuleError("the cash to keep must be at least 0% and below 100%")

    @property
    def any(self) -> bool:
        return self.max_position_weight is not None or self.min_cash_weight is not None

    def check_buy(self, symbol: str, total: Decimal, position_after: Decimal, cash_after: Decimal) -> None:
        """Raise RuleBrokenError if a buy of `symbol` would break a rule: given the wallet's whole value, and what the
        holding and the cash would be once it and the open buys before it fill, all in the wallet's currency."""
        if not total:
            return
        position, cash = position_after / total, cash_after / total
        if self.max_position_weight is not None and position > self.max_position_weight:
            limit = _percent(self.max_position_weight)
            raise RuleBrokenError(f"the order would put {_percent(position)} of the wallet in {symbol}, above the limit of {limit}")
        if self.min_cash_weight is not None and cash < self.min_cash_weight:
            raise RuleBrokenError(
                f"the order would leave {_percent(cash)} of the wallet in cash, below the minimum of {_percent(self.min_cash_weight)}"
            )


def _percent(ratio: Decimal) -> str:
    return f"{ratio * PERCENT:.2f}%"
