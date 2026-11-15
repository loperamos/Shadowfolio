"""The MCP server's read-only tools, called as an agent would (through the protocol, in-process): wallets, a wallet's
snapshot, and securities, with the same figures, times and caveats as the web API."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_company_data import InMemoryCompanyData
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.company import FiscalYear, Fundamentals
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
QUOTE_TIME = datetime(2026, 3, 2, 14, 59, tzinfo=UTC)
ACME = Fundamentals(
    company_name="ACME CORP",
    currency=Currency.USD,
    years=(FiscalYear(date(2025, 1, 1), date(2025, 12, 31), Decimal("1000000"), Decimal("200000"), Decimal("2.00")),),
    shares_outstanding=Decimal("100000"),
    shares_as_of=date(2026, 2, 1),
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def app() -> Any:
    prices = InMemoryPriceData({"ACME": Quote(Decimal("50"), Currency.USD, QUOTE_TIME)})
    fx_rates = InMemoryFxRates()
    fx_rates.set(FxRate(Currency.USD, Currency.EUR, Decimal("0.90"), date(2026, 3, 2)))
    return build_test_app(clock=FixedClock(NOW), prices=prices, fx_rates=fx_rates, company_data=InMemoryCompanyData({"ACME": ACME}))


def a_wallet(app: Any) -> str:
    """An EUR wallet with 1000 deposited and 10 ACME bought at 40 USD (360 EUR)."""
    http = TestClient(app)
    wallet_id: str = http.post("/api/wallets", json={"name": "Agent's", "currency": "EUR", "cash": "0"}).json()["id"]
    http.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "1000", "timestamp": "2026-01-05T09:00:00Z"})
    buy = {
        "symbol": "ACME",
        "quantity": "10",
        "price": "40",
        "price_currency": "USD",
        "settled_amount": "360",
        "timestamp": "2026-01-06T15:00:00Z",
    }
    assert http.post(f"/api/wallets/{wallet_id}/buys", json=buy).status_code == 200
    return wallet_id


async def call(app: Any, tool: str, **arguments: Any) -> Any:
    async with Client(app.state.mcp) as client:
        result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content
    return result.structured_content


@pytest.mark.anyio
async def test_the_read_tools_are_offered_each_described(app: Any) -> None:
    async with Client(app.state.mcp) as client:
        tools = (await client.list_tools()).tools

    assert {tool.name for tool in tools} == {"list_wallets", "wallet_snapshot", "security_summary", "compare_securities"}
    assert all(tool.description for tool in tools)


@pytest.mark.anyio
async def test_a_wallets_snapshot_has_its_value_weights_buying_power_and_rules(app: Any) -> None:
    wallet_id = a_wallet(app)

    assert (await call(app, "list_wallets"))["result"] == [{"id": wallet_id, "name": "Agent's", "currency": "EUR", "cash": "640"}]
    snapshot = await call(app, "wallet_snapshot", wallet_id=wallet_id)

    # 10 x 50 USD = 500 USD = 450 EUR, at the price of 14:59: of 1090 EUR in all, 41.28% in ACME.
    valuation = snapshot["valuation"]
    assert (valuation["total"], valuation["buying_power"], valuation["cash_weight_percent"]) == ("1090.00", "640.00", "58.72")
    [holding] = valuation["holdings"]
    assert (holding["symbol"], holding["value_in_wallet_currency"], holding["weight_percent"], holding["as_of"]) == (
        "ACME",
        "450.00",
        "41.28",
        "2026-03-02T14:59:00Z",
    )
    assert snapshot["wallet"]["rules"]["max_position_weight"] is None
    assert snapshot["open_orders"] == []


@pytest.mark.anyio
async def test_securities_come_summarised_and_side_by_side(app: Any) -> None:
    summary = await call(app, "security_summary", symbol="acme")

    assert (summary["symbol"], summary["pe"], summary["market_cap"], summary["unavailable"]) == ("ACME", "25.00", "5000000.00", [])
    compared = await call(app, "compare_securities", symbols=["ACME", "ZZZZ"])
    assert [(s["symbol"], s["price"]) for s in compared["result"]] == [("ACME", "50"), ("ZZZZ", None)]


@pytest.mark.anyio
async def test_an_unknown_wallet_is_an_error_the_agent_can_read(app: Any) -> None:
    async with Client(app.state.mcp) as client:
        result = await client.call_tool("wallet_snapshot", {"wallet_id": "00000000-0000-0000-0000-000000000000"})

    assert result.is_error
    assert "no wallet" in result.content[0].text  # type: ignore[union-attr]


def test_each_request_stands_alone_as_on_the_rest_api(app: Any) -> None:
    """No session to open first, and one plain JSON answer: any server instance can answer any request."""
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_wallets", "arguments": {}}}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

    # As a local client calls it: the server only answers requests addressed to localhost.
    with TestClient(app, base_url="http://127.0.0.1:8000") as http:  # runs the app's startup, as a server does
        response = http.post("/mcp", json=request, headers=headers)

    assert (response.status_code, response.headers["content-type"]) == (200, "application/json")
    assert "mcp-session-id" not in response.headers
    assert response.json()["result"]["structuredContent"] == {"result": []}
