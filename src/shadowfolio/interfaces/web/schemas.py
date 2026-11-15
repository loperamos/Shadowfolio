"""Request and response bodies of the HTTP API."""

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from shadowfolio.domain.company import ValueRange
from shadowfolio.domain.comparison import Benchmark
from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import (
    Buy,
    Deposit,
    Dividend,
    Fee,
    ImportedDividend,
    Income,
    Operation,
    OperationType,
    PriceSource,
    Sell,
    SharesReceived,
    Split,
    Withdrawal,
)
from shadowfolio.domain.orders import Order, OrderSide, OrderStatus
from shadowfolio.domain.performance import Performance
from shadowfolio.domain.valuation import DailyValue, Quote, WalletValuation
from shadowfolio.domain.wallet import Wallet
from shadowfolio.usecases.comparison import PerformanceComparison
from shadowfolio.usecases.imports import ImportReport
from shadowfolio.usecases.securities import CompanyFigures, SecurityRanges


class CreateWalletRequest(BaseModel):
    name: str
    currency: Currency
    cash: Decimal


class UpdateWalletRequest(BaseModel):
    """Only the fields given change."""

    name: str | None = None
    withholding_rate: Decimal | None = None  # share of each dividend withheld as tax, e.g. 0.15 for 15%


class CopyWalletRequest(BaseModel):
    name: str
    # Copy only the history before this time ("what if"); the whole history when left out.
    before: AwareDatetime | None = None


class CashMovementRequest(BaseModel):
    """A deposit or a withdrawal."""

    amount: Decimal
    timestamp: AwareDatetime | None = None  # defaults to now


class TradeRequest(BaseModel):
    symbol: str
    quantity: Decimal
    timestamp: AwareDatetime
    # The price the broker reported, with its currency. Leave both out to price the trade from market data
    # at `timestamp`; the trade is then marked as priced with hindsight.
    price: Decimal | None = None
    price_currency: Currency | None = None
    # Cash that left (buy) or entered (sell) the wallet before fees, in the wallet's currency, as the broker
    # reports it. Required when price_currency differs from the wallet's currency; computed for market prices.
    settled_amount: Decimal | None = None
    fees: Decimal = Decimal(0)


# Replacing an operation: the same fields as recording one, plus its type, which may change.
class DepositEdit(CashMovementRequest):
    type: Literal[OperationType.DEPOSIT]


class WithdrawalEdit(CashMovementRequest):
    type: Literal[OperationType.WITHDRAWAL]


class BuyEdit(TradeRequest):
    type: Literal[OperationType.BUY]


class SellEdit(TradeRequest):
    type: Literal[OperationType.SELL]


OperationEditRequest = Annotated[DepositEdit | WithdrawalEdit | BuyEdit | SellEdit, Field(discriminator="type")]


# Costs and gains are exact in the domain and rounded here, for display: money to cents, percentages to hundredths.
CENT = Decimal("0.01")


def _cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)


def _percent(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole * 100).quantize(CENT, rounding=ROUND_HALF_EVEN)


def _ratio_percent(ratio: Decimal | None) -> Decimal | None:
    return None if ratio is None else (ratio * 100).quantize(CENT, rounding=ROUND_HALF_EVEN)


def _optional_cents(amount: Decimal | None) -> Decimal | None:
    return None if amount is None else _cents(amount)


def _checked_through(wallet: Wallet) -> date | None:
    held = wallet.holdings
    periods = [wallet.checked.get(symbol) for symbol in held]
    if not held or any(period is None for period in periods):
        return None
    return min(period.end for period in periods if period is not None)


class UncreditedDividendResponse(BaseModel):
    symbol: str
    ex_date: date
    per_share: Decimal
    currency: Currency


