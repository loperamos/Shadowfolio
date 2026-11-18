"""Comparison use cases: a wallet against a benchmark given the same deposits (see domain.comparison), and how both
did over a period (see domain.performance)."""

from dataclasses import dataclass
from datetime import UTC, date, timedelta
from decimal import Decimal
from uuid import UUID

from shadowfolio.domain.comparison import Benchmark, benchmark_values
from shadowfolio.domain.errors import CorporateActionsUnavailableNowError, FxRateUnavailableError, PriceUnavailableError
from shadowfolio.domain.operations import Deposit, Withdrawal
from shadowfolio.domain.performance import (
    Contribution,
    DayValue,
    Performance,
    TradingActivity,
    contributions,
    cumulative_returns,
    performance,
    trading_activity,
)
from shadowfolio.domain.valuation import DailyValue
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.corporate_actions import CorporateActionsUnavailableError
from shadowfolio.ports.fx_rates import FxRates, FxRatesUnavailableError
from shadowfolio.ports.market_data import MarketDataSource
from shadowfolio.ports.price_data import PriceDataUnavailableError
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.valuation import Valuation

# The benchmark when none is chosen: the US market as a whole, the usual yardstick. Any symbol market data prices
# can be one (e.g. an ETF following another index).
DEFAULT_BENCHMARK = "SPY"


@dataclass(frozen=True)
class PerformanceComparison:
    """How the wallet and the benchmark did over the same period (None for either when no day in it was valued), and
    their time-weighted return from its start to the end of each day (None when unvalued): unlike values, returns
    compare whatever money each had."""

    wallet: Performance | None
    benchmark_symbol: str
    benchmark: Performance | None
    wallet_returns: tuple[tuple[date, Decimal | None], ...]
    benchmark_returns: tuple[tuple[date, Decimal | None], ...]
    trading: TradingActivity  # the wallet's, over the period
    contributions: tuple[Contribution, ...]  # what each holding brought to the wallet's gain; empty when unvalued

    @property
    def other_gain(self) -> Decimal | None:
        """The wallet's gain no holding brought, e.g. fees charged on their own or interest; None when unvalued."""
        if self.wallet is None:
            return None
        return self.wallet.gain - sum((contribution.gain for contribution in self.contributions), Decimal(0))


class Comparison:
    def __init__(self, repo: WalletRepository, clock: Clock, market_data: MarketDataSource, fx_rates: FxRates) -> None:
        """Benchmarks come from each wallet's owner's market data."""
        self._repo = repo
        self._clock = clock
        self._market_data = market_data
        self._fx_rates = fx_rates
        # The wallet's own daily values: a withdrawal sells the share of the benchmark it took from the wallet.
        self._valuation = Valuation(repo, clock, market_data, fx_rates)

    def benchmark_daily(self, wallet_id: UUID, symbol: str = DEFAULT_BENCHMARK) -> Benchmark | None:
        """The benchmark's value at the end of every day from the wallet's first operation to today, given the wallet's
        deposits and withdrawals. Returns None if the wallet does not exist; fails as a whole when a provider cannot
        answer."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        return self._benchmark(wallet, self._valuation.daily(wallet_id) or [], _normalized(symbol))

    def performance(
        self, wallet_id: UUID, start: date | None = None, end: date | None = None, symbol: str = DEFAULT_BENCHMARK
    ) -> PerformanceComparison | None:
        """How the wallet and the benchmark did from `start` (default: the wallet's first operation) to `end` (default:
        today), and their returns day by day. Returns None if the wallet does not exist; fails as a whole when a
        provider cannot answer."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        daily = self._valuation.daily(wallet.id) or []
        wallet_points, benchmark_symbol, benchmark_points, first_day = self._points(wallet, daily, symbol)
        start, end = start or first_day, end or self._clock.now().date()
        wallet_performance = performance(wallet_points, start, end)
        by_day = {value.day: value.holdings for value in daily}
        return PerformanceComparison(
            wallet_performance,
            benchmark_symbol,
            performance(benchmark_points, start, end),
            cumulative_returns(wallet_points, start, end),
            cumulative_returns(benchmark_points, start, end),
            trading_activity(wallet.operations, wallet_points, start, end),
            ()
            if wallet_performance is None
            else contributions(
                wallet.operations,
                by_day[wallet_performance.start_day],
                by_day[wallet_performance.end_day],
                wallet_performance.start_day,
                wallet_performance.end_day,
            ),
        )

    def _points(self, wallet: Wallet, daily: list[DailyValue], symbol: str) -> tuple[list[DayValue], str, list[DayValue], date]:
        """The wallet's and the benchmark's daily values with the money moved each day, given the wallet's own, the
        benchmark's symbol, and the wallet's first day (today when it has none)."""
        benchmark = self._benchmark(wallet, daily, _normalized(symbol))
        wallet_points, previous_deposits = [], Decimal(0)
        for value in daily:
            wallet_points.append(DayValue(value.day, value.total, value.net_deposits - previous_deposits))
            previous_deposits = value.net_deposits
        benchmark_points = [DayValue(value.day, value.value, value.flow) for value in benchmark.values]
        first_day = daily[0].day if daily else self._clock.now().date()
        return wallet_points, benchmark.symbol, benchmark_points, first_day

    def _benchmark(self, wallet: Wallet, daily: list[DailyValue], symbol: str) -> Benchmark:
        """`symbol` as the wallet's benchmark, given the wallet's own daily values; every day unvalued when market
        data has no prices for it."""
        if not wallet.operations:
            return Benchmark(symbol, ())
        start = wallet.operations[0].timestamp.astimezone(UTC).date()
        end = self._clock.now().date()
        days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        flows: dict[date, Decimal] = {}
        for op in wallet.operations:
            if isinstance(op, Deposit | Withdrawal):
                day = op.timestamp.astimezone(UTC).date()
                flows[day] = flows.get(day, Decimal(0)) + op.cash_delta
        data = self._market_data.for_user(wallet.owner_id)
        try:
            closes = data.prices.closes_between(symbol, start, end)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error
        # What one unit of the benchmark's currency is worth in the wallet's, per day.
        currency = next(iter(closes.values())).currency if closes else wallet.currency
        rates = {day: Decimal(1) for day in days}
        if currency is not wallet.currency:
            try:
                fx = self._fx_rates.rates_between(currency, wallet.currency, start, end)
            except FxRatesUnavailableError as error:
                raise FxRateUnavailableError(f"could not fetch the {currency}→{wallet.currency} rate right now; try again later") from error
            rates = {day: rate.rate for day, rate in fx.items()}
        try:
            dividends = data.corporate_actions.dividends(symbol, start, end)
        except CorporateActionsUnavailableError as error:
            raise CorporateActionsUnavailableNowError(f"could not fetch {symbol}'s dividends right now; try again later") from error
        wallet_values = {value.day: value.total for value in daily if value.total is not None}
        return Benchmark(symbol, benchmark_values(days, flows, wallet_values, closes, rates, dividends, wallet.withholding_rate))


def _normalized(symbol: str) -> str:
    """Symbols as market data writes them (e.g. "qqq " is QQQ)."""
    return symbol.strip().upper()
