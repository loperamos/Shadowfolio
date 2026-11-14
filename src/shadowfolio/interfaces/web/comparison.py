"""Routes for comparing a wallet with a benchmark."""

from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import BenchmarkResponse
from shadowfolio.usecases.comparison import Comparison


def comparison_router(comparison: Comparison) -> APIRouter:
    router = APIRouter()

    @router.get("/wallets/{wallet_id}/benchmark/daily", responses=NOT_FOUND | INVALID)
    def benchmark_daily(wallet_id: UUID) -> BenchmarkResponse:
        """What the wallet's deposits and withdrawals would be worth in SPY instead, at the end of every day from its
        first operation to today, with SPY's dividends reinvested after the wallet's withholding tax."""
        try:
            benchmark = comparison.benchmark_daily(wallet_id)
        except DomainError as error:
            raise rule_violation(error) from error
        if benchmark is None:
            raise wallet_not_found()
        return BenchmarkResponse.from_benchmark(benchmark)

    return router