class WalletResponse(BaseModel):
    id: UUID
    name: str
    currency: Currency
    withholding_rate: Decimal  # share of each dividend withheld as tax, e.g. 0.15 for 15%
    cash: Decimal
    holdings: dict[str, Decimal]
    cost_basis: dict[str, Decimal]  # what each holding cost, in the wallet's currency (FIFO, fees included)
    realized_gain: Decimal  # from all sells so far, in the wallet's currency
    hindsight: bool  # some trade was priced from market data after the fact, so results are not a forward test
    # Corporate actions of the held symbols are applied up to this day (the earliest across them); null when nothing
    # is held, or when a held symbol has never been checked.
    splits_checked_through: date | None
    # Dividends the wallet qualified for but that were not credited: the data provider has no payment date for them.
    uncredited_dividends: list[UncreditedDividendResponse]

    @classmethod
    def from_wallet(cls, wallet: Wallet) -> "WalletResponse":
        ledger = wallet.ledger
        return cls(
            id=wallet.id,
            name=wallet.name,
            currency=wallet.currency,
            withholding_rate=wallet.withholding_rate,
            cash=wallet.cash,
            holdings=wallet.holdings,
            cost_basis={symbol: _cents(position.cost) for symbol, position in ledger.positions.items()},
            realized_gain=_cents(ledger.realized_gain),
            hindsight=wallet.hindsight,
            splits_checked_through=_checked_through(wallet),
            uncredited_dividends=[
                UncreditedDividendResponse(symbol=e.symbol, ex_date=e.ex_date, per_share=e.per_share, currency=e.currency)
                for e in wallet.uncredited_dividends
            ],
        )


class OperationResponse(BaseModel):
    id: UUID
    type: OperationType
    timestamp: AwareDatetime
    amount: Decimal
    fees: Decimal
    symbol: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    price_currency: Currency | None = None
    price_source: PriceSource | None = None  # trades only: entered (from the broker) or market (filled from market data)
    # Splits only: old_rate shares became new_rate shares (e.g. 1 → 10).
    split_old_rate: Decimal | None = None
    split_new_rate: Decimal | None = None
    automatic: bool = False  # added by the system from market data; cannot be edited or deleted
    had_effect: bool = True  # false for a split when no shares of its symbol were held then
    fx_rate: Decimal | None = None  # dividends only: the rate into the wallet's currency on the payment date
    # Dividends only, in the wallet's currency: before tax, and the tax withheld (amount is what was credited).
    gross: Decimal | None = None
    withholding: Decimal | None = None
    description: str | None = None  # fees and income only: the broker's wording

    @classmethod
    def from_operation(cls, operation: Operation, had_effect: bool = True) -> "OperationResponse":
        match operation:
            case Deposit() | Withdrawal():
                return cls(id=operation.id, type=operation.type, timestamp=operation.timestamp, amount=operation.amount, fees=Decimal(0))
            case Buy() | Sell():
                trade = operation.trade
                return cls(
                    id=operation.id,
                    type=operation.type,
                    timestamp=operation.timestamp,
                    amount=operation.settled_amount,
                    fees=operation.fees,
                    symbol=trade.symbol,
                    quantity=trade.quantity,
                    price=trade.price,
                    price_currency=trade.price_currency,
                    price_source=trade.price_source,
                )
            case Split():
                return cls(
                    id=operation.id,
                    type=operation.type,
                    timestamp=operation.timestamp,
                    amount=Decimal(0),
                    fees=Decimal(0),
                    symbol=operation.symbol,
                    split_old_rate=operation.old_rate,
                    split_new_rate=operation.new_rate,
                    automatic=True,
                    had_effect=had_effect,
                )
            case SharesReceived():
                # amount: what the shares count as having cost.
                return cls(
                    id=operation.id,
                    type=operation.type,
                    timestamp=operation.timestamp,
                    amount=operation.cost,
                    fees=Decimal(0),
                    symbol=operation.symbol,
                    quantity=operation.quantity,
                )
            case Fee() | Income():
                return cls(
                    id=operation.id,
                    type=operation.type,
                    timestamp=operation.timestamp,
                    amount=operation.amount,
                    fees=Decimal(0),
                    description=operation.description,
                )
            case ImportedDividend():
                # From a broker statement: amount is what was credited, fees the broker's fee and the tax, in its currency.
                return cls(
                    id=operation.id,
                    type=operation.type,
                    timestamp=operation.timestamp,
                    amount=operation.amount,
                    fees=Decimal(0),
                    symbol=operation.symbol,
                )
            case Dividend():
                # quantity: the shares that qualified; price: the amount per share, in its currency; amount: credited (net).
                return cls(
                    id=operation.id,
                    type=operation.type,
                    timestamp=operation.timestamp,
                    amount=operation.amount,
                    fees=Decimal(0),
                    symbol=operation.symbol,
                    quantity=operation.shares,
                    price=operation.per_share,
                    price_currency=operation.currency,
                    fx_rate=operation.fx_rate,
                    gross=operation.gross,
                    withholding=operation.withholding,
                    automatic=True,
                )


