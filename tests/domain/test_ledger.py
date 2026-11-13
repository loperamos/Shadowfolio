"""FIFO lots: what holdings cost and what selling gains."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from shadowfolio.domain.ledger import Lot, build_ledger
from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Deposit, Operation, Sell, Split, Trade

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


def test_a_split_resizes_the_lots_and_keeps_their_cost() -> None:
    split = Split(uuid4(), START + timedelta(days=3), "AAPL", Decimal(1), Decimal(4), "aapl-split")
    ledger = build_ledger(timeline(buy(1, "10", "1000"), buy(2, "5", "600"), split, sell(4, "45", "1200")))

    # 60 shares after the split: the first lot (40 shares, 1000) and 5 of the second (20 shares, 600 → 150) are sold.
    assert ledger.positions["AAPL"].lots == (Lot(Decimal("15"), Decimal("450")),)
    assert ledger.realized_gain == Decimal("50")
