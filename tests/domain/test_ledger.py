"""FIFO lots: what holdings cost and what selling gains."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from shadowfolio.domain.ledger import Lot, build_ledger
from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Deposit, Operation, Sell, Trade

START = datetime(2024, 1, 2, 9, 0, tzinfo=UTC)


def timeline(*operations: Operation) -> list[Operation]:
    return [Deposit(uuid4(), START, Decimal("100000")), *operations]


def buy(day: int, quantity: str, settled: str, fees: str = "0") -> Buy:
    trade = Trade("AAPL", Decimal(quantity), Decimal(settled) / Decimal(quantity), Currency.USD)
    return Buy(uuid4(), START + timedelta(days=day), trade, Decimal(settled), Decimal(fees))


def sell(day: int, quantity: str, settled: str, fees: str = "0") -> Sell:
    trade = Trade("AAPL", Decimal(quantity), Decimal(settled) / Decimal(quantity), Currency.USD)
    return Sell(uuid4(), START + timedelta(days=day), trade, Decimal(settled), Decimal(fees))


def test_a_buy_costs_its_settled_amount_plus_fees() -> None:
    ledger = build_ledger(timeline(buy(1, "10", "1000", fees="10")))

    assert ledger.positions["AAPL"].lots == (Lot(Decimal("10"), Decimal("1010")),)
    assert ledger.realized_gain == 0


def test_sells_close_the_oldest_lots_first() -> None:
    ledger = build_ledger(timeline(buy(1, "10", "1000", fees="10"), buy(2, "10", "1200"), sell(3, "15", "1800", fees="5")))

    # Sold: all of the first lot (1010) and half of the second (600); proceeds 1800 - 5.
    assert ledger.realized_gain == Decimal("185")
    assert ledger.positions["AAPL"].lots == (Lot(Decimal("5"), Decimal("600")),)


def test_a_loss_is_a_negative_gain() -> None:
    ledger = build_ledger(timeline(buy(1, "10", "1000"), sell(2, "10", "900")))

    assert ledger.realized_gain == Decimal("-100")
    assert "AAPL" not in ledger.positions