class FxRateResponse(BaseModel):
    rate: Decimal  # units of the wallet's currency per unit of the price's currency
    as_of: date


class HoldingValueResponse(BaseModel):
    symbol: str
    quantity: Decimal
    price: Decimal
    currency: Currency
    as_of: AwareDatetime
    value: Decimal  # in the price's currency
    fx_rate: FxRateResponse | None  # null when the price is already in the wallet's currency
    value_in_wallet_currency: Decimal
    cost: Decimal  # in the wallet's currency
    gain: Decimal  # unrealized, in the wallet's currency; negative for a loss
    gain_percent: Decimal  # of the cost
    previous_close: Decimal | None  # in the price's currency
    day_change: Decimal | None  # since the previous close, in the wallet's currency (price only, not exchange rates)
    day_change_percent: Decimal | None  # the price's move since the previous close
    weight_percent: Decimal | None  # its share of the wallet's whole value, cash included


class ValuationResponse(BaseModel):
    currency: Currency
    cash: Decimal
    holdings: list[HoldingValueResponse]
    cost: Decimal  # of all holdings, in the wallet's currency
    gain: Decimal  # unrealized gain of all holdings
    gain_percent: Decimal | None  # of the cost; null when nothing is held
    day_change: Decimal | None  # of all holdings since the previous close; null if any holding has no previous close
    day_change_percent: Decimal | None  # of the holdings' value at the previous close
    total: Decimal  # cash plus holdings, in the wallet's currency
    cash_weight_percent: Decimal | None  # cash's share of the whole value
    largest_weight_percent: Decimal | None  # the largest holding's share of the whole value
    effective_holdings: Decimal | None  # how many equal-sized holdings the holdings spread risk like

    @classmethod
    def from_valuation(cls, valuation: WalletValuation) -> "ValuationResponse":
        return cls(
            currency=valuation.currency,
            cash=valuation.cash,
            holdings=[
                HoldingValueResponse(
                    symbol=h.symbol,
                    quantity=h.quantity,
                    price=h.quote.price,
                    currency=h.quote.currency,
                    as_of=h.quote.as_of,
                    value=h.value,
                    fx_rate=FxRateResponse(rate=h.fx_rate.rate, as_of=h.fx_rate.as_of) if h.fx_rate else None,
                    value_in_wallet_currency=h.value_in_wallet_currency,
                    cost=_cents(h.cost),
                    gain=_cents(h.gain),
                    gain_percent=_percent(h.gain, h.cost),
                    previous_close=h.quote.previous_close,
                    day_change=_optional_cents(h.day_change),
                    day_change_percent=_ratio_percent(h.day_change_ratio),
                    weight_percent=_ratio_percent(valuation.weight(h)),
                )
                for h in valuation.holdings
            ],
            cost=_cents(valuation.cost),
            gain=_cents(valuation.gain),
            gain_percent=_percent(valuation.gain, valuation.cost) if valuation.cost else None,
            day_change=_optional_cents(valuation.day_change),
            day_change_percent=_ratio_percent(valuation.day_change_ratio),
            total=valuation.total,
            cash_weight_percent=_ratio_percent(valuation.cash_weight),
            largest_weight_percent=_ratio_percent(valuation.largest_weight),
            effective_holdings=None
            if valuation.effective_holdings is None
            else valuation.effective_holdings.quantize(CENT, rounding=ROUND_HALF_EVEN),
        )


