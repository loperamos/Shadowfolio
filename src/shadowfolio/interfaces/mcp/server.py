"""The MCP server: what an agent can read about the user's wallets and the securities they hold or consider, and the
orders it can place in them.

Agents connect over MCP's Streamable HTTP transport, at MCP_PATH on the same app as the web API. The tools call the
same use cases and answer with the same response models as the web API, so an agent sees the figures the user sees,
each with its time and, where it applies, what could not be fetched. Orders are placed now only: no tool takes a time,
so nothing can be back-dated with hindsight (see SPEC.md, the trading scope).
"""

from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from shadowfolio.domain.access import AccessToken
from shadowfolio.domain.errors import DomainError, OrderNotFoundError
from shadowfolio.domain.money import to_cents
from shadowfolio.domain.orders import OrderSide
from shadowfolio.interfaces.mcp.access import MISSING, current_token
from shadowfolio.interfaces.web.schemas import (
    CENT,
    OrderOutcomeResponse,
    OrderResponse,
    PerformanceResponse,
    SecuritySummaryResponse,
    ValuationResponse,
    WalletResponse,
)
from shadowfolio.usecases.comparison import DEFAULT_BENCHMARK, Comparison
from shadowfolio.usecases.orders import Orders
from shadowfolio.usecases.securities import Securities
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallets import Wallets

MCP_PATH = "/mcp"
# The addresses always allowed to reach it, as host names and as browsers' origins (the SDK's own for localhost).
PERCENT = Decimal(100)
LOCAL_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")
ORIGIN_SCHEMES = ("http", "https")
SERVER_NAME = "Shadowfolio"
# As many securities as the web comparison takes.
MAX_COMPARED = 6
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
PLACES = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
CANCELS = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)
# How an order fills, as the fill model works (see domain.orders): said with every preview.
FILL_RULES = {
    False: "A market order fills at the open of the first minute after it is placed; while the market is closed, at the next open.",
    True: "A limit order fills on the first minute after it is placed that reaches its limit, at the limit or the minute's "
    "better open; until then it stays open, also through the next open.",
}
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


class OrderPreviewResponse(BaseModel):
    """What an order would do if placed now; nothing is placed. Amounts in the wallet's currency."""

    price: Decimal  # what it is counted at: its limit, or the latest price for a market order
    price_currency: str
    amount: Decimal  # what it would cost (a buy) or bring in (a sell)
    buying_power_after: Decimal | None
    holding_weight_after_percent: Decimal | None  # the symbol's share of the wallet once it fills
    refusal: str | None  # the wallet's rule or the plan's limit that refuses it now; null when place_order would accept it
    warnings: list[str]  # why it would be rejected when it fills, though placed
    fill_rule: str


