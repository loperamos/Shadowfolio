"""Routes for comparing a wallet with a benchmark."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import BenchmarkResponse, PerformanceComparisonResponse
from shadowfolio.usecases.comparison import Comparison


def comparison_router(comparison: Comparison) -> APIRouter:
    router = APIRouter()

    @router.get("/wallets/{wallet_id}/benchmark/daily", responses=NOT_FOUND | INVALID)
    def benchmark_daily(wallet_id: UUID) -> BenchmarkResponse:
        """What the wallet's money would be worth in SPY instead, at the end of every day from its first operation to
        today: each deposit buys SPY that day, each withdrawal sells the same share of it as it took from the wallet,
        and SPY's dividends are reinvested after the wallet's withholding tax."""
        try:
            benchmark = comparison.benchmark_daily(wallet_id)
        except DomainError as error:
            raise rule_violation(error) from error
        if benchmark is None:
            raise wallet_not_found()
        return BenchmarkResponse.from_benchmark(benchmark)

    @router.get("/wallets/{wallet_id}/performance", responses=NOT_FOUND | INVALID)
    def wallet_performance(wallet_id: UUID, start: date | None = None, end: date | None = None) -> PerformanceComparisonResponse:
        """How the wallet did from `start` (default: its first operation) to `end` (default: today), next to SPY with the
        same deposits: gain, and returns that ignore (time-weighted) or include (money-weighted) when money moved."""
        try:
            result = comparison.performance(wallet_id, start, end)
        except DomainError as error:
            raise rule_violation(error) from error
        if result is None:
            raise wallet_not_found()
        return PerformanceComparisonResponse.from_comparison(result)

    return router