class BenchmarkValueResponse(BaseModel):
    day: date
    value: Decimal | None  # in the wallet's currency; null when the benchmark has no close or rate that day


class BenchmarkResponse(BaseModel):
    """What the wallet's money would be worth in `symbol` instead, at the end of every day (see the endpoint)."""

    symbol: str
    values: list[BenchmarkValueResponse]

    @classmethod
    def from_benchmark(cls, benchmark: Benchmark) -> "BenchmarkResponse":
        return cls(symbol=benchmark.symbol, values=[BenchmarkValueResponse(day=v.day, value=v.value) for v in benchmark.values])


class PerformanceResponse(BaseModel):
    """How a wallet or a benchmark did over a period (see domain.performance); returns in percent."""

    start_day: date  # the day whose end value the period starts from
    end_day: date  # its last valued day
    start_value: Decimal
    end_value: Decimal
    net_deposits: Decimal  # money put in less money taken out in the period
    gain: Decimal  # end value - start value - net deposits
    time_weighted_return: Decimal  # ignores when money was put in or taken out
    time_weighted_return_per_year: Decimal | None  # only for periods of a year or more
    money_weighted_return: Decimal | None  # includes it; null when no rate explains the end value
    money_weighted_return_per_year: Decimal | None  # only for periods of a year or more

    @classmethod
    def from_performance(cls, result: Performance) -> "PerformanceResponse":
        time_weighted = _ratio_percent(result.time_weighted)
        assert time_weighted is not None
        return cls(
            start_day=result.start_day,
            end_day=result.end_day,
            start_value=_cents(result.start_value),
            end_value=_cents(result.end_value),
            net_deposits=_cents(result.net_flows),
            gain=_cents(result.gain),
            time_weighted_return=time_weighted,
            time_weighted_return_per_year=_ratio_percent(result.time_weighted_per_year),
            money_weighted_return=_ratio_percent(result.money_weighted),
            money_weighted_return_per_year=_ratio_percent(result.money_weighted_per_year),
        )


class PlaceOrderRequest(BaseModel):
    """An order placed now: at market, it fills at the first price after it; with a limit price, on the first later
    minute that reaches it (see domain.orders)."""

    side: OrderSide
    symbol: str = Field(min_length=1)
    quantity: Decimal
    reason: str = ""  # why it is placed, kept as a decision log
    limit_price: Decimal | None = None  # the most a buy pays or the least a sell takes, in the symbol's currency


class OrderResponse(BaseModel):
    id: UUID
    side: OrderSide
    symbol: str
    quantity: Decimal
    reason: str
    limit_price: Decimal | None  # null for a market order
    placed_at: AwareDatetime
    status: OrderStatus
    closed_at: AwareDatetime | None  # when it filled (the price's time), was cancelled or rejected
    price: Decimal | None  # what it filled at, in `price_currency`; null until filled
    price_currency: Currency | None
    rejection: str | None  # why it was rejected

    @classmethod
    def from_order(cls, order: Order, wallet: Wallet) -> "OrderResponse":
        trade = next((op.trade for op in wallet.operations if op.id == order.id and isinstance(op, Buy | Sell)), None)
        return cls(
            id=order.id,
            side=order.side,
            symbol=order.symbol,
            quantity=order.quantity,
            reason=order.reason,
            limit_price=order.limit_price,
            placed_at=order.placed_at,
            status=order.status,
            closed_at=order.closed_at,
            price=None if trade is None else trade.price,
            price_currency=None if trade is None else trade.price_currency,
            rejection=order.rejection,
        )


