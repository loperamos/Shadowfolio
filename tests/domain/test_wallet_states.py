"""A wallet's past states at many moments, in one pass over its operations: as rebuilding it at each moment would give."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Deposit, Sell, Split, Trade, Withdrawal
from shadowfolio.domain.wallet import Wallet

START = datetime(2024, 1, 2, 9, 0, tzinfo=UTC)


def at(days: int) -> datetime:
    return START + timedelta(days=days)


def trade(kind: type[Buy] | type[Sell], days: int, symbol: str, quantity: str, price: str) -> Buy | Sell:
    settled = Decimal(quantity) * Decimal(price)
    return kind(uuid4(), at(days), Trade(symbol, Decimal(quantity), Decimal(price), Currency.EUR), settled, Decimal(1))


def test_states_at_many_moments_match_the_wallet_as_of_each() -> None:
    operations = (
        Deposit(uuid4(), at(0), Decimal(10000)),
        trade(Buy, 1, "NVDA", "8", "900"),
        trade(Buy, 3, "AAPL", "5", "180"),
        Split(uuid4(), at(5), "NVDA", Decimal(1), Decimal(10), "nvda-split"),
        trade(Sell, 7, "AAPL", "5", "190"),  # sold out: no longer held
        Withdrawal(uuid4(), at(8), Decimal(500)),
        trade(Sell, 9, "NVDA", "30", "95"),
    )
    wallet = replace(Wallet(uuid4(), "owner", "W", Currency.EUR), operations=operations)
    moments = [at(day) + timedelta(hours=12) for day in range(-1, 11)]

    states = wallet.states_at(moments)

    expected = [(w.cash, w.net_deposits, w.holdings) for w in (wallet.as_of(moment) for moment in moments)]
    assert [(state.cash, state.net_deposits, state.holdings) for state in states] == expected
    assert states[-1].holdings == {"NVDA": Decimal(50)}  # 8 x 10 after the split, less 30 sold
