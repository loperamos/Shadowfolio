"""Prices that stand in for a missing close: the price of the wallet's nearest trade in the symbol."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Sell, SharesReceived, Trade
from shadowfolio.domain.valuation import estimated_price


def trade(kind: type[Buy] | type[Sell], day: date, price: str) -> Buy | Sell:
    at = datetime(day.year, day.month, day.day, 15, 0, tzinfo=UTC)
    return kind(uuid4(), at, Trade("9MD.XGAT", Decimal(1), Decimal(price), Currency.EUR), Decimal(price), Decimal(0))


def test_the_last_trade_on_or_before_the_day_gives_the_price() -> None:
    operations = [trade(Buy, date(2023, 1, 4), "10.00"), trade(Sell, date(2024, 2, 7), "8.14")]

    quote = estimated_price(operations, "9MD.XGAT", date(2023, 6, 1))

    assert quote is not None and (quote.price, quote.currency, quote.as_of.date()) == (Decimal("10.00"), Currency.EUR, date(2023, 1, 4))


def test_shares_received_without_a_price_take_the_next_trades() -> None:
    received = SharesReceived(uuid4(), datetime(2023, 1, 4, 9, 0, tzinfo=UTC), "9MD.XGAT", Decimal(1), Decimal(0))
    operations = [received, trade(Sell, date(2024, 2, 7), "8.14")]

    quote = estimated_price(operations, "9MD.XGAT", date(2023, 6, 1))

    assert quote is not None and quote.price == Decimal("8.14")


def test_a_symbol_never_traded_has_no_estimate() -> None:
    assert estimated_price([trade(Buy, date(2023, 1, 4), "10.00")], "NNND.XGAT", date(2023, 6, 1)) is None