class FillSummaryResponse(BaseModel):
    wallets: int  # wallets looked at
    filled: int  # orders filled


class DailyReturnResponse(BaseModel):
    day: date
    value: Decimal | None  # the return since the start of the period, in percent; null when the day could not be valued


class PerformanceComparisonResponse(BaseModel):
    """How the wallet did over a period next to `benchmark_symbol` with the same deposits; null when nothing in the
    period could be valued."""

    wallet: PerformanceResponse | None
    benchmark_symbol: str
    benchmark: PerformanceResponse | None
    # The time-weighted return since the start of the period, day by day: comparable whatever money each had.
    wallet_returns: list[DailyReturnResponse]
    benchmark_returns: list[DailyReturnResponse]

    @classmethod
    def from_comparison(cls, comparison: PerformanceComparison) -> "PerformanceComparisonResponse":
        return cls(
            wallet=None if comparison.wallet is None else PerformanceResponse.from_performance(comparison.wallet),
            benchmark_symbol=comparison.benchmark_symbol,
            benchmark=None if comparison.benchmark is None else PerformanceResponse.from_performance(comparison.benchmark),
            wallet_returns=_daily_returns(comparison.wallet_returns),
            benchmark_returns=_daily_returns(comparison.benchmark_returns),
        )


def _daily_returns(returns: tuple[tuple[date, Decimal | None], ...]) -> list[DailyReturnResponse]:
    return [DailyReturnResponse(day=day, value=_ratio_percent(value)) for day, value in returns]


class DailyValueResponse(BaseModel):
    """The wallet at the end of a day, valued at that day's closing prices, in its currency."""

    day: date
    cash: Decimal
    holdings_value: Decimal | None  # null when the day cannot be valued (see missing)
    total: Decimal | None  # cash plus holdings; null when the day cannot be valued
    net_deposits: Decimal  # deposits minus withdrawals up to then, so a chart can tell money put in from gains
    missing: list[str]  # what has no price (a symbol) or rate (e.g. "USD→EUR") that day; empty when valued
    estimated: list[str]  # holdings without a close that day, valued at the price of the wallet's nearest trade in them

    @classmethod
    def from_daily_value(cls, value: DailyValue) -> "DailyValueResponse":
        if value.total is None:
            return cls(
                day=value.day,
                cash=value.cash,
                holdings_value=None,
                total=None,
                net_deposits=value.net_deposits,
                missing=list(value.missing),
                estimated=list(value.estimated),
            )
        holdings_value = _cents(value.total - value.cash)
        return cls(
            day=value.day,
            cash=value.cash,
            holdings_value=holdings_value,
            total=value.cash + holdings_value,
            net_deposits=value.net_deposits,
            missing=[],
            estimated=list(value.estimated),
        )


class StatementRequest(BaseModel):
    """A broker's two exports, as the files' text."""

    transactions: str  # trades
    account: str  # cash movements


class ImportProblemResponse(BaseModel):
    date: date
    kind: str  # what the row was read as
    description: str  # the statement's wording
    reason: str  # why it was not imported


class ImportResponse(BaseModel):
    records: int  # read from the statement
    can_import: bool  # every record goes in
    imported: bool  # saved: only on an import (not a preview) that can import
    problems: list[ImportProblemResponse]
    cash: Decimal  # in the wallet after the import, in its currency
    holdings: dict[str, Decimal]  # after the import

    @classmethod
    def from_report(cls, report: ImportReport) -> "ImportResponse":
        assert report.wallet is not None
        problems = [
            ImportProblemResponse(
                date=p.record.timestamp.date(), kind=p.record.kind.value, description=p.record.description, reason=p.reason
            )
            for p in report.not_imported
        ]
        return cls(
            records=report.records,
            can_import=report.imported,
            imported=report.saved,
            problems=problems,
            cash=report.wallet.cash,
            holdings=report.wallet.holdings,
        )


