"""Importing DEGIRO's CSV exports (Transactions and Account, in French) into a wallet.

Each test writes the rows of one kind of operation in DEGIRO's exact format, then checks how they are read and what
the wallet holds after importing them.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from shadowfolio.adapters.degiro_statements import DegiroStatementReader
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.domain.imports import ImportKind, ImportRecord
from shadowfolio.domain.money import Currency
from shadowfolio.domain.wallet import Wallet
from shadowfolio.usecases.history import History
from shadowfolio.usecases.imports import ImportReport, Imports
from shadowfolio.usecases.sync import Sync
from shadowfolio.usecases.wallets import Wallets

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
# The first line of each export, exactly as DEGIRO writes it.
TRANSACTIONS_HEADER = (
    "Date,Heure,Produit,Code ISIN,Place boursière sectionnée,Lieu d'exécution,Quantité,Cours,,Montant devise locale,,"
    "Montant EUR,Taux de change,Frais conversion AutoFX,Frais de courtage et/ou de parties,Montant négocié EUR,ID Ordre"
)
ACCOUNT_HEADER = "Date,Heure,Date de,Produit,Code ISIN,Description,FX,Mouvements,,Solde,,ID Ordre"


@dataclass(frozen=True)
class Imported:
    records: list[ImportRecord]
    report: ImportReport
    wallet: Wallet


def import_degiro(transactions: list[str], account: list[str]) -> Imported:
    """Read the exports with these rows (newest first, as DEGIRO lists them) and import them into a new EUR wallet."""
    repo, clock, fx_rates = InMemoryWalletRepository(), FixedClock(NOW), InMemoryFxRates()
    history = History(repo, clock, InMemoryPriceData(), fx_rates, Sync(repo, clock, InMemoryCorporateActions(), fx_rates))
    wallets = Wallets(repo, clock)
    wallet = wallets.create("owner", "DEGIRO", Currency.EUR, Decimal(0))

    records = DegiroStatementReader().read("\n".join([TRANSACTIONS_HEADER, *transactions]), "\n".join([ACCOUNT_HEADER, *account]))
    report = Imports(history).apply(wallet.id, records)

    imported = wallets.get(wallet.id)
    assert imported is not None
    return Imported(records, report, imported)


def test_exports_without_rows_import_nothing() -> None:
    imported = import_degiro(transactions=[], account=[])

    assert imported.records == []
    assert (imported.wallet.cash, imported.wallet.holdings, imported.wallet.operations) == (Decimal(0), {}, ())


@pytest.mark.parametrize("description", ["Dépôt flatex", "Versement de fonds"])
def test_a_deposit_adds_its_amount_to_the_cash(description: str) -> None:
    imported = import_degiro(transactions=[], account=[f'01-06-2024,15:32,01-06-2024,,,{description},,EUR,"500,00",EUR,"500,00",'])

    # DEGIRO writes Paris time: 15:32 in summer is 13:32 UTC.
    assert imported.records == [
        ImportRecord(ImportKind.DEPOSIT, datetime(2024, 6, 1, 13, 32, tzinfo=UTC), Decimal("500.00"), "EUR", description)
    ]
    assert imported.wallet.cash == Decimal("500.00")


@pytest.mark.parametrize("description", ["Retrait flatex", "Retrait instantané SEPA"])
def test_a_withdrawal_takes_its_amount_from_the_cash(description: str) -> None:
    imported = import_degiro(
        transactions=[],
        account=[
            f'07-10-2025,14:11,07-10-2025,,,{description},,EUR,"-200,00",EUR,"300,00",',
            '01-06-2024,15:32,01-06-2024,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
        ],
    )

    assert imported.records[-1] == ImportRecord(
        ImportKind.WITHDRAWAL, datetime(2025, 10, 7, 12, 11, tzinfo=UTC), Decimal("200.00"), "EUR", description
    )
    assert imported.wallet.cash == Decimal("300.00")


def test_a_row_the_import_does_not_know_is_reported_and_changes_nothing() -> None:
    imported = import_degiro(transactions=[], account=['02-10-2026,07:48,01-10-2026,,,Something new,,EUR,"1,00",EUR,"1,00",'])

    assert [(problem.record.description, problem.reason) for problem in imported.report.not_imported] == [("Something new", "unknown row")]
    assert imported.wallet.operations == ()
