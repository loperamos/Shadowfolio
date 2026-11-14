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
# The fund DEGIRO kept spare cash in before flatex: product and ISIN cells.
FUND = "MORGAN STANLEY EUR LIQUIDITY FUND,LU1959429272"


@dataclass(frozen=True)
class Imported:
    records: list[ImportRecord]
    report: ImportReport
    wallet: Wallet


def import_degiro(transactions: list[str], account: list[str], tickers: dict[str, str] | None = None) -> Imported:
    """Read the exports with these rows (newest first, as DEGIRO lists them) and import them into a new EUR wallet.

    `tickers` maps each security's ISIN to its ticker, which DEGIRO's exports do not give.
    """
    repo, clock, fx_rates = InMemoryWalletRepository(), FixedClock(NOW), InMemoryFxRates()
    history = History(repo, clock, InMemoryPriceData(), fx_rates, Sync(repo, clock, InMemoryCorporateActions(), fx_rates))
    wallets = Wallets(repo, clock)
    wallet = wallets.create("owner", "DEGIRO", Currency.EUR, Decimal(0))

    records = DegiroStatementReader().read("\n".join([TRANSACTIONS_HEADER, *transactions]), "\n".join([ACCOUNT_HEADER, *account]))
    report = Imports(history).apply(wallet.id, records, tickers or {})

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


@pytest.mark.parametrize(
    "row",
    [
        # flatex books a processed withdrawal out and back in; the "Retrait flatex" row is the real one.
        '07-10-2025,14:11,07-10-2025,,,Processed Flatex Withdrawal,,EUR,"200,00",EUR,"500,00",',
        # Spare cash swept between DEGIRO and the flatex bank cash account, both yours.
        '09-11-2026,18:12,09-11-2026,,,Degiro Cash Sweep Transfer,,EUR,"-26,76",EUR,"473,24",',
        '09-11-2026,18:12,09-11-2026,,,"Virement vers votre Compte Espèces à la flatexDEGIRO Bank: 26,76 EUR",,,,EUR,"500,00",',
        '30-09-2026,09:41,30-09-2026,,,"Virement depuis votre Compte Espèces à la flatexDEGIRO Bank: 3,18 EUR",,,,EUR,"500,00",',
        # Before flatex (2020), DEGIRO kept spare cash in a money market fund: still cash.
        f'26-10-2020,00:00,25-10-2020,{FUND},Variation Fonds Monétaires (EUR),,EUR,"0,00",EUR,"500,00",',
        f'27-10-2020,17:50,23-10-2020,{FUND},"Conversion Fonds Monétaires finalisée: Achat 0,01 @ 0 EUR",,EUR,"99,16",EUR,"599,16",',
        f'02-09-2020,16:09,02-09-2020,{FUND},"Conversion Fonds Monétaires finalisée: Vente 0,000001 @ 9 924,6649 EUR",,,,EUR,"500,00",',
    ],
)
def test_money_moving_inside_the_broker_changes_nothing(row: str) -> None:
    deposit = '01-06-2020,15:32,01-06-2020,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",'

    imported = import_degiro(transactions=[], account=[row, deposit])

    assert imported.records[-1].kind is ImportKind.INTERNAL_TRANSFER
    assert imported.report.not_imported == []
    assert imported.wallet.cash == Decimal("500.00")


