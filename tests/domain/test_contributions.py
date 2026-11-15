"""What each holding brought to a wallet's gain over a period (see domain.performance)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Dividend, Fee
from shadowfolio.domain.performance import Contribution, contributions

START, END = date(2024, 6, 3), date(2024, 6, 4)


def test_dividends_add_to_their_holdings_gain_and_fees_charged_on_their_own_to_none() -> None:
    at = datetime(2024, 6, 4, 14, 0, tzinfo=UTC)
    operations = (
        Dividend(uuid4(), at, "AAPL", Decimal("0.25"), Currency.EUR, Decimal(10), None, Decimal("2.13"), "aapl-div", Decimal("0.37")),
        Fee(uuid4(), at, Decimal(3), "exchange connection fee"),
    )

    found = contributions(operations, {"AAPL": Decimal(1000)}, {"AAPL": Decimal(990)}, START, END)

    assert found == (Contribution("AAPL", Decimal(1000), Decimal(990), Decimal("-7.87")),)  # -10, and 2.13 paid out
