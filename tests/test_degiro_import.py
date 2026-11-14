"""Importing DEGIRO's CSV exports (Transactions and Account, in French) into a wallet.

Each test writes the rows of one kind of operation in DEGIRO's exact format, then checks how they are read and what
the wallet holds after importing them.
"""

from datetime import UTC, datetime
from decimal import Decimal

from shadowfolio.adapters.degiro_statements import DegiroStatementReader
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.domain.imports import ImportRecord
from shadowfolio.domain.money import Currency
from shadowfolio.domain.wallet import Wallet
from shadowfolio.usecases.history import History
from shadowfolio.usecases.imports import Imports
from shadowfolio.usecases.sync import Sync
from shadowfolio.usecases.wallets import Wallets

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
# The first line of each export, exactly as DEGIRO writes it.
TRANSACTIONS_HEADER = (
    "Date,Heure,Produit,Code ISIN,Place boursière sectionnée,Lieu d'exécution,Quantité,Cours,,Montant devise locale,,"
    "Montant EUR,Taux de change,Frais conversion AutoFX,Frais de courtage et/ou de parties,Montant négocié EUR,ID Ordre"
)
ACCOUNT_HEADER = "Date,Heure,Date de,Produit,Code ISIN,Description,FX,Mouvements,,Solde,,ID Ordre"


def import_degiro(transactions: list[str], account: list[str]) -> tuple[list[ImportRecord], Wallet]:
    """Read the exports with these rows (newest first, as DEGIRO lists them) and import them into a new EUR wallet."""
    repo, clock, fx_rates = InMemoryWalletRepository(), FixedClock(NOW), InMemoryFxRates()
    history = History(repo, clock, InMemoryPriceData(), fx_rates, Sync(repo, clock, InMemoryCorporateActions(), fx_rates))
    wallets = Wallets(repo, clock)
    wallet = wallets.create("owner", "DEGIRO", Currency.EUR, Decimal(0))

    records = DegiroStatementReader().read("\n".join([TRANSACTIONS_HEADER, *transactions]), "\n".join([ACCOUNT_HEADER, *account]))
    Imports(history).apply(wallet.id, records)

    imported = wallets.get(wallet.id)
    assert imported is not None
    return records, imported


def test_exports_without_rows_import_nothing() -> None:
    records, wallet = import_degiro(transactions=[], account=[])

    assert records == []
    assert (wallet.cash, wallet.holdings, wallet.operations) == (Decimal(0), {}, ())
