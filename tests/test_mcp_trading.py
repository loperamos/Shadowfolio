"""The MCP server's trading tools, as an agent uses them: preview an order before placing it, place it now with a
reason (the decision log), cancel it, and read its orders with how the filled ones turned out. Nothing back-dated: the
tools have no time to give."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.interfaces.mcp.access import acting_with
from shadowfolio.wiring.test import build_test_app

PLACED = datetime(2026, 3, 2, 15, 0, 30, tzinfo=UTC)
NEXT_MINUTE = datetime(2026, 3, 2, 15, 1, tzinfo=UTC)
LATER = datetime(2026, 4, 1, 15, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(PLACED)


@pytest.fixture
def prices() -> InMemoryPriceData:
    return InMemoryPriceData({"NVDA": Quote(Decimal("100"), Currency.USD, datetime(2026, 3, 2, 14, 59, tzinfo=UTC))})


@pytest.fixture
def app(clock: FixedClock, prices: InMemoryPriceData) -> Any:
    return build_test_app(clock=clock, prices=prices)


def a_wallet(app: Any, **rules: Any) -> str:
    """A USD wallet with 10000 in cash and the given rules."""
    http = TestClient(app)
    wallet_id: str = http.post("/api/wallets", json={"name": "Agent's", "currency": "USD", "cash": "10000"}).json()["id"]
    if rules:
        body = {"max_position_weight": None, "min_cash_weight": None, "allowed_symbols": [], "max_orders_per_month": None, **rules}
        assert http.put(f"/api/wallets/{wallet_id}/rules", json=body).status_code == 200
    # The agent's token: trading, in this wallet.
    secret = http.post("/api/access-tokens", json={"name": "agent", "scope": "trading", "wallet_ids": [wallet_id]}).json()["secret"]
    app.state.agent_token = app.state.access_tokens.authenticate(secret)
    return wallet_id


async def call(app: Any, tool: str, **arguments: Any) -> Any:
    with acting_with(app.state.agent_token):
        async with Client(app.state.mcp) as client:
            result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content
    return result.structured_content


async def error_of(app: Any, tool: str, **arguments: Any) -> str:
    with acting_with(app.state.agent_token):
        async with Client(app.state.mcp) as client:
            result = await client.call_tool(tool, arguments)
    assert result.is_error
    text: str = result.content[0].text  # type: ignore[union-attr]
    return text


@pytest.mark.anyio
async def test_a_preview_says_what_the_order_would_do_and_places_nothing(app: Any) -> None:
    wallet_id = a_wallet(app, max_position_weight="0.15")

    preview = await call(app, "preview_order", wallet_id=wallet_id, side="buy", symbol="nvda", quantity="20")

    # 20 x 100 USD: 2000 of the 10000 left to spend, and 20% of the wallet in NVDA, above its limit of 15%.
    assert (preview["amount"], preview["buying_power_after"], preview["holding_weight_after_percent"]) == ("2000.00", "8000.00", "20.00")
    assert preview["refusal"] == "the order would put 20.00% of the wallet in NVDA, above the limit of 15.00%"
    assert "next open" in preview["fill_rule"]
    assert (await call(app, "list_orders", wallet_id=wallet_id))["result"] == []


@pytest.mark.anyio
async def test_a_preview_warns_of_an_order_that_would_be_rejected_when_it_fills(app: Any) -> None:
    wallet_id = a_wallet(app)

    sell = await call(app, "preview_order", wallet_id=wallet_id, side="sell", symbol="NVDA", quantity="5")
    buy = await call(app, "preview_order", wallet_id=wallet_id, side="buy", symbol="NVDA", quantity="150")

    assert (sell["refusal"], sell["warnings"]) == (None, ["the wallet holds 0 NVDA, fewer than 5: it would be rejected when it fills"])
    assert buy["warnings"] == ["it costs 15000.00 USD, more than the buying power of 10000.00 USD: it would be rejected when it fills"]


@pytest.mark.anyio
async def test_an_order_is_placed_now_with_its_reason_and_refused_when_it_breaks_a_rule(app: Any) -> None:
    wallet_id = a_wallet(app, max_position_weight="0.15")

    refused = await error_of(app, "place_order", wallet_id=wallet_id, side="buy", symbol="NVDA", quantity="20", reason="Momentum")
    placed = await call(app, "place_order", wallet_id=wallet_id, side="buy", symbol="NVDA", quantity="10", reason="Momentum, small")

    assert refused.endswith("the order would put 20.00% of the wallet in NVDA, above the limit of 15.00%")
    assert (placed["status"], placed["reason"], placed["placed_at"]) == ("open", "Momentum, small", "2026-03-02T15:00:30Z")
    assert "reason" in await error_of(app, "place_order", wallet_id=wallet_id, side="buy", symbol="NVDA", quantity="1", reason=" ")


@pytest.mark.anyio
async def test_orders_come_with_how_the_filled_ones_turned_out_and_open_ones_can_be_cancelled(
    app: Any, clock: FixedClock, prices: InMemoryPriceData
) -> None:
    wallet_id = a_wallet(app)
    for symbol, price in [("NVDA", "101"), ("SPY", "500")]:
        prices.add_bar(symbol, Quote(Decimal(price), Currency.USD, NEXT_MINUTE))
    filled = await call(app, "place_order", wallet_id=wallet_id, side="buy", symbol="NVDA", quantity="10", reason="Earnings ahead")
    to_cancel = await call(app, "place_order", wallet_id=wallet_id, side="buy", symbol="NVDA", quantity="1", reason="Dip", limit_price="50")
    clock.set(LATER)
    prices.set("NVDA", Quote(Decimal("111.10"), Currency.USD, LATER))
    prices.set("SPY", Quote(Decimal("505"), Currency.USD, LATER))

    cancelled = await call(app, "cancel_order", wallet_id=wallet_id, order_id=to_cancel["id"])
    orders = (await call(app, "list_orders", wallet_id=wallet_id))["result"]

    assert cancelled["status"] == "cancelled"
    # Filled at the next minute's 101; now 111.10, +10%, while SPY rose 1% from the same minute.
    assert [(o["order"]["id"], o["order"]["status"], o["order"]["reason"]) for o in orders] == [
        (filled["id"], "filled", "Earnings ahead"),
        (to_cancel["id"], "cancelled", "Dip"),
    ]
    assert (orders[0]["outcome"]["return_percent"], orders[0]["outcome"]["benchmark_return_percent"]) == ("10.00", "1.00")
    assert orders[1]["outcome"] is None


@pytest.mark.anyio
async def test_the_trading_tools_take_no_time_so_nothing_is_back_dated(app: Any) -> None:
    async with Client(app.state.mcp) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    for name in ("preview_order", "place_order", "cancel_order", "list_orders"):
        properties = tools[name].input_schema["properties"]
        assert not {"timestamp", "at", "date", "placed_at"} & properties.keys(), name
