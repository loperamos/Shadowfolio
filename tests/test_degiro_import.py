"""Importing DEGIRO's CSV exports (Transactions and Account, in French) into a wallet.

Each test writes the rows of one kind of operation in DEGIRO's exact format, then checks how they are read and what
the wallet holds after importing them.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from shadowfolio.adapters.degiro_statements import DegiroStatementReader
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.domain.corporate_actions import DividendEvent, SplitEvent
from shadowfolio.domain.imports import ImportKind, ImportRecord
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.operations import Dividend, Fee, ImportedDividend, Income, SharesReceived
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


def import_degiro(
    transactions: list[str],
    account: list[str],
    tickers: dict[str, str] | None = None,
    corporate_actions: tuple[SplitEvent | DividendEvent, ...] = (),
    fx_rates: tuple[FxRate, ...] = (),
) -> Imported:
    """Read the exports with these rows (newest first, as DEGIRO lists them) and import them into a new EUR wallet.

    `tickers` maps each security's ISIN to its ticker, which DEGIRO's exports do not give. `corporate_actions` and
    `fx_rates` are what market data knows (the wallet applies splits and credits dividends from it automatically).
    """
    repo, clock, rates = InMemoryWalletRepository(), FixedClock(NOW), InMemoryFxRates(*fx_rates)
    sync = Sync(repo, clock, InMemoryCorporateActions(*corporate_actions), rates)
    history = History(repo, clock, InMemoryPriceData(), rates, sync)
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


DEPOSIT_500 = '01-09-2026,10:00,01-09-2026,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",'
# NVIDIA's dividend as DEGIRO books it (newest first): 9.50 USD, less 1.43 USD of US tax and a 0.81 USD fee; the
# remaining 7.26 USD is converted the next day into 6.43 EUR.
NVIDIA_DIVIDEND = [
    '03-10-2026,06:53,02-10-2026,,,Operation de change - Crédit,,EUR,"6,43",EUR,"506,43",',
    '03-10-2026,06:53,02-10-2026,,,Opération de change - Débit,"1,1283",USD,"-7,26",USD,"0,00",',
    '02-10-2026,07:49,01-10-2026,,,Frais d’opération sur titres,,USD,"-0,81",USD,"7,26",',
    f'02-10-2026,07:48,01-10-2026,{NVIDIA},Impôts sur dividende,,USD,"-1,43",USD,"8,07",',
    f'02-10-2026,07:48,01-10-2026,{NVIDIA},Dividende,,USD,"9,50",USD,"9,50",',
]


def test_a_dividend_with_its_tax_fee_and_conversion_is_one_dividend_credited_in_euros() -> None:
    imported = import_degiro(transactions=[], account=[*NVIDIA_DIVIDEND, DEPOSIT_500], tickers=NVIDIA_TICKER)

    assert imported.records[-1] == ImportRecord(
        kind=ImportKind.DIVIDEND,
        timestamp=datetime(2026, 10, 2, 5, 48, tzinfo=UTC),
        amount=Decimal("6.43"),
        currency="EUR",
        description="NVIDIA CORPORATION",
        isin="US67066G1040",
        dividend_currency="USD",
        gross=Decimal("9.50"),
        tax=Decimal("1.43"),
        dividend_fee=Decimal("0.81"),
    )
    assert imported.report.not_imported == []
    [dividend] = [op for op in imported.wallet.operations if isinstance(op, ImportedDividend)]
    assert (dividend.symbol, dividend.currency, dividend.gross, dividend.tax, dividend.fee, dividend.amount) == (
        "NVDA",
        "USD",
        Decimal("9.50"),
        Decimal("1.43"),
        Decimal("0.81"),
        Decimal("6.43"),
    )
    assert imported.wallet.cash == Decimal("506.43")


def test_dividends_converted_together_share_the_euros_in_proportion() -> None:
    meta = '"META PLATFORMS, INC. CLASS A",US30303M1027'
    account = [
        '30-09-2026,06:50,29-09-2026,,,Operation de change - Crédit,,EUR,"9,00",EUR,"509,00",',
        '30-09-2026,06:50,29-09-2026,,,Opération de change - Débit,"1,1000",USD,"-9,90",USD,"0,00",',
        f'29-09-2026,07:30,28-09-2026,{meta},Dividende,,USD,"3,30",USD,"9,90",',
        f'29-09-2026,07:30,28-09-2026,{NVIDIA},Dividende,,USD,"6,60",USD,"6,60",',
        DEPOSIT_500,
    ]

    imported = import_degiro(transactions=[], account=account, tickers={**NVIDIA_TICKER, "US30303M1027": "META"})

    credited = {op.symbol: op.amount for op in imported.wallet.operations if isinstance(op, ImportedDividend)}
    assert credited == {"NVDA": Decimal("6.00"), "META": Decimal("3.00")}
    assert imported.wallet.cash == Decimal("509.00")


def test_a_dividend_in_hong_kong_dollars_without_tax() -> None:
    tencent = "TENCENT HOLDINGS LIMITED,KYG875721634"
    account = [
        '07-06-2023,07:32,06-06-2023,,,Operation de change - Crédit,,EUR,"3,09",EUR,"503,09",',
        '07-06-2023,07:32,06-06-2023,,,Opération de change - Débit,"8,3977",HKD,"-25,92",HKD,"0,00",',
        '06-06-2023,07:17,05-06-2023,,,Frais d’opération sur titres,,HKD,"-2,88",HKD,"25,92",',
        f'06-06-2023,07:17,05-06-2023,{tencent},Dividende,,HKD,"28,80",HKD,"28,80",',
        '01-06-2023,10:00,01-06-2023,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={"KYG875721634": "0700.HK"})

    [dividend] = [op for op in imported.wallet.operations if isinstance(op, ImportedDividend)]
    assert (dividend.currency, dividend.gross, dividend.tax, dividend.fee, dividend.amount) == (
        "HKD",  # only shown: wallets and prices are not in Hong Kong dollars
        Decimal("28.80"),
        Decimal(0),
        Decimal("2.88"),
        Decimal("3.09"),
    )


def test_an_imported_dividend_replaces_the_one_credited_from_market_data() -> None:
    # Market data knows NVIDIA's dividend paid on 1 October; DEGIRO books it the next day, with its real tax and fee.
    paid = DividendEvent("NVDA", date(2026, 9, 11), date(2026, 10, 1), Decimal("0.01"), Currency.USD, "nvda-2026-10")
    rate = FxRate(Currency.USD, Currency.EUR, Decimal("0.90"), date(2026, 10, 1))

    imported = import_degiro(
        transactions=[NVIDIA_BUY],
        account=[*NVIDIA_DIVIDEND, DEPOSIT_1000],
        tickers=NVIDIA_TICKER,
        corporate_actions=(paid,),
        fx_rates=(rate,),
    )

    assert [op for op in imported.wallet.operations if isinstance(op, Dividend)] == []
    assert imported.wallet.cash == Decimal("96.75")  # 90.32 after the buy, + 6.43 from DEGIRO's dividend only


def test_an_exchange_connection_fee_is_a_fee_taken_from_the_cash() -> None:
    description = "Frais de connexion aux places boursières 2026 (New York Stock Exchange - NSY)"
    fee = f'23-02-2026,10:47,31-01-2026,,,{description},,EUR,"-2,50",EUR,"497,50",'

    imported = import_degiro(transactions=[], account=[fee, DEPOSIT_500.replace("01-09-2026", "01-01-2026")])

    assert imported.records[-1].kind is ImportKind.FEE
    [taken] = [op for op in imported.wallet.operations if isinstance(op, Fee)]
    assert (taken.amount, taken.description) == (Decimal("2.50"), description)
    assert imported.wallet.cash == Decimal("497.50")


def test_interest_and_compensations_are_income_and_charged_interest_is_negative() -> None:
    account = [
        '26-10-2026,00:30,26-10-2026,,,Compensation Fonds Monétaires DEGIRO,,EUR,"8,89",EUR,"508,88",',
        '06-10-2026,06:52,30-09-2026,,,Flatex Interest Income,,EUR,"0,00",EUR,"499,99",',  # nothing paid: nothing recorded
        '01-10-2022,07:41,30-09-2022,,,Flatex Interest,,EUR,"-0,01",EUR,"499,99",',
        '01-09-2022,10:00,01-09-2022,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account)

    assert [record.kind for record in imported.records[1:]] == [ImportKind.INCOME] * 3
    income = [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)]
    assert income == [(Decimal("-0.01"), "Flatex Interest"), (Decimal("8.89"), "Compensation Fonds Monétaires DEGIRO")]
    assert imported.wallet.cash == Decimal("508.88")


def test_a_split_comes_from_market_data_and_its_statement_rows_are_skipped() -> None:
    # 2 NVIDIA bought before the 10-for-1 split of 10 June 2024; DEGIRO books the split as a sale of the 2 old shares
    # and a purchase of 20 new ones, with no order ID and no money moving.
    buy = f'01-05-2024,16:00,{NVIDIA},NDQ,XNAS,2,"900,0000",USD,"-1800,00",USD,"-1680,00","1,0714","-4,20","-2,00","-1686,20",order-4'
    split = [
        f'10-06-2024,00:00,{NVIDIA},NDQ,,20,"120,8880",USD,"-2417,76",USD,"-2245,95","1,0765","0,00",,"-2245,95",',
        f'10-06-2024,00:00,{NVIDIA},NDQ,,-2,"1208,8800",USD,"2417,76",USD,"2245,95","1,0765","0,00",,"2245,95",',
    ]
    split_cash = [
        f'10-06-2024,10:52,10-06-2024,{NVIDIA},"Ajustement fractionnement: 20 NVIDIA Corporation @ 120,888 USD (US67066G1040)",,'
        'USD,"-2417,76",USD,"0,00",',
        f'10-06-2024,10:52,10-06-2024,{NVIDIA},"Ajustement fractionnement: 2 NVIDIA Corporation @ 1208,88 USD (US67066G1040)",,'
        'USD,"2417,76",USD,"2417,76",',
    ]
    deposit = '20-04-2024,10:00,20-04-2024,,,Dépôt flatex,,EUR,"2000,00",EUR,"2000,00",'
    ten_for_one = SplitEvent("NVDA", date(2024, 6, 10), Decimal(1), Decimal(10), "nvda-split-2024")

    imported = import_degiro(
        transactions=[*split, buy], account=[*split_cash, deposit], tickers=NVIDIA_TICKER, corporate_actions=(ten_for_one,)
    )

    assert [record.kind for record in imported.records].count(ImportKind.SPLIT) == 4
    assert imported.report.not_imported == []
    assert imported.wallet.holdings == {"NVDA": Decimal(20)}
    assert imported.wallet.cash == Decimal("313.80")  # 2000 - 1680.00 - 6.20


TENCENT = "TENCENT HOLDINGS LIMITED,KYG875721634"
TENCENT_BUY = f'31-01-2022,08:01,{TENCENT},TDG,XGAT,12,"45,0000",EUR,"-540,00",EUR,"-540,00","1,0000","0,00","-3,90","-543,90",order-5'
DEPOSIT_600 = '20-01-2022,10:00,20-01-2022,,,Dépôt flatex,,EUR,"600,00",EUR,"600,00",'
# Tencent handed its shareholders Meituan shares: 1 for the 12 Tencent held, first as a temporary "non tradeable" line.
MEITUAN_SPIN_OFF = '05-01-2023,00:00,MEITUAN - NON TRADEABLE,KYG596691041,DEG,,1,"0,0000",EUR,"0,00",EUR,"0,00","1,0000","0,00",,"0,00",'
MEITUAN_SPIN_OFF_NOTICE = (
    "05-01-2023,07:52,05-01-2023,MEITUAN - NON TRADEABLE,KYG596691041,Spin-off: Achat 1 Meituan - Non tradeable@0 EUR (KYG596691041),,"
    'EUR,"0,00",EUR,"56,10",'
)
TENCENT_TICKERS = {"KYG875721634": "0700.HK", "KYG596691041": "3690.HK"}


def test_shares_received_in_a_spin_off_are_added_at_no_cost() -> None:
    imported = import_degiro(
        transactions=[MEITUAN_SPIN_OFF, TENCENT_BUY], account=[MEITUAN_SPIN_OFF_NOTICE, DEPOSIT_600], tickers=TENCENT_TICKERS
    )

    assert ImportKind.SPIN_OFF in [record.kind for record in imported.records]
    assert imported.report.not_imported == []
    [received] = [op for op in imported.wallet.operations if isinstance(op, SharesReceived)]
    assert (received.symbol, received.quantity) == ("3690.HK", Decimal(1))
    assert imported.wallet.holdings == {"0700.HK": Decimal(12), "3690.HK": Decimal(1)}
    assert imported.wallet.ledger.positions["3690.HK"].cost == Decimal(0)  # DEGIRO gives it no cost
    assert imported.wallet.cash == Decimal("56.10")


def test_a_spin_off_that_gives_no_whole_share_records_nothing() -> None:
    # 1 IBM share entitled to 0.2 Kyndryl shares: DEGIRO delivers none (the fraction is paid in cash, later).
    kyndryl = '"KYNDRYL HOLDINGS, INC.",US50155Q1004'
    spin_off = f'04-11-2021,00:00,{kyndryl},NSY,,0,"0,0000",USD,"0,00",USD,"0,00","1,1738","0,00",,"0,00",'
    notice = (
        f'04-11-2021,13:55,04-11-2021,{kyndryl},"Spin-off: Achat 0 Kyndryl Holdings, Inc.@0 USD (US50155Q1004)",,USD,"0,00",USD,"0,00",'
    )

    imported = import_degiro(transactions=[spin_off], account=[notice], tickers={"US50155Q1004": "KD"})

    assert imported.report.not_imported == []
    assert imported.wallet.operations == ()


# The temporary Meituan line moved to a placeholder identifier, then became tradable Meituan shares: each move is
# booked as a sale and a purchase of the same share at the same price, with no order ID.
MEITUAN_ISIN_CHANGES = [
    '27-03-2023,08:44,MEITUAN - NON TRADEABLE,RCC188527108,DEG,,-1,"17,0520",EUR,"17,05",EUR,"17,05","1,0000","0,00",,"17,05",',
    '27-03-2023,08:44,MEITUAN,KYG596691041,TDG,,1,"17,0520",EUR,"-17,05",EUR,"-17,05","1,0000","0,00",,"-17,05",',
]
MEITUAN_ISIN_CHANGE_NOTICES = [
    '27-03-2023,08:44,27-03-2023,MEITUAN - NON TRADEABLE,RCC188527108,"Changement ISIN: Vente 1 Meituan - Non tradeable@17,052 EUR '
    '(RCC188527108)",,EUR,"17,05",EUR,"73,15",',
    '27-03-2023,08:44,27-03-2023,MEITUAN,KYG596691041,"Changement ISIN: Achat 1 Meituan@17,052 EUR (KYG596691041)",,EUR,"-17,05",'
    'EUR,"56,10",',
]


def test_an_isin_change_within_the_same_ticker_changes_nothing() -> None:
    imported = import_degiro(
        transactions=[*MEITUAN_ISIN_CHANGES, MEITUAN_SPIN_OFF, TENCENT_BUY],
        account=[*MEITUAN_ISIN_CHANGE_NOTICES, MEITUAN_SPIN_OFF_NOTICE, DEPOSIT_600],
        tickers={**TENCENT_TICKERS, "RCC188527108": "3690.HK"},
    )

    assert [record.kind for record in imported.records].count(ImportKind.ISIN_CHANGE) == 2
    assert imported.report.not_imported == []
    assert imported.wallet.holdings == {"0700.HK": Decimal(12), "3690.HK": Decimal(1)}
    assert imported.wallet.cash == Decimal("56.10")


def test_an_isin_change_to_another_ticker_is_reported() -> None:
    imported = import_degiro(
        transactions=[*MEITUAN_ISIN_CHANGES, MEITUAN_SPIN_OFF, TENCENT_BUY],
        account=[*MEITUAN_ISIN_CHANGE_NOTICES, MEITUAN_SPIN_OFF_NOTICE, DEPOSIT_600],
        tickers={**TENCENT_TICKERS, "RCC188527108": "MEITUAN-TEMP"},
    )

    assert {problem.reason for problem in imported.report.not_imported} == {"an ISIN change to another ticker is not imported yet"}


def test_cash_for_a_fraction_of_a_share_in_euros_is_income() -> None:
    # Meituan paid in euros for the 0.2 share DEGIRO could not deliver.
    cash = '14-04-2023,14:24,14-04-2023,MEITUAN,KYG596691041,Règlement espèces - Action,,EUR,"3,08",EUR,"503,08",'
    deposit = '01-04-2023,10:00,01-04-2023,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",'

    imported = import_degiro(transactions=[], account=[cash, deposit], tickers=TENCENT_TICKERS)

    assert imported.records[-1].kind is ImportKind.CASH_IN_LIEU
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)] == [
        (Decimal("3.08"), "Cash for a fraction of a share of 3690.HK")
    ]
    assert imported.wallet.cash == Decimal("503.08")


def test_cash_for_a_fraction_in_dollars_is_credited_with_its_conversion() -> None:
    # 5.63 USD for IBM shareholders' fraction of a Kyndryl share, converted the next day into 4.99 EUR.
    ibm = "INTERNATIONAL BUSINESS MACHINES CORP,US4592001014"
    account = [
        '15-12-2021,07:35,14-12-2021,,,Operation de change - Crédit,,EUR,"4,99",EUR,"504,99",',
        '15-12-2021,07:35,14-12-2021,,,Opération de change - Débit,"1,1270",USD,"-5,63",USD,"0,00",',
        f'14-12-2021,09:55,09-12-2021,{ibm},Règlement espèces - Action,,USD,"5,63",USD,"5,63",',
        '01-12-2021,10:00,01-12-2021,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={"US4592001014": "IBM"})

    assert imported.report.not_imported == []
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)] == [
        (Decimal("4.99"), "Cash for a fraction of a share of IBM")
    ]
    assert imported.wallet.cash == Decimal("504.99")


def test_a_tax_listed_before_its_dividend_in_the_same_minute_still_belongs_to_it() -> None:
    # As IBM's dividend of December 2021 appears: DEGIRO lists the tax below the dividend, i.e. booked first.
    ibm = "INTERNATIONAL BUSINESS MACHINES CORP,US4592001014"
    account = [
        '14-12-2021,07:38,13-12-2021,,,Operation de change - Crédit,,EUR,"1,10",EUR,"501,10",',
        '14-12-2021,07:38,13-12-2021,,,Opération de change - Débit,"1,1297",USD,"-1,25",USD,"0,00",',
        '13-12-2021,07:46,10-12-2021,,,Frais d’opération sur titres,,USD,"-0,14",USD,"1,25",',
        f'13-12-2021,07:46,10-12-2021,{ibm},Dividende,,USD,"1,64",USD,"1,39",',
        f'13-12-2021,07:46,10-12-2021,{ibm},Impôts sur dividende,,USD,"-0,25",USD,"-0,25",',
        '01-12-2021,10:00,01-12-2021,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={"US4592001014": "IBM"})

    assert imported.report.not_imported == []
    [dividend] = [op for op in imported.wallet.operations if isinstance(op, ImportedDividend)]
    assert (dividend.gross, dividend.tax, dividend.fee, dividend.amount) == (
        Decimal("1.64"),
        Decimal("0.25"),
        Decimal("0.14"),
        Decimal("1.10"),
    )


def test_shares_subscribed_in_an_ipo_are_bought_at_the_subscription_price() -> None:
    # 2 SpaceX shares subscribed for 233.90 EUR on a temporary "non tradeable" line, which then became the listed
    # shares (an instrument change, booked like an ISIN change).
    subscription, listed = (
        "SPACEX - IPO SUBSCRIPTION - NON TRADEABLE,US0IPOSPACEX",
        "SPACE EXPLORATION TECHNOLOGIES CORP CLASS A,US84615Q1031",
    )
    transactions = [
        f'12-06-2026,13:04,{listed},NDQ,,2,"135,0000",USD,"-270,00",USD,"-232,96","1,1590","0,00",,"-232,96",',
        f'12-06-2026,13:04,{subscription},DEG,,-2,"116,6607",EUR,"233,32",EUR,"233,32","1,0000","0,00",,"233,32",',
        f'12-06-2026,00:00,{subscription},DEG,,2,"0,0000",EUR,"0,00",EUR,"0,00","1,0000","0,00",,"0,00",',
    ]
    account = [
        f'12-06-2026,13:04,12-06-2026,{listed},"Modification instrument: Achat 2 Space Exploration Technologies Corp Class A@135 USD '
        '(US84615Q1031)",,USD,"0,00",USD,"0,00",',
        f'12-06-2026,13:04,12-06-2026,{subscription},"Modification instrument: Vente 2 SpaceX - IPO Subscription - Non tradeable@116,6607 '
        'EUR (US0IPOSPACEX)",,EUR,"0,00",EUR,"266,10",',
        f"12-06-2026,12:50,12-06-2026,{subscription},Introduction en bourse: Achat 2 SpaceX - IPO Subscription - Non tradeable@0 EUR "
        '(US0IPOSPACEX),,EUR,"-233,90",EUR,"266,10",',
        '01-06-2026,10:00,01-06-2026,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=transactions, account=account, tickers={"US0IPOSPACEX": "SPCX", "US84615Q1031": "SPCX"})

    kinds = [record.kind for record in imported.records]
    assert (kinds.count(ImportKind.IPO_SUBSCRIPTION), kinds.count(ImportKind.ISIN_CHANGE)) == (1, 2)
    assert imported.report.not_imported == []
    assert imported.wallet.holdings == {"SPCX": Decimal(2)}
    assert imported.wallet.ledger.positions["SPCX"].cost == Decimal("233.90")
    assert imported.wallet.cash == Decimal("266.10")