class OrderWithOutcome(BaseModel):
    order: OrderResponse
    outcome: OrderOutcomeResponse | None  # how it turned out since it filled; null until filled


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
        token = _token()
        listed = [w for w in wallets.list(token.owner_id) if token.reaches(w.id)]
        return [WalletListing(id=w.id, name=w.name, currency=w.currency.value, cash=w.cash) for w in listed]

    @server.tool(annotations=READ_ONLY)
    def wallet_snapshot(wallet_id: UUID) -> WalletSnapshot:
        """A wallet at a glance: its value now at the latest prices (each holding with its price time, weight and gain),
        cash and buying power after open buy orders, how concentrated it is, the owner's rules for orders, its open
        orders, and its returns since it started next to SPY with the same deposits."""
        _reading(wallet_id)
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
        owner = _token().owner_id  # with the market data of the user the agent works for
        return SecuritySummaryResponse.from_summary(securities.summary(owner, symbol.strip().upper(), start, end))

    @server.tool(annotations=READ_ONLY)
    def compare_securities(symbols: list[str], start: date | None = None, end: date | None = None) -> list[SecuritySummaryResponse]:
        """Several securities' summaries (as security_summary), in the order given, to compare them side by side."""
        owner = _token().owner_id
        if not 1 <= len(symbols) <= MAX_COMPARED:
            raise ToolError(f"compare 1 to {MAX_COMPARED} securities at a time")
        return [SecuritySummaryResponse.from_summary(securities.summary(owner, symbol.strip().upper(), start, end)) for symbol in symbols]

    @server.tool(annotations=READ_ONLY)
    def preview_order(
        wallet_id: UUID, side: OrderSide, symbol: str, quantity: Decimal, limit_price: Decimal | None = None
    ) -> OrderPreviewResponse:
        """What an order would do if placed now, without placing it: its estimated amount (at the limit, or the latest
        price), the buying power and the symbol's share of the wallet once it fills, the wallet rule that would refuse
        it, warnings if it would be rejected when it fills, and how it fills. Use before place_order."""
        _reading(wallet_id)
        preview = _answer(lambda: orders.preview(wallet_id, side, symbol, quantity, limit_price), wallet_id)
        return OrderPreviewResponse(
            price=preview.estimate.price,
            price_currency=preview.estimate.currency.value,
            amount=preview.estimate.amount,
            buying_power_after=None if preview.buying_power_after is None else to_cents(preview.buying_power_after),
            holding_weight_after_percent=None
            if preview.holding_weight_after is None
            else (preview.holding_weight_after * PERCENT).quantize(CENT),
            refusal=preview.refusal,
            warnings=list(preview.warnings),
            fill_rule=FILL_RULES[limit_price is not None],
        )

    @server.tool(annotations=PLACES)
    def place_order(
        wallet_id: UUID, side: OrderSide, symbol: str, quantity: Decimal, reason: str, limit_price: Decimal | None = None
    ) -> OrderResponse:
        """Place an order now: at market, or with a limit price (the most a buy pays, the least a sell takes, in the
        symbol's currency). It fills later, as preview_order's fill_rule says; cash and shares are checked then. Give the
        reason for it: it is kept with the order as the decision log. Refused when it breaks one of the wallet's rules."""
        _trading(wallet_id)
        if not reason.strip():
            raise ToolError("give a reason for the order: it is kept with it as the decision log")
        placed = _answer(lambda: orders.place(wallet_id, side, symbol, quantity, reason, limit_price), wallet_id)
        wallet, order = placed
        return OrderResponse.from_order(order, wallet)

    @server.tool(annotations=CANCELS)
    def cancel_order(wallet_id: UUID, order_id: UUID) -> OrderResponse:
        """Cancel an open order; one that has filled, or was cancelled or rejected, cannot be."""
        _trading(wallet_id)
        wallet, order = _answer(lambda: orders.cancel(wallet_id, order_id), wallet_id)
        return OrderResponse.from_order(order, wallet)

    @server.tool(annotations=READ_ONLY)
    def list_orders(wallet_id: UUID, benchmark: str = DEFAULT_BENCHMARK) -> list[OrderWithOutcome]:
        """The wallet's orders in the order they were placed, each with its reason and status, and for filled ones how
        they turned out: the symbol's return since the fill next to `benchmark`'s over the same time."""
        _reading(wallet_id)
        wallet = _answer(lambda: orders.list(wallet_id), wallet_id)
        try:
            outcomes = {o.order_id: OrderOutcomeResponse.from_outcome(o) for o in orders.outcomes(wallet_id, benchmark) or []}
        except DomainError:
            outcomes = {}  # the orders still come; their outcomes when prices can be fetched again
        return [OrderWithOutcome(order=OrderResponse.from_order(o, wallet), outcome=outcomes.get(o.id)) for o in wallet.orders]

    return server


def _token() -> AccessToken:
    """The calling agent's token; every request has one, as the HTTP check lets no other through."""
    token = current_token()
    if token is None:
        raise ToolError(MISSING)
    return token


def _reading(wallet_id: UUID) -> AccessToken:
    """The token, if it may use the wallet; a wallet it may not is answered as one that does not exist."""
    token = _token()
    if not token.reaches(wallet_id):
        raise ToolError(f"no wallet {wallet_id}")
    return token


def _trading(wallet_id: UUID) -> None:
    """Only a trading token places or cancels orders, in the wallets it may use."""
    if not _reading(wallet_id).may_trade:
        raise ToolError("this access token only reads: placing or cancelling orders needs a trading token")


def _answer[T](call: Callable[[], T | None], wallet_id: UUID) -> T:
    """The use case's answer, or a tool error the agent can read: no such wallet, or a rule it broke."""
    try:
        answer = call()
    except OrderNotFoundError as error:
        raise ToolError(f"no such order in wallet {wallet_id}") from error
    except DomainError as error:
        raise ToolError(str(error)) from error
    if answer is None:
        raise ToolError(f"no wallet {wallet_id}")
    return answer


def transport_security(allowed_hosts: Sequence[str]) -> TransportSecuritySettings:
    """Against DNS rebinding (a web page making the browser talk to a server on the user's network), only requests
    addressed to localhost or to one of `allowed_hosts` (e.g. "192.168.1.75:8000", or a domain once hosted) reach it."""
    hosts = [*LOCAL_HOSTS, *allowed_hosts]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[f"{scheme}://{host}" for host in hosts for scheme in ORIGIN_SCHEMES],
    )
