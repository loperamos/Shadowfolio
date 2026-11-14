"""Importing DEGIRO's CSV exports (Transactions and Account, in French) into a wallet.

Each test writes the rows of one kind of operation in DEGIRO's exact format, then checks how they are read and what
the wallet holds after importing them.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from shadowfolio.adapters.degiro_statements import DegiroStatementReader
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.domain.corporate_actions import DividendEvent, SplitEvent
from shadowfolio.domain.imports import DividendDetails, ImportKind, ImportRecord, TradeDetails
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.operations import Dividend, Fee, ImportedDividend, Income, SharesReceived
from shadowfolio.domain.wallet import Wallet
from shadowfolio.usecases.imports import ImportReport, Imports
from shadowfolio.usecases.sync import Sync
from shadowfolio.usecases.wallet_changes import WalletChanges
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
    changes = WalletChanges(clock, InMemoryPriceData(), rates, sync)
    wallets = Wallets(repo, clock)
    wallet = wallets.create("owner", "DEGIRO", Currency.EUR, Decimal(0))

    records = DegiroStatementReader().read("\n".join([TRANSACTIONS_HEADER, *transactions]), "\n".join([ACCOUNT_HEADER, *account]))
    report = Imports(repo, changes).apply(wallet.id, records, tickers or {})
    assert report is not None

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
        '09-11-2026,18:12,09-11-2026,,,Degiro Cash Sweep Transfer,,EUR,"-25,00",EUR,"475,00",',
        '09-11-2026,18:12,09-11-2026,,,"Virement vers votre Compte Espèces à la flatexDEGIRO Bank: 25,00 EUR",,,,EUR,"500,00",',
        '30-09-2026,09:41,30-09-2026,,,"Virement depuis votre Compte Espèces à la flatexDEGIRO Bank: 3,00 EUR",,,,EUR,"500,00",',
        # Before flatex (2020), DEGIRO kept spare cash in a money market fund: moving cash in or out is still cash.
        f'27-10-2020,17:50,23-10-2020,{FUND},"Conversion Fonds Monétaires finalisée: Achat 0,01 @ 0 EUR",,EUR,"100,00",EUR,"600,00",',
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
DEPOSIT_1200 = '20-06-2024,10:00,20-06-2024,,,Dépôt flatex,,EUR,"1200,00",EUR,"1200,00",'
# A buy of 10 NVIDIA at 120 USD: 1,100.00 EUR, plus 2.75 EUR of currency conversion (AutoFX) and 2.00 EUR brokerage.
NVIDIA_BUY = f'24-06-2024,16:26,{NVIDIA},NDQ,XNAS,10,"120,0000",USD,"-1200,00",USD,"-1100,00","1,0909","-2,75","-2,00","-1104,75",order-1'
# Its cash lines in the Account export: the same money as the trade, so they must not count again.
NVIDIA_BUY_CASH = [
    '24-06-2024,16:26,24-06-2024,,,Operation de change - Crédit,,USD,"1200,00",USD,"0,00",order-1',
    '24-06-2024,16:26,24-06-2024,,,Opération de change - Débit,"1,0909",EUR,"-1102,75",EUR,"97,25",order-1',
    f'24-06-2024,16:26,24-06-2024,{NVIDIA},Frais DEGIRO de courtage et/ou de parties tierces,,EUR,"-2,00",EUR,"95,25",order-1',
    f'24-06-2024,16:26,24-06-2024,{NVIDIA},"Achat 10 NVIDIA Corporation@120 USD (US67066G1040)",,USD,"-1200,00",USD,"-1200,00",order-1',
]
# A sale of 3 of them at 130 USD: 362.00 EUR, less 0.91 EUR AutoFX and 2.00 EUR brokerage.
NVIDIA_SELL = f'01-07-2024,15:40,{NVIDIA},NDQ,XNAS,-3,"130,0000",USD,"390,00",USD,"362,00","1,0773","-0,91","-2,00","359,09",order-2'
NVIDIA_TICKER = {"US67066G1040": "NVDA"}


def test_a_buy_adds_the_shares_and_takes_its_cost_and_fees_from_the_cash() -> None:
    imported = import_degiro(transactions=[NVIDIA_BUY], account=[*NVIDIA_BUY_CASH, DEPOSIT_1200], tickers=NVIDIA_TICKER)

    buy = next(record for record in imported.records if record.kind is ImportKind.BUY)
    assert (buy.timestamp, buy.isin, buy.amount, buy.currency) == (
        datetime(2024, 6, 24, 14, 26, tzinfo=UTC),
        "US67066G1040",
        Decimal("1100.00"),
        "EUR",
    )
    assert buy.trade == TradeDetails(quantity=Decimal(10), price=Decimal("120.00"), price_currency="USD", fees=Decimal("4.75"))
    assert [record.kind for record in imported.records].count(ImportKind.TRADE_SETTLEMENT) == len(NVIDIA_BUY_CASH)
    assert imported.wallet.holdings == {"NVDA": Decimal(10)}
    assert imported.wallet.cash == Decimal("95.25")  # 1200 - 1100.00 - 4.75


def test_a_sale_removes_the_shares_and_adds_its_proceeds_less_fees() -> None:
    imported = import_degiro(transactions=[NVIDIA_SELL, NVIDIA_BUY], account=[DEPOSIT_1200], tickers=NVIDIA_TICKER)

    assert imported.records[-1].kind is ImportKind.SELL
    assert imported.wallet.holdings == {"NVDA": Decimal(7)}
    assert imported.wallet.cash == Decimal("454.34")  # 95.25 + 362.00 - 2.91


def test_a_trade_in_a_security_without_a_known_ticker_is_reported() -> None:
    imported = import_degiro(transactions=[NVIDIA_BUY], account=[DEPOSIT_1200])

    assert [(problem.record.isin, problem.reason) for problem in imported.report.not_imported] == [
        ("US67066G1040", "no ticker for US67066G1040")
    ]
    assert imported.wallet.holdings == {}


def test_a_trade_in_euros_on_a_european_exchange() -> None:
    # Tesla on Tradegate, in euros: no currency conversion, a flat 3.90 EUR fee.
    tesla = "TESLA INC,US88160R1014"
    buy = f'15-11-2024,14:39,{tesla},TDG,XGAT,4,"300,0000",EUR,"-1200,00",EUR,"-1200,00","1,0000","0,00","-3,90","-1203,90",order-3'
    deposit = '01-11-2024,10:00,01-11-2024,,,Dépôt flatex,,EUR,"1500,00",EUR,"1500,00",'

    imported = import_degiro(transactions=[buy], account=[deposit], tickers={"US88160R1014": "TSLA"})

    assert imported.wallet.holdings == {"TSLA": Decimal(4)}
    assert imported.wallet.cash == Decimal("296.10")  # 1500 - 1200.00 - 3.90


DEPOSIT_500 = '01-09-2026,10:00,01-09-2026,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",'
# NVIDIA's dividend as DEGIRO books it (newest first): 10.00 USD, less 1.50 USD of US tax and a 0.80 USD fee; the
# remaining 7.70 USD is converted the next day into 7.00 EUR.
NVIDIA_DIVIDEND = [
    '03-10-2026,06:53,02-10-2026,,,Operation de change - Crédit,,EUR,"7,00",EUR,"507,00",',
    '03-10-2026,06:53,02-10-2026,,,Opération de change - Débit,"1,1000",USD,"-7,70",USD,"0,00",',
    '02-10-2026,07:49,01-10-2026,,,Frais d’opération sur titres,,USD,"-0,80",USD,"7,70",',
    f'02-10-2026,07:48,01-10-2026,{NVIDIA},Impôts sur dividende,,USD,"-1,50",USD,"8,50",',
    f'02-10-2026,07:48,01-10-2026,{NVIDIA},Dividende,,USD,"10,00",USD,"10,00",',
]


def test_a_dividend_with_its_tax_fee_and_conversion_is_one_dividend_credited_in_euros() -> None:
    imported = import_degiro(transactions=[], account=[*NVIDIA_DIVIDEND, DEPOSIT_500], tickers=NVIDIA_TICKER)

    assert imported.records[-1] == ImportRecord(
        kind=ImportKind.DIVIDEND,
        timestamp=datetime(2026, 10, 2, 5, 48, tzinfo=UTC),
        amount=Decimal("7.00"),
        currency="EUR",
        description="NVIDIA CORPORATION",
        isin="US67066G1040",
        dividend=DividendDetails(
            currency="USD", gross=Decimal("10.00"), tax=Decimal("1.50"), fee=Decimal("0.80"), payment_date=date(2026, 10, 1)
        ),
    )
    assert imported.report.not_imported == []
    [dividend] = [op for op in imported.wallet.operations if isinstance(op, ImportedDividend)]
    assert (dividend.symbol, dividend.currency, dividend.gross, dividend.tax, dividend.fee, dividend.amount) == (
        "NVDA",
        "USD",
        Decimal("10.00"),
        Decimal("1.50"),
        Decimal("0.80"),
        Decimal("7.00"),
    )
    assert imported.wallet.cash == Decimal("507.00")


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
        '07-06-2023,07:32,06-06-2023,,,Operation de change - Crédit,,EUR,"3,18",EUR,"503,18",',
        '07-06-2023,07:32,06-06-2023,,,Opération de change - Débit,"8,4906",HKD,"-27,00",HKD,"0,00",',
        '06-06-2023,07:17,05-06-2023,,,Frais d’opération sur titres,,HKD,"-3,00",HKD,"27,00",',
        f'06-06-2023,07:17,05-06-2023,{tencent},Dividende,,HKD,"30,00",HKD,"30,00",',
        '01-06-2023,10:00,01-06-2023,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={"KYG875721634": "0700.HK"})

    [dividend] = [op for op in imported.wallet.operations if isinstance(op, ImportedDividend)]
    assert (dividend.currency, dividend.gross, dividend.tax, dividend.fee, dividend.amount) == (
        "HKD",  # only shown: wallets and prices are not in Hong Kong dollars
        Decimal("30.00"),
        Decimal(0),
        Decimal("3.00"),
        Decimal("3.18"),
    )


def test_an_imported_dividend_replaces_the_one_credited_from_market_data() -> None:
    # Market data knows NVIDIA's dividend paid on 1 October; DEGIRO books it the next day, with its real tax and fee.
    paid = DividendEvent("NVDA", date(2026, 9, 11), date(2026, 10, 1), Decimal("0.01"), Currency.USD, "nvda-2026-10")
    rate = FxRate(Currency.USD, Currency.EUR, Decimal("0.90"), date(2026, 10, 1))

    imported = import_degiro(
        transactions=[NVIDIA_BUY],
        account=[*NVIDIA_DIVIDEND, DEPOSIT_1200],
        tickers=NVIDIA_TICKER,
        corporate_actions=(paid,),
        fx_rates=(rate,),
    )

    assert [op for op in imported.wallet.operations if isinstance(op, Dividend)] == []
    assert imported.wallet.cash == Decimal("102.25")  # 95.25 after the buy, + 7.00 from DEGIRO's dividend only


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
        '26-10-2026,00:30,26-10-2026,,,Compensation Fonds Monétaires DEGIRO,,EUR,"5,00",EUR,"504,99",',
        '06-10-2026,06:52,30-09-2026,,,Flatex Interest Income,,EUR,"0,00",EUR,"499,99",',  # nothing paid: nothing recorded
        '01-10-2022,07:41,30-09-2022,,,Flatex Interest,,EUR,"-0,01",EUR,"499,99",',
        '01-09-2022,10:00,01-09-2022,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account)

    assert [record.kind for record in imported.records[1:]] == [ImportKind.INCOME] * 3
    income = [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)]
    assert income == [(Decimal("-0.01"), "Flatex Interest"), (Decimal("5.00"), "Compensation Fonds Monétaires DEGIRO")]
    assert imported.wallet.cash == Decimal("504.99")


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
TENCENT_BUY = f'31-01-2022,08:01,{TENCENT},TDG,XGAT,20,"40,0000",EUR,"-800,00",EUR,"-800,00","1,0000","0,00","-3,90","-803,90",order-5'
DEPOSIT_900 = '20-01-2022,10:00,20-01-2022,,,Dépôt flatex,,EUR,"900,00",EUR,"900,00",'
# Tencent handed its shareholders Meituan shares: here 1, first as a temporary "non tradeable" line.
MEITUAN_SPIN_OFF = '05-01-2023,00:00,MEITUAN - NON TRADEABLE,KYG596691041,DEG,,1,"0,0000",EUR,"0,00",EUR,"0,00","1,0000","0,00",,"0,00",'
MEITUAN_SPIN_OFF_NOTICE = (
    "05-01-2023,07:52,05-01-2023,MEITUAN - NON TRADEABLE,KYG596691041,Spin-off: Achat 1 Meituan - Non tradeable@0 EUR (KYG596691041),,"
    'EUR,"0,00",EUR,"96,10",'
)
TENCENT_TICKERS = {"KYG875721634": "0700.HK", "KYG596691041": "3690.HK"}


def test_shares_received_in_a_spin_off_are_added_at_no_cost() -> None:
    imported = import_degiro(
        transactions=[MEITUAN_SPIN_OFF, TENCENT_BUY], account=[MEITUAN_SPIN_OFF_NOTICE, DEPOSIT_900], tickers=TENCENT_TICKERS
    )

    assert ImportKind.SPIN_OFF in [record.kind for record in imported.records]
    assert imported.report.not_imported == []
    [received] = [op for op in imported.wallet.operations if isinstance(op, SharesReceived)]
    assert (received.symbol, received.quantity) == ("3690.HK", Decimal(1))
    assert imported.wallet.holdings == {"0700.HK": Decimal(20), "3690.HK": Decimal(1)}
    assert imported.wallet.ledger.positions["3690.HK"].cost == Decimal(0)  # DEGIRO gives it no cost
    assert imported.wallet.cash == Decimal("96.10")


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
    '(RCC188527108)",,EUR,"17,05",EUR,"113,15",',
    '27-03-2023,08:44,27-03-2023,MEITUAN,KYG596691041,"Changement ISIN: Achat 1 Meituan@17,052 EUR (KYG596691041)",,EUR,"-17,05",'
    'EUR,"96,10",',
]


def test_an_isin_change_within_the_same_ticker_changes_nothing() -> None:
    imported = import_degiro(
        transactions=[*MEITUAN_ISIN_CHANGES, MEITUAN_SPIN_OFF, TENCENT_BUY],
        account=[*MEITUAN_ISIN_CHANGE_NOTICES, MEITUAN_SPIN_OFF_NOTICE, DEPOSIT_900],
        tickers={**TENCENT_TICKERS, "RCC188527108": "3690.HK"},
    )

    assert [record.kind for record in imported.records].count(ImportKind.ISIN_CHANGE) == 2
    assert imported.report.not_imported == []
    assert imported.wallet.holdings == {"0700.HK": Decimal(20), "3690.HK": Decimal(1)}
    assert imported.wallet.cash == Decimal("96.10")


def test_an_isin_change_to_another_ticker_is_reported() -> None:
    imported = import_degiro(
        transactions=[*MEITUAN_ISIN_CHANGES, MEITUAN_SPIN_OFF, TENCENT_BUY],
        account=[*MEITUAN_ISIN_CHANGE_NOTICES, MEITUAN_SPIN_OFF_NOTICE, DEPOSIT_900],
        tickers={**TENCENT_TICKERS, "RCC188527108": "MEITUAN-TEMP"},
    )

    assert {problem.reason for problem in imported.report.not_imported} == {"an ISIN change to another ticker is not imported yet"}


def test_cash_for_a_fraction_of_a_share_in_euros_is_income() -> None:
    # Meituan paid in euros for the fraction of a share DEGIRO could not deliver.
    cash = '14-04-2023,14:24,14-04-2023,MEITUAN,KYG596691041,Règlement espèces - Action,,EUR,"2,50",EUR,"502,50",'
    deposit = '01-04-2023,10:00,01-04-2023,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",'

    imported = import_degiro(transactions=[], account=[cash, deposit], tickers=TENCENT_TICKERS)

    assert imported.records[-1].kind is ImportKind.CASH_IN_LIEU
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)] == [
        (Decimal("2.50"), "Cash for a fraction of a share of 3690.HK")
    ]
    assert imported.wallet.cash == Decimal("502.50")


def test_cash_for_a_fraction_in_dollars_is_credited_with_its_conversion() -> None:
    # 6.00 USD for IBM shareholders' fraction of a Kyndryl share, converted the next day into 5.40 EUR.
    ibm = "INTERNATIONAL BUSINESS MACHINES CORP,US4592001014"
    account = [
        '15-12-2021,07:35,14-12-2021,,,Operation de change - Crédit,,EUR,"5,40",EUR,"505,40",',
        '15-12-2021,07:35,14-12-2021,,,Opération de change - Débit,"1,1111",USD,"-6,00",USD,"0,00",',
        f'14-12-2021,09:55,09-12-2021,{ibm},Règlement espèces - Action,,USD,"6,00",USD,"6,00",',
        '01-12-2021,10:00,01-12-2021,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={"US4592001014": "IBM"})

    assert imported.report.not_imported == []
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)] == [
        (Decimal("5.40"), "Cash for a fraction of a share of IBM")
    ]
    assert imported.wallet.cash == Decimal("505.40")


def test_a_tax_listed_before_its_dividend_in_the_same_minute_still_belongs_to_it() -> None:
    # As DEGIRO sometimes lists them (IBM, December 2021): the tax below the dividend, i.e. booked first.
    ibm = "INTERNATIONAL BUSINESS MACHINES CORP,US4592001014"
    account = [
        '14-12-2021,07:38,13-12-2021,,,Operation de change - Crédit,,EUR,"1,35",EUR,"501,35",',
        '14-12-2021,07:38,13-12-2021,,,Opération de change - Débit,"1,1111",USD,"-1,50",USD,"0,00",',
        '13-12-2021,07:46,10-12-2021,,,Frais d’opération sur titres,,USD,"-0,20",USD,"1,50",',
        f'13-12-2021,07:46,10-12-2021,{ibm},Dividende,,USD,"2,00",USD,"1,70",',
        f'13-12-2021,07:46,10-12-2021,{ibm},Impôts sur dividende,,USD,"-0,30",USD,"-0,30",',
        '01-12-2021,10:00,01-12-2021,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={"US4592001014": "IBM"})

    assert imported.report.not_imported == []
    [dividend] = [op for op in imported.wallet.operations if isinstance(op, ImportedDividend)]
    assert (dividend.gross, dividend.tax, dividend.fee, dividend.amount) == (
        Decimal("2.00"),
        Decimal("0.30"),
        Decimal("0.20"),
        Decimal("1.35"),
    )


def test_shares_subscribed_in_an_ipo_are_bought_at_the_subscription_price() -> None:
    # 3 SpaceX shares subscribed for 300.00 EUR on a temporary "non tradeable" line, which then became the listed
    # shares (an instrument change, booked like an ISIN change).
    subscription, listed = (
        "SPACEX - IPO SUBSCRIPTION - NON TRADEABLE,US0IPOSPACEX",
        "SPACE EXPLORATION TECHNOLOGIES CORP CLASS A,US84615Q1031",
    )
    transactions = [
        f'12-06-2026,13:04,{listed},NDQ,,3,"120,0000",USD,"-360,00",USD,"-327,27","1,1000","0,00",,"-327,27",',
        f'12-06-2026,13:04,{subscription},DEG,,-3,"100,0000",EUR,"300,00",EUR,"300,00","1,0000","0,00",,"300,00",',
        f'12-06-2026,00:00,{subscription},DEG,,3,"0,0000",EUR,"0,00",EUR,"0,00","1,0000","0,00",,"0,00",',
    ]
    account = [
        f'12-06-2026,13:04,12-06-2026,{listed},"Modification instrument: Achat 3 Space Exploration Technologies Corp Class A@120 USD '
        '(US84615Q1031)",,USD,"0,00",USD,"0,00",',
        f'12-06-2026,13:04,12-06-2026,{subscription},"Modification instrument: Vente 3 SpaceX - IPO Subscription - Non tradeable@100 '
        'EUR (US0IPOSPACEX)",,EUR,"0,00",EUR,"200,00",',
        f"12-06-2026,12:50,12-06-2026,{subscription},Introduction en bourse: Achat 3 SpaceX - IPO Subscription - Non tradeable@0 EUR "
        '(US0IPOSPACEX),,EUR,"-300,00",EUR,"200,00",',
        '01-06-2026,10:00,01-06-2026,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=transactions, account=account, tickers={"US0IPOSPACEX": "SPCX", "US84615Q1031": "SPCX"})

    kinds = [record.kind for record in imported.records]
    assert (kinds.count(ImportKind.IPO_SUBSCRIPTION), kinds.count(ImportKind.ISIN_CHANGE)) == (1, 2)
    assert imported.report.not_imported == []
    assert imported.wallet.holdings == {"SPCX": Decimal(3)}
    assert imported.wallet.ledger.positions["SPCX"].cost == Decimal("300.00")
    assert imported.wallet.cash == Decimal("200.00")


def test_a_dividend_tax_refunded_later_is_income_credited_with_its_conversion() -> None:
    # As in December 2021: a cent of tax refunded on two dividends of October, converted together the next day.
    apple = "APPLE INC.,US0378331005"
    account = [
        '17-12-2021,07:37,16-12-2021,,,Operation de change - Crédit,,EUR,"0,01",EUR,"500,01",',
        '17-12-2021,07:37,16-12-2021,,,Opération de change - Débit,"1,1341",USD,"-0,02",USD,"0,00",',
        f'16-12-2021,14:41,22-10-2021,{NVIDIA},Impôts sur dividende,,USD,"0,01",USD,"0,02",',
        f'16-12-2021,14:41,22-10-2021,{apple},Impôts sur dividende,,USD,"0,01",USD,"0,01",',
        '01-12-2021,10:00,01-12-2021,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={**NVIDIA_TICKER, "US0378331005": "AAPL"})

    assert [record.kind for record in imported.records[1:]] == [ImportKind.TAX_REFUND] * 2
    assert imported.report.not_imported == []
    # The cent cannot be split in two: one refund gets it, the other is 0.00 and records nothing.
    [refund] = [op for op in imported.wallet.operations if isinstance(op, Income)]
    assert refund.amount == Decimal("0.01")
    assert refund.description in {"Dividend tax refunded on AAPL", "Dividend tax refunded on NVDA"}
    assert imported.wallet.cash == Decimal("500.01")


def test_nothing_is_saved_unless_every_record_goes_in_and_every_problem_is_reported() -> None:
    account = [
        '01-03-2026,10:00,01-03-2026,,,Something new,,EUR,"1,00",EUR,"301,00",',  # not recognised
        '01-02-2026,10:00,01-02-2026,,,Retrait flatex,,EUR,"-800,00",EUR,"-300,00",',  # more than the cash: refused
        '01-01-2026,10:00,01-01-2026,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',  # fine on its own
    ]

    imported = import_degiro(transactions=[], account=account)

    assert not imported.report.imported
    assert [(problem.record.description, problem.reason.split(" on ")[0]) for problem in imported.report.not_imported] == [
        ("Retrait flatex", "cash would be -300.00"),
        ("Something new", "unknown row"),
    ]
    assert imported.wallet.operations == ()  # not even the deposit


def test_an_import_where_every_record_goes_in_is_saved() -> None:
    imported = import_degiro(transactions=[], account=[DEPOSIT_500])

    assert imported.report.imported
    assert imported.wallet.cash == Decimal("500.00")


def test_a_fee_in_dollars_without_a_dividend_is_paid_by_converting_euros() -> None:
    # As on 22 February 2022: a 0.05 USD fee takes the dollar balance below zero, and DEGIRO converts 0.04 EUR
    # into dollars the next day to cover it.
    account = [
        '23-02-2022,07:37,22-02-2022,,,Operation de change - Crédit,"1,1328",USD,"0,05",USD,"0,00",',
        '23-02-2022,07:37,22-02-2022,,,Opération de change - Débit,,EUR,"-0,04",EUR,"499,96",',
        '22-02-2022,15:29,22-02-2022,,,Frais d’opération sur titres,,USD,"-0,05",USD,"-0,05",',
        '01-02-2022,10:00,01-02-2022,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account)

    assert imported.report.imported
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Fee)] == [
        (Decimal("0.04"), "Frais d’opération sur titres")
    ]
    assert imported.wallet.cash == Decimal("499.96")


def test_dividend_tax_charged_later_is_paid_by_converting_euros() -> None:
    # As in 2025: more tax on an earlier dividend, without the dividend; DEGIRO converts euros to cover it.
    account = [
        '04-12-2025,06:39,03-12-2025,,,Operation de change - Crédit,"1,1111",USD,"0,50",USD,"0,00",',
        '04-12-2025,06:39,03-12-2025,,,Opération de change - Débit,,EUR,"-0,45",EUR,"499,55",',
        f'03-12-2025,07:46,26-09-2025,{NVIDIA},Impôts sur dividende,,USD,"-0,50",USD,"-0,50",',
        '01-11-2025,10:00,01-11-2025,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers=NVIDIA_TICKER)

    assert imported.report.imported
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Fee)] == [
        (Decimal("0.45"), "Dividend tax charged later on NVDA")
    ]
    assert imported.wallet.cash == Decimal("499.55")


def test_a_conversion_settles_only_the_waiting_cash_it_converts() -> None:
    # As in March 2024: NVIDIA's dividend (0.80 USD after tax and fee) is converted on its own, though Waste
    # Management's (2.30 USD) is already waiting; that one is converted the next day.
    wm = "WASTE MANAGEMENT INC,US94106L1098"
    account = [
        '30-03-2024,07:08,29-03-2024,,,Operation de change - Crédit,,EUR,"2,07",EUR,"502,79",',
        '30-03-2024,07:08,29-03-2024,,,Opération de change - Débit,"1,1111",USD,"-2,30",USD,"0,00",',
        '29-03-2024,08:08,28-03-2024,,,Operation de change - Crédit,,EUR,"0,72",EUR,"500,72",',
        '29-03-2024,08:08,28-03-2024,,,Opération de change - Débit,"1,1111",USD,"-0,80",USD,"2,30",',
        '29-03-2024,07:14,28-03-2024,,,Frais d’opération sur titres,,USD,"-0,25",USD,"3,10",',
        f'29-03-2024,07:14,28-03-2024,{wm},Dividende,,USD,"3,00",USD,"3,35",',
        f'29-03-2024,07:14,28-03-2024,{wm},Impôts sur dividende,,USD,"-0,45",USD,"0,35",',
        '28-03-2024,07:41,27-03-2024,,,Frais d’opération sur titres,,USD,"-0,05",USD,"0,80",',
        f'28-03-2024,07:39,27-03-2024,{NVIDIA},Impôts sur dividende,,USD,"-0,15",USD,"0,85",',
        f'28-03-2024,07:39,27-03-2024,{NVIDIA},Dividende,,USD,"1,00",USD,"1,00",',
        '01-03-2024,10:00,01-03-2024,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={**NVIDIA_TICKER, "US94106L1098": "WM"})

    assert imported.report.imported
    credited = {op.symbol: op.amount for op in imported.wallet.operations if isinstance(op, ImportedDividend)}
    assert credited == {"NVDA": Decimal("0.72"), "WM": Decimal("2.07")}


def test_a_leftover_cent_converted_with_nothing_waiting_is_recorded_as_it_is() -> None:
    # As on 19 September 2026: a sale left -0.01 USD from rounding, and DEGIRO converted 0.01 EUR to cover it.
    account = [
        '19-09-2026,06:31,18-09-2026,,,Opération de change - Débit,,EUR,"-0,01",EUR,"499,99",',
        '19-09-2026,06:31,18-09-2026,,,Operation de change - Crédit,"1,1456",USD,"0,01",USD,"0,00",',
        DEPOSIT_500,
    ]

    imported = import_degiro(transactions=[], account=account)

    assert imported.report.imported
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)] == [
        (Decimal("-0.01"), "Leftover USD balance converted")
    ]
    assert imported.wallet.cash == Decimal("499.99")


GOOGL = "ALPHABET INC. CLASS A,US02079K3059"


def test_a_dividend_booked_and_reversed_several_times_counts_once() -> None:
    # As Alphabet's dividend of 16 March 2026 (the value date): booked four times and reversed three times, with its
    # tax and fees likewise, then converted (8.20 USD into 7.10 EUR); one fee was given back the next day.
    paid, value = "17-03-2026", "16-03-2026"
    account = [
        '19-03-2026,06:33,18-03-2026,,,Operation de change - Crédit,,EUR,"0,87",EUR,"507,97",',
        '19-03-2026,06:33,18-03-2026,,,Opération de change - Débit,"1,1494",USD,"-1,00",USD,"0,00",',
        f'18-03-2026,12:15,{value},,,Frais d’opération sur titres,,USD,"1,00",USD,"1,00",',
        '18-03-2026,06:36,17-03-2026,,,Operation de change - Crédit,,EUR,"7,10",EUR,"507,10",',
        '18-03-2026,06:36,17-03-2026,,,Opération de change - Débit,"1,1549",USD,"-8,20",USD,"0,00",',
        f'{paid},08:10,{value},{GOOGL},Impôts sur dividende,,USD,"1,80",USD,"8,20",',
        f'{paid},08:10,{value},{GOOGL},Dividende,,USD,"-12,00",USD,"6,40",',
        f'{paid},07:51,{value},,,Frais d’opération sur titres,,USD,"-1,00",USD,"18,40",',
        f'{paid},07:50,{value},{GOOGL},Impôts sur dividende,,USD,"-1,80",USD,"19,40",',
        f'{paid},07:48,{value},{GOOGL},Dividende,,USD,"12,00",USD,"21,20",',
        f'{paid},07:47,{value},,,Frais d’opération sur titres,,USD,"-1,00",USD,"9,20",',
        f'{paid},07:46,{value},,,Frais d’opération sur titres,,USD,"1,00",USD,"10,20",',
        f'{paid},07:45,{value},{GOOGL},Dividende,,USD,"12,00",USD,"9,20",',
        f'{paid},07:45,{value},{GOOGL},Impôts sur dividende,,USD,"-1,80",USD,"-2,80",',
        f'{paid},07:44,{value},{GOOGL},Dividende,,USD,"12,00",USD,"-1,00",',
        f'{paid},07:44,{value},{GOOGL},Impôts sur dividende,,USD,"-1,80",USD,"-13,00",',
        f'{paid},07:39,{value},{GOOGL},Impôts sur dividende,,USD,"1,80",USD,"-11,20",',
        f'{paid},07:39,{value},{GOOGL},Dividende,,USD,"-12,00",USD,"-13,00",',
        f'{paid},07:39,{value},{GOOGL},Dividende,,USD,"-12,00",USD,"-1,00",',
        f'{paid},07:39,{value},{GOOGL},Impôts sur dividende,,USD,"1,80",USD,"11,00",',
        f'{paid},07:39,{value},,,Frais d’opération sur titres,,USD,"-1,00",USD,"9,20",',
        f'{paid},07:28,{value},{GOOGL},Impôts sur dividende,,USD,"-1,80",USD,"10,20",',
        f'{paid},07:26,{value},{GOOGL},Dividende,,USD,"12,00",USD,"12,00",',
        '01-03-2026,10:00,01-03-2026,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={"US02079K3059": "GOOGL"})

    assert imported.report.imported
    [dividend] = [op for op in imported.wallet.operations if isinstance(op, ImportedDividend)]
    assert (dividend.gross, dividend.tax, dividend.fee, dividend.amount) == (
        Decimal("12.00"),
        Decimal("1.80"),
        Decimal("2.00"),
        Decimal("7.10"),
    )
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)] == [
        (Decimal("0.87"), "Frais d’opération sur titres (given back)")
    ]
    assert imported.wallet.cash == Decimal("507.97")


def test_a_dividend_reversed_and_booked_again_counts_once() -> None:
    # As Microsoft's September 2025 dividend in December: reversed (covered by converting euros), then booked again.
    msft, value = "MICROSOFT CORPORATION,US5949181045", "11-09-2025"
    account = [
        '05-12-2025,06:44,04-12-2025,,,Operation de change - Crédit,,EUR,"0,77",EUR,"500,00",',
        '05-12-2025,06:44,04-12-2025,,,Opération de change - Débit,"1,1039",USD,"-0,85",USD,"0,00",',
        f'04-12-2025,08:18,{value},,,Frais d’opération sur titres,,USD,"-0,10",USD,"0,85",',
        f'04-12-2025,08:15,{value},{msft},Impôts sur dividende,,USD,"-0,15",USD,"0,95",',
        f'04-12-2025,08:15,{value},{msft},Dividende,,USD,"1,00",USD,"1,10",',
        f'04-12-2025,08:14,{value},,,Frais d’opération sur titres,,USD,"0,10",USD,"0,10",',
        '04-12-2025,06:39,03-12-2025,,,Opération de change - Débit,,EUR,"-0,77",EUR,"499,23",',
        '04-12-2025,06:39,03-12-2025,,,Operation de change - Crédit,"1,1039",USD,"0,85",USD,"0,00",',
        f'03-12-2025,18:07,{value},{msft},Impôts sur dividende,,USD,"0,15",USD,"-0,85",',
        f'03-12-2025,18:05,{value},{msft},Dividende,,USD,"-1,00",USD,"-1,00",',
        '01-12-2025,10:00,01-12-2025,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account, tickers={"US5949181045": "MSFT"})

    assert imported.report.imported
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)] == [
        (Decimal("-0.77"), "Dividend of MSFT reversed")
    ]
    assert [op.amount for op in imported.wallet.operations if isinstance(op, ImportedDividend)] == [Decimal("0.77")]
    assert imported.wallet.cash == Decimal("500.00")


def test_value_changes_of_the_cash_fund_are_income() -> None:
    # In 2020 DEGIRO parked spare cash in a money market fund whose value fell by a few cents most days (negative
    # rates). Moving cash into or out of it changes nothing; its value changes are income, here negative.
    account = [
        f'27-10-2020,17:50,23-10-2020,{FUND},"Conversion Fonds Monétaires finalisée: Achat 0,01 @ 0 EUR",,EUR,"99,16",EUR,"599,13",',
        f'27-10-2020,17:50,23-10-2020,{FUND},"Conversion Fonds Monétaires finalisée: Vente 0,01 @ 0 EUR",,EUR,"-99,16",EUR,"499,97",',
        f'26-10-2020,00:00,25-10-2020,{FUND},Variation Fonds Monétaires (EUR),,EUR,"0,00",EUR,"499,97",',
        f'02-06-2020,00:00,01-06-2020,{FUND},Variation Fonds Monétaires (EUR),,EUR,"-0,03",EUR,"499,97",',
        '01-06-2020,10:00,01-06-2020,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(transactions=[], account=account)

    assert imported.report.imported
    assert [(op.amount, op.description) for op in imported.wallet.operations if isinstance(op, Income)] == [
        (Decimal("-0.03"), "Variation Fonds Monétaires (EUR)")
    ]
    assert imported.wallet.cash == Decimal("499.97")


def test_a_trade_in_a_currency_wallets_do_not_use_is_reported_and_nothing_is_saved() -> None:
    hkd_buy = (
        f'31-01-2022,03:00,{TENCENT},HKS,XHKG,100,"450,0000",HKD,"-45000,00",HKD,"-5180,00","8,6870","-12,95","-3,00","-5195,95",order-6'
    )
    deposit = '01-01-2022,10:00,01-01-2022,,,Dépôt flatex,,EUR,"6000,00",EUR,"6000,00",'

    imported = import_degiro(transactions=[hkd_buy], account=[deposit], tickers=TENCENT_TICKERS)

    assert [problem.reason for problem in imported.report.not_imported] == ["prices in HKD are not supported"]
    assert imported.wallet.operations == ()


def test_importing_into_a_wallet_that_does_not_exist_imports_nothing() -> None:
    repo, clock, rates = InMemoryWalletRepository(), FixedClock(NOW), InMemoryFxRates()
    changes = WalletChanges(clock, InMemoryPriceData(), rates, Sync(repo, clock, InMemoryCorporateActions(), rates))
    records = DegiroStatementReader().read(TRANSACTIONS_HEADER, "\n".join([ACCOUNT_HEADER, DEPOSIT_500]))

    assert Imports(repo, changes).apply(uuid4(), records, {}) is None


def test_a_dividend_booked_just_after_midnight_still_replaces_the_automatic_one() -> None:
    # Booked at 00:30 in Paris on its payment day, which is still the day before in UTC: matched by the payment date
    # DEGIRO prints (the value date), not by when it was booked.
    paid = DividendEvent("NVDA", date(2026, 9, 11), date(2026, 10, 1), Decimal("0.01"), Currency.USD, "nvda-2026-10")
    rate = FxRate(Currency.USD, Currency.EUR, Decimal("0.90"), date(2026, 10, 1))
    dividend = [
        '02-10-2026,06:53,01-10-2026,,,Operation de change - Crédit,,EUR,"6,95",EUR,"102,20",',
        '02-10-2026,06:53,01-10-2026,,,Opération de change - Débit,"1,1007",USD,"-7,65",USD,"0,00",',
        f'01-10-2026,00:30,01-10-2026,{NVIDIA},Impôts sur dividende,,USD,"-1,35",USD,"7,65",',
        f'01-10-2026,00:30,01-10-2026,{NVIDIA},Dividende,,USD,"9,00",USD,"9,00",',
    ]

    imported = import_degiro(
        transactions=[NVIDIA_BUY], account=[*dividend, DEPOSIT_1200], tickers=NVIDIA_TICKER, corporate_actions=(paid,), fx_rates=(rate,)
    )

    assert [op for op in imported.wallet.operations if isinstance(op, Dividend)] == []
    assert imported.wallet.cash == Decimal("102.20")  # 95.25 after the buy, + 6.95


def test_a_dividend_whose_value_date_is_before_the_market_data_payment_date_still_replaces_it() -> None:
    # As IBM's dividend of September 2023: DEGIRO's value date is Saturday 9, market data says Monday 11.
    ibm = "INTERNATIONAL BUSINESS MACHINES CORP,US4592001014"
    paid = DividendEvent("IBM", date(2023, 8, 9), date(2023, 9, 11), Decimal("1.66"), Currency.USD, "ibm-2023-09")
    rate = FxRate(Currency.USD, Currency.EUR, Decimal("0.93"), date(2023, 9, 11))
    buy = f'01-06-2023,16:00,{ibm},NSY,XNYS,1,"130,0000",USD,"-130,00",USD,"-120,00","1,0833","-0,30","-0,50","-120,80",order-7'
    account = [
        '12-09-2023,07:00,11-09-2023,,,Operation de change - Crédit,,EUR,"1,15",EUR,"381,35",',
        '12-09-2023,07:00,11-09-2023,,,Opération de change - Débit,"1,0700",USD,"-1,23",USD,"0,00",',
        f'11-09-2023,07:40,09-09-2023,{ibm},Impôts sur dividende,,USD,"-0,25",USD,"1,23",',
        '11-09-2023,07:41,09-09-2023,,,Frais d’opération sur titres,,USD,"-0,18",USD,"1,23",',
        f'11-09-2023,07:40,09-09-2023,{ibm},Dividende,,USD,"1,66",USD,"1,66",',
        '20-05-2023,10:00,20-05-2023,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
    ]

    imported = import_degiro(
        transactions=[buy], account=account, tickers={"US4592001014": "IBM"}, corporate_actions=(paid,), fx_rates=(rate,)
    )

    assert [op for op in imported.wallet.operations if isinstance(op, Dividend)] == []
    assert imported.wallet.cash == Decimal("380.35")  # 500 - 120.80 + 1.15


def test_two_isin_changes_in_the_same_minute_are_paired_by_their_shares() -> None:
    # Meituan's change (1 share) and, at the same minute, another holding's (20 shares), each within one ticker.
    other_change = [
        '27-03-2023,08:44,TENCENT HOLDINGS - OLD LINE,XX0000000001,DEG,,-20,"40,0000",EUR,"800,00",EUR,"800,00","1,0000","0,00",,"800,00",',
        f'27-03-2023,08:44,{TENCENT},TDG,,20,"40,0000",EUR,"-800,00",EUR,"-800,00","1,0000","0,00",,"-800,00",',
    ]
    other_notices = [
        '27-03-2023,08:44,27-03-2023,TENCENT HOLDINGS - OLD LINE,XX0000000001,"Changement ISIN: Vente 20 Tencent@40 EUR (XX0000000001)",,'
        'EUR,"800,00",EUR,"896,10",',
        f'27-03-2023,08:44,27-03-2023,{TENCENT},"Changement ISIN: Achat 20 Tencent@40 EUR (KYG875721634)",,EUR,"-800,00",EUR,"96,10",',
    ]

    imported = import_degiro(
        transactions=[*other_change, *MEITUAN_ISIN_CHANGES, MEITUAN_SPIN_OFF, TENCENT_BUY],
        account=[*other_notices, *MEITUAN_ISIN_CHANGE_NOTICES, MEITUAN_SPIN_OFF_NOTICE, DEPOSIT_900],
        tickers={**TENCENT_TICKERS, "RCC188527108": "3690.HK", "XX0000000001": "0700.HK"},
    )

    assert imported.report.imported
    assert imported.wallet.holdings == {"0700.HK": Decimal(20), "3690.HK": Decimal(1)}


def test_a_spin_off_giving_no_whole_share_needs_no_ticker() -> None:
    # Kyndryl's spin-off gave 0 shares: nothing to record, so the import must not ask for KD's ticker.
    kyndryl = '"KYNDRYL HOLDINGS, INC.",US50155Q1004'
    spin_off = f'04-11-2021,00:00,{kyndryl},NSY,,0,"0,0000",USD,"0,00",USD,"0,00","1,1738","0,00",,"0,00",'
    notice = (
        f'04-11-2021,13:55,04-11-2021,{kyndryl},"Spin-off: Achat 0 Kyndryl Holdings, Inc.@0 USD (US50155Q1004)",,USD,"0,00",USD,"0,00",'
    )

    imported = import_degiro(transactions=[spin_off], account=[notice])

    assert imported.report.imported


WM = "WASTE MANAGEMENT INC,US94106L1098"
TWO_DIVIDENDS_WAITING = [
    f'29-03-2024,07:14,28-03-2024,{WM},Dividende,,USD,"2,00",USD,"3,00",',
    f'28-03-2024,07:39,27-03-2024,{NVIDIA},Dividende,,USD,"1,00",USD,"1,00",',
    '01-03-2024,10:00,01-03-2024,,,Dépôt flatex,,EUR,"500,00",EUR,"500,00",',
]
TWO_TICKERS = {**NVIDIA_TICKER, "US94106L1098": "WM"}


def test_a_conversion_matching_no_waiting_cash_is_reported_not_guessed() -> None:
    account = [
        '30-03-2024,07:00,29-03-2024,,,Operation de change - Crédit,,EUR,"2,25",EUR,"502,25",',
        '30-03-2024,07:00,29-03-2024,,,Opération de change - Débit,"1,1000",USD,"-2,50",USD,"0,50",',
        *TWO_DIVIDENDS_WAITING,
    ]

    imported = import_degiro(transactions=[], account=account, tickers=TWO_TICKERS)

    assert not imported.report.imported
    assert {problem.record.description for problem in imported.report.not_imported} >= {"Opération de change - Débit"}
