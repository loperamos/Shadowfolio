"""Comparison use cases: a wallet against a benchmark given the same deposits (see domain.comparison), and how both
did over a period (see domain.performance)."""

from dataclasses import dataclass
from datetime import UTC, date, timedelta
from decimal import Decimal
from uuid import UUID

from shadowfolio.domain.comparison import Benchmark, benchmark_values
from shadowfolio.domain.errors import CorporateActionsUnavailableNowError, FxRateUnavailableError, PriceUnavailableError
from shadowfolio.domain.operations import Deposit, Withdrawal
from shadowfolio.domain.performance import DayValue, Performance, performance
from shadowfolio.domain.valuation import DailyValue
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.corporate_actions import CorporateActions, CorporateActionsUnavailableError
from shadowfolio.ports.fx_rates import FxRates, FxRatesUnavailableError
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.valuation import Valuation

# The US market as a whole: the usual yardstick, with prices from the first day of market data.
BENCHMARK_SYMBOL = "SPY"


@dataclass(frozen=True)
class PerformanceComparison:
    """How the wallet and the benchmark did over the same period; None for either when no day in it was valued."""

    wallet: Performance | None
    benchmark_symbol: str
    benchmark: Performance | None


class Comparison:
    def __init__(
        self, repo: WalletRepository, clock: Clock, prices: PriceData, fx_rates: FxRates, corporate_actions: CorporateActions
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._prices = prices
        self._fx_rates = fx_rates
        self._corporate_actions = corporate_actions
        # The wallet's own daily values: a withdrawal sells the share of the benchmark it took from the wallet.
        self._valuation = Valuation(repo, clock, prices, fx_rates)

    def benchmark_daily(self, wallet_id: UUID) -> Benchmark | None:
        """The benchmark's value at the end of every day from the wallet's first operation to today, given the wallet's
        deposits and withdrawals. Returns None if the wallet does not exist; fails as a whole when a provider cannot
        answer."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        return self._benchmark(wallet, self._valuation.daily(wallet_id) or [])

    def performance(self, wallet_id: UUID, start: date | None = None, end: date | None = None) -> PerformanceComparison | None:
        """How the wallet and the benchmark did from `start` (default: the wallet's first operation) to `end` (default:
        today). Returns None if the wallet does not exist; fails as a whole when a provider cannot answer."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        daily = self._valuation.daily(wallet_id) or []
        benchmark = self._benchmark(wallet, daily)
        start = start or (daily[0].day if daily else self._clock.now().date())
        end = end or self._clock.now().date()
        wallet_points, previous_deposits = [], Decimal(0)
        for value in daily:
            total = None if value.valuation is None else value.valuation.total
            wallet_points.append(DayValue(value.day, total, value.net_deposits - previous_deposits))
            previous_deposits = value.net_deposits
        benchmark_points = [DayValue(value.day, value.value, value.flow) for value in benchmark.values]
        return PerformanceComparison(performance(wallet_points, start, end), BENCHMARK_SYMBOL, performance(benchmark_points, start, end))

    def _benchmark(self, wallet: Wallet, daily: list[DailyValue]) -> Benchmark:
        """The benchmark for the wallet, given the wallet's own daily values."""
        if not wallet.operations:
            return Benchmark(BENCHMARK_SYMBOL, ())
        start = wallet.operations[0].timestamp.astimezone(UTC).date()
        end = self._clock.now().date()
        days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        flows: dict[date, Decimal] = {}
        for op in wallet.operations:
            if isinstance(op, Deposit | Withdrawal):
                day = op.timestamp.astimezone(UTC).date()
                flows[day] = flows.get(day, Decimal(0)) + op.cash_delta
        try:
            closes = self._prices.closes_between(BENCHMARK_SYMBOL, start, end)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {BENCHMARK_SYMBOL} right now; try again later") from error
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
            dividends = self._corporate_actions.dividends(BENCHMARK_SYMBOL, start, end)
        except CorporateActionsUnavailableError as error:
            raise CorporateActionsUnavailableNowError(
                f"could not fetch {BENCHMARK_SYMBOL}'s dividends right now; try again later"
            ) from error
        wallet_values = {value.day: value.valuation.total for value in daily if value.valuation is not None}
        return Benchmark(BENCHMARK_SYMBOL, benchmark_values(days, flows, wallet_values, closes, rates, dividends, wallet.withholding_rate))
