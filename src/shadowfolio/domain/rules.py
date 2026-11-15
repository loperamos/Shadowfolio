"""The owner's rules for a wallet: limits its orders keep within, checked when an order is placed.

They make a wallet's investment policy machine-readable, as CFA Institute's investment policy statements describe it,
and they are the boundary an agent trading the wallet works within. A rule guards the decision to trade: it is checked
when a buy is placed, not when it fills, and never for past operations entered by hand or imported.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from shadowfolio.domain.errors import InvalidRuleError, RuleBrokenError
from shadowfolio.domain.orders import Order, OrderStatus

# How shares of the wallet read in messages, e.g. 21.00%.
PERCENT = Decimal(100)
# Orders that count towards the monthly limit: the ones that trade, or still may.
COUNTED_STATUSES = frozenset({OrderStatus.OPEN, OrderStatus.FILLED})


@dataclass(frozen=True)
class Rules:
    """Shares are of the wallet's whole value, cash included (0.2 for 20%); None, or no symbols, for no limit."""

    max_position_weight: Decimal | None = None  # the most one holding may reach after a buy, above 0 and up to 100%
    min_cash_weight: Decimal | None = None  # what to keep in cash after a buy, from 0 and below 100%
    allowed_symbols: tuple[str, ...] = ()  # the only symbols it may buy, as market data writes them; any when empty
    max_orders_per_month: int | None = None  # orders placed in a calendar month (UTC), buys and sells, at least 1

    def __post_init__(self) -> None:
        if self.max_position_weight is not None and not Decimal(0) < self.max_position_weight <= Decimal(1):
            raise InvalidRuleError("the largest position must be above 0% and at most 100%")
        if self.min_cash_weight is not None and not Decimal(0) <= self.min_cash_weight < Decimal(1):
            raise InvalidRuleError("the cash to keep must be at least 0% and below 100%")
        if any(not symbol.strip() for symbol in self.allowed_symbols):
            raise InvalidRuleError("an allowed symbol must not be blank")
        if self.max_orders_per_month is not None and self.max_orders_per_month < 1:
            raise InvalidRuleError("the orders a month must be at least 1")

    @property
    def limits_value(self) -> bool:
        """Whether a buy must be valued to be checked: a limit on a holding's or the cash's share."""
        return self.max_position_weight is not None or self.min_cash_weight is not None

    def check_order(self, placed: Iterable[Order], now: datetime) -> None:
        """Raise RuleBrokenError if the wallet has already placed its orders for this month: those placed in it that
        are open or filled (cancelled and rejected ones never traded). For buys and sells alike."""
        if self.max_orders_per_month is None:
            return
        month = (now.astimezone(UTC).year, now.astimezone(UTC).month)
        counted = sum(
            1
            for order in placed
            if order.status in COUNTED_STATUSES and (order.placed_at.astimezone(UTC).year, order.placed_at.astimezone(UTC).month) == month
        )
        if counted >= self.max_orders_per_month:
            raise RuleBrokenError(f"the wallet has placed {counted} orders this month, its limit")

    def check_symbol(self, symbol: str) -> None:
        """Raise RuleBrokenError if `symbol` may not be bought. Any symbol may be sold, to get out of it."""
        if self.allowed_symbols and symbol not in self.allowed_symbols:
            raise RuleBrokenError(f"{symbol} is not among the symbols this wallet may buy")

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