NVIDIA = "NVIDIA CORPORATION,US67066G1040"
DEPOSIT_1000 = '20-06-2024,10:00,20-06-2024,,,Dépôt flatex,,EUR,"1000,00",EUR,"1000,00",'
# A buy of 8 NVIDIA at 121.81 USD: 905.40 EUR, plus 2.28 EUR of currency conversion (AutoFX) and 2.00 EUR brokerage.
NVIDIA_BUY = f'24-06-2024,16:26,{NVIDIA},NDQ,XNAS,8,"121,8100",USD,"-974,48",USD,"-905,40","1,0763","-2,28","-2,00","-909,68",order-1'
# Its cash lines in the Account export: the same money as the trade, so they must not count again.
NVIDIA_BUY_CASH = [
    '24-06-2024,16:26,24-06-2024,,,Operation de change - Crédit,,USD,"974,48",USD,"0,00",order-1',
    '24-06-2024,16:26,24-06-2024,,,Opération de change - Débit,"1,0763",EUR,"-907,68",EUR,"92,32",order-1',
    f'24-06-2024,16:26,24-06-2024,{NVIDIA},Frais DEGIRO de courtage et/ou de parties tierces,,EUR,"-2,00",EUR,"90,32",order-1',
    f'24-06-2024,16:26,24-06-2024,{NVIDIA},"Achat 8 NVIDIA Corporation@121,81 USD (US67066G1040)",,USD,"-974,48",USD,"-974,48",order-1',
]
# A sale of 3 of them at 130 USD: 362.00 EUR, less 0.91 EUR AutoFX and 2.00 EUR brokerage.
NVIDIA_SELL = f'01-07-2024,15:40,{NVIDIA},NDQ,XNAS,-3,"130,0000",USD,"390,00",USD,"362,00","1,0773","-0,91","-2,00","359,09",order-2'
NVIDIA_TICKER = {"US67066G1040": "NVDA"}


def test_a_buy_adds_the_shares_and_takes_its_cost_and_fees_from_the_cash() -> None:
    imported = import_degiro(transactions=[NVIDIA_BUY], account=[*NVIDIA_BUY_CASH, DEPOSIT_1000], tickers=NVIDIA_TICKER)

    buy = next(record for record in imported.records if record.kind is ImportKind.BUY)
    assert (buy.timestamp, buy.isin, buy.quantity, buy.price, buy.price_currency) == (
        datetime(2024, 6, 24, 14, 26, tzinfo=UTC),
        "US67066G1040",
        Decimal(8),
        Decimal("121.81"),
        "USD",
    )
    assert (buy.amount, buy.currency, buy.fees) == (Decimal("905.40"), "EUR", Decimal("4.28"))
    assert [record.kind for record in imported.records].count(ImportKind.TRADE_SETTLEMENT) == len(NVIDIA_BUY_CASH)
    assert imported.wallet.holdings == {"NVDA": Decimal(8)}
    assert imported.wallet.cash == Decimal("90.32")  # 1000 - 905.40 - 4.28


def test_a_sale_removes_the_shares_and_adds_its_proceeds_less_fees() -> None:
    imported = import_degiro(transactions=[NVIDIA_SELL, NVIDIA_BUY], account=[DEPOSIT_1000], tickers=NVIDIA_TICKER)

    assert imported.records[-1].kind is ImportKind.SELL
    assert imported.wallet.holdings == {"NVDA": Decimal(5)}
    assert imported.wallet.cash == Decimal("449.41")  # 90.32 + 362.00 - 2.91


def test_a_trade_in_a_security_without_a_known_ticker_is_reported() -> None:
    imported = import_degiro(transactions=[NVIDIA_BUY], account=[DEPOSIT_1000])

    assert [(problem.record.isin, problem.reason) for problem in imported.report.not_imported] == [
        ("US67066G1040", "no ticker for US67066G1040")
    ]
    assert imported.wallet.holdings == {}


def test_a_trade_in_euros_on_a_european_exchange() -> None:
    # Tesla on Tradegate, in euros: no currency conversion, a flat 3.90 EUR fee.
    tesla = "TESLA INC,US88160R1014"
    buy = f'15-11-2024,14:39,{tesla},TDG,XGAT,5,"295,0500",EUR,"-1475,25",EUR,"-1475,25","1,0000","0,00","-3,90","-1479,15",order-3'
    deposit = '01-11-2024,10:00,01-11-2024,,,Dépôt flatex,,EUR,"1500,00",EUR,"1500,00",'

    imported = import_degiro(transactions=[buy], account=[deposit], tickers={"US88160R1014": "TSLA"})

    assert imported.wallet.holdings == {"TSLA": Decimal(5)}
    assert imported.wallet.cash == Decimal("20.85")  # 1500 - 1475.25 - 3.90