class QuoteResponse(BaseModel):
    symbol: str
    price: Decimal
    currency: Currency
    as_of: AwareDatetime
    previous_close: Decimal | None
    day_change: Decimal | None  # since the previous close; null without one
    day_change_percent: Decimal | None

    @classmethod
    def from_quote(cls, symbol: str, quote: Quote) -> "QuoteResponse":
        return cls(
            symbol=symbol,
            price=quote.price,
            currency=quote.currency,
            as_of=quote.as_of,
            previous_close=quote.previous_close,
            day_change=quote.change,
            day_change_percent=_ratio_percent(quote.change_ratio),
        )


class FiscalYearResponse(BaseModel):
    start: date
    end: date
    revenue: Decimal | None
    net_income: Decimal | None
    eps_diluted: Decimal | None
    revenue_growth: Decimal | None  # on the year before, in percent; null without it
    net_margin: Decimal | None  # net income as a share of revenue, in percent


class FundamentalsResponse(BaseModel):
    """A company's reported yearly results (amounts in `currency`, oldest first) and shares outstanding, with the P/E
    (against the last fiscal year's diluted EPS) and market cap at the latest price; those are null without one."""

    company_name: str
    currency: Currency
    years: list[FiscalYearResponse]
    shares_outstanding: Decimal | None
    shares_as_of: date | None
    price: Decimal | None
    pe: Decimal | None
    market_cap: Decimal | None

    @classmethod
    def from_figures(cls, figures: CompanyFigures) -> "FundamentalsResponse":
        fundamentals = figures.fundamentals
        return cls(
            company_name=fundamentals.company_name,
            currency=fundamentals.currency,
            years=[
                FiscalYearResponse(
                    start=y.start,
                    end=y.end,
                    revenue=y.revenue,
                    net_income=y.net_income,
                    eps_diluted=y.eps_diluted,
                    revenue_growth=_ratio_percent(fundamentals.revenue_growth(y)),
                    net_margin=_ratio_percent(y.net_margin),
                )
                for y in fundamentals.years
            ],
            shares_outstanding=fundamentals.shares_outstanding,
            shares_as_of=fundamentals.shares_as_of,
            price=None if figures.price is None else figures.price.price,
            pe=None if figures.pe is None else figures.pe.quantize(CENT, rounding=ROUND_HALF_EVEN),
            market_cap=_optional_cents(figures.market_cap),
        )


class ArticleResponse(BaseModel):
    headline: str
    summary: str
    source: str
    url: str
    published_at: AwareDatetime


class ValueRangeResponse(BaseModel):
    low: Decimal
    high: Decimal
    current: Decimal  # the latest day's
    start: date  # the first and last days it covers
    end: date

    @classmethod
    def from_range(cls, value_range: ValueRange, places: Decimal | None = None) -> "ValueRangeResponse":
        """Rounded to `places` (e.g. CENT for a ratio), or as they are."""

        def shown(value: Decimal) -> Decimal:
            return value if places is None else value.quantize(places, rounding=ROUND_HALF_EVEN)

        return cls(
            low=shown(value_range.low),
            high=shown(value_range.high),
            current=shown(value_range.current),
            start=value_range.start,
            end=value_range.end,
        )


class SecurityRangesResponse(BaseModel):
    """Where the price and the P/E stand within their lows and highs over a period; null without them."""

    price: ValueRangeResponse | None
    pe: ValueRangeResponse | None

    @classmethod
    def from_ranges(cls, ranges: SecurityRanges) -> "SecurityRangesResponse":
        return cls(
            price=None if ranges.price is None else ValueRangeResponse.from_range(ranges.price),
            pe=None if ranges.pe is None else ValueRangeResponse.from_range(ranges.pe, CENT),
        )


class DailyCloseResponse(BaseModel):
    day: date
    close: Decimal
    currency: Currency


class SyncSummaryResponse(BaseModel):
    wallets: int  # wallets checked
    added: int
