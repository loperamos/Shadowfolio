"""The MCP server: what an agent can read about the user's wallets and the securities they hold or consider.

Agents connect over MCP's Streamable HTTP transport, at MCP_PATH on the same app as the web API. The tools call the
same use cases and answer with the same response models as the web API, so an agent sees the figures the user sees,
each with its time and, where it applies, what could not be fetched. Read-only for now: placing orders comes with the
trading scope (see SPEC.md).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.schemas import (
    OrderResponse,
    PerformanceResponse,
    SecuritySummaryResponse,
    ValuationResponse,
    WalletResponse,
)
from shadowfolio.interfaces.web.wallets import LOCAL_OWNER
from shadowfolio.usecases.comparison import Comparison
from shadowfolio.usecases.orders import Orders
from shadowfolio.usecases.securities import Securities
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallets import Wallets

MCP_PATH = "/mcp"
SERVER_NAME = "Shadowfolio"
# As many securities as the web comparison takes.
MAX_COMPARED = 6
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
INSTRUCTIONS = """\
Shadowfolio simulates investment wallets with real market data; nothing here touches a real brokerage account.
Amounts are exact decimal strings, in the wallet's currency unless a currency is given. Percentages are in percent
(12.5 means 12.5%), ratios such as beta and P/E are plain numbers. Times are UTC. Every price has its as_of time: a
price can be from the last close while the market is closed. A null value means it is not known; when a part could not
be fetched, `unavailable` (or `valuation_unavailable`) says why. Prices and figures describe the past; none predicts.
"""


class WalletListing(BaseModel):
    id: UUID
    name: str
    currency: str
    cash: Decimal


class PerformanceSinceStart(BaseModel):
    """How the wallet did since its first operation, next to `benchmark_symbol` with the same deposits."""

    wallet: PerformanceResponse | None
    benchmark_symbol: str
    benchmark: PerformanceResponse | None


class WalletSnapshot(BaseModel):
    """A wallet at a glance: its settings and rules, its value now, its open orders and how it did since it started."""

    wallet: WalletResponse
    valuation: ValuationResponse | None  # null when it cannot be valued now; valuation_unavailable says why
    valuation_unavailable: str | None
    open_orders: list[OrderResponse]
    performance_since_start: PerformanceSinceStart | None  # null when it cannot be worked out now


def mcp_server(wallets: Wallets, valuation: Valuation, orders: Orders, comparison: Comparison, securities: Securities) -> MCPServer:
    server = MCPServer(name=SERVER_NAME, instructions=INSTRUCTIONS)

    @server.tool(annotations=READ_ONLY)
    def list_wallets() -> list[WalletListing]:
        """The user's wallets: id, name, currency and cash. Use an id with wallet_snapshot for the rest."""
        return [WalletListing(id=w.id, name=w.name, currency=w.currency.value, cash=w.cash) for w in wallets.list(LOCAL_OWNER)]

    @server.tool(annotations=READ_ONLY)
    def wallet_snapshot(wallet_id: UUID) -> WalletSnapshot:
        """A wallet at a glance: its value now at the latest prices (each holding with its price time, weight and gain),
        cash and buying power after open buy orders, how concentrated it is, the owner's rules for orders, its open
        orders, and its returns since it started next to SPY with the same deposits."""
        found = orders.list(wallet_id)  # reading the orders fills the ones due, as the web page does
        if found is None:
            raise ToolError(f"no wallet {wallet_id}")
        valued, unavailable = None, None
        try:
            current = valuation.current(wallet_id)
            valued = None if current is None else ValuationResponse.from_valuation(current)
        except DomainError as error:
            unavailable = str(error)
        try:
            result = comparison.performance(wallet_id)
            performance = (
                None
                if result is None
                else PerformanceSinceStart(
                    wallet=None if result.wallet is None else PerformanceResponse.from_performance(result.wallet),
                    benchmark_symbol=result.benchmark_symbol,
                    benchmark=None if result.benchmark is None else PerformanceResponse.from_performance(result.benchmark),
                )
            )
        except DomainError:
            performance = None
        return WalletSnapshot(
            wallet=WalletResponse.from_wallet(found),
            valuation=valued,
            valuation_unavailable=unavailable,
            open_orders=[OrderResponse.from_order(order, found) for order in found.orders if order.is_open],
            performance_since_start=performance,
        )

    @server.tool(annotations=READ_ONLY)
    def security_summary(symbol: str, start: date | None = None, end: date | None = None) -> SecuritySummaryResponse:
        """A security at a glance: latest price, valuation (P/E, price to sales, FCF yield, market cap), last fiscal
        year's growth and margin, dividends, trend over 3, 6 and 12 months, and from `start` to `end` (default: the last
        year) its volatility, deepest fall, beta against SPY and daily traded value; its industry and next earnings."""
        return SecuritySummaryResponse.from_summary(securities.summary(symbol.strip().upper(), start, end))

    @server.tool(annotations=READ_ONLY)
    def compare_securities(symbols: list[str], start: date | None = None, end: date | None = None) -> list[SecuritySummaryResponse]:
        """Several securities' summaries (as security_summary), in the order given, to compare them side by side."""
        if not 1 <= len(symbols) <= MAX_COMPARED:
            raise ToolError(f"compare 1 to {MAX_COMPARED} securities at a time")
        return [SecuritySummaryResponse.from_summary(securities.summary(symbol.strip().upper(), start, end)) for symbol in symbols]

    return server
