"""Ledger: what each holding cost, and what selling has gained, using FIFO lots.

Costs and gains are in the wallet's currency, from what actually moved in the account: a buy costs its settled amount
plus fees, a sell brings its settled amount minus fees. For shares priced in another currency, the exchange rate paid
is part of the cost, so gains include currency effects.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from shadowfolio.domain.operations import Buy, Operation, Sell, Split


@dataclass(frozen=True)
class Lot:
    """Shares bought together, and what they cost."""

    quantity: Decimal
    cost: Decimal


@dataclass(frozen=True)
class Position:
    """The lots still held for one symbol, oldest first."""

    lots: tuple[Lot, ...]

    @property
    def quantity(self) -> Decimal:
        return sum((lot.quantity for lot in self.lots), Decimal(0))

    @property
    def cost(self) -> Decimal:
        return sum((lot.cost for lot in self.lots), Decimal(0))


@dataclass(frozen=True)
class Ledger:
    positions: dict[str, Position]  # only symbols still held
    realized_gain: Decimal  # from every sell so far


def build_ledger(timeline: Iterable[Operation]) -> Ledger:
    """Replay a valid timeline (oldest first): buys open lots, sells close the oldest lots first, splits resize them."""
    lots: dict[str, list[Lot]] = {}
    realized = Decimal(0)
    for op in timeline:
        match op:
            case Buy():
                lots.setdefault(op.trade.symbol, []).append(Lot(op.trade.quantity, op.settled_amount + op.fees))
            case Sell():
                cost_sold = _close_oldest(lots[op.trade.symbol], op.trade.quantity)
                realized += op.settled_amount - op.fees - cost_sold
            case Split():
                # More (or fewer) shares, for the same total cost.
                factor = op.new_rate / op.old_rate
                lots[op.symbol] = [Lot(lot.quantity * factor, lot.cost) for lot in lots.get(op.symbol, [])]
    positions = {symbol: Position(tuple(open_lots)) for symbol, open_lots in lots.items() if open_lots}
    return Ledger(positions=positions, realized_gain=realized)


def _close_oldest(lots: list[Lot], quantity: Decimal) -> Decimal:
    """Remove `quantity` shares from the oldest lots and return what they cost; a lot sold in part keeps its share of the cost."""
    cost = Decimal(0)
    remaining = quantity
    while remaining > 0:
        lot = lots[0]
        if lot.quantity <= remaining:
            cost += lot.cost
            remaining -= lot.quantity
            lots.pop(0)
        else:
            sold_cost = lot.cost * remaining / lot.quantity
            cost += sold_cost
            lots[0] = Lot(lot.quantity - remaining, lot.cost - sold_cost)
            remaining = Decimal(0)
    return cost
