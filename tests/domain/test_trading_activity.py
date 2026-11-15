"""What a wallet traded and paid in fees over a period, against its average value (see domain.performance)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Fee, Trade
from shadowfolio.domain.performance import DayValue, trading_activity

DAY = date(2024, 6, 3)


def test_fees_charged_on_their_own_count_and_unvalued_days_are_left_out_of_the_average() -> None:
    at = datetime(2024, 6, 3, 14, 0, tzinfo=UTC)
    operations = (
        Buy(uuid4(), at, Trade("AAPL", Decimal(1), Decimal(100), Currency.USD), Decimal(100), Decimal("0.50")),
        Fee(uuid4(), at, Decimal("2.50"), "exchange connection fee"),
    )
    values = [DayValue(DAY, Decimal(1000), Decimal(0)), DayValue(date(2024, 6, 4), None, Decimal(0))]

    activity = trading_activity(operations, values, DAY, date(2024, 6, 4))

    assert (activity.bought, activity.sold, activity.fees, activity.average_value) == (Decimal(100), Decimal(0), Decimal(3), Decimal(1000))
    assert (activity.turnover, activity.fees_ratio) == (Decimal(0), Decimal("0.003"))
