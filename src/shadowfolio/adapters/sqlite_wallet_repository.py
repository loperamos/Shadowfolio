"""WalletRepository backed by a SQLite file."""

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from shadowfolio.domain.corporate_actions import CheckedPeriod, DividendEvent, RecordedDividend
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
    Trade,
    Withdrawal,
)
from shadowfolio.domain.orders import Order, OrderSide, OrderStatus
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.wallet_repository import WalletRepository

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    currency TEXT NOT NULL,
    withholding_rate TEXT NOT NULL DEFAULT '0'
);
CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL REFERENCES wallets (id),
    type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    amount TEXT NOT NULL,
    fees TEXT NOT NULL,
    symbol TEXT,
    quantity TEXT,
    price TEXT,
    price_currency TEXT,
    price_source TEXT,
    split_old_rate TEXT,
    split_new_rate TEXT,
    event_id TEXT,
    fx_rate TEXT,
    withholding TEXT,
    gross TEXT,
    description TEXT,
    payment_date TEXT
);
CREATE TABLE IF NOT EXISTS checked_periods (
    wallet_id TEXT NOT NULL REFERENCES wallets (id),
    symbol TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    PRIMARY KEY (wallet_id, symbol)
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL REFERENCES wallets (id),
    side TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity TEXT NOT NULL,
    placed_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    closed_at TEXT,
    rejection TEXT
);
CREATE TABLE IF NOT EXISTS dividend_events (
    wallet_id TEXT NOT NULL REFERENCES wallets (id),
    event_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    payable_date TEXT,
    per_share TEXT NOT NULL,
    currency TEXT NOT NULL,
    fx_rate TEXT,
    PRIMARY KEY (wallet_id, event_id)
);
"""

# Columns added after a database may already exist, with what existing rows get. Trades stored before
# price_source existed were all typed in from a broker; split and dividend columns only apply to those, added later.
# Wallets stored before withholding existed paid dividends gross.
_ADDED_COLUMNS = {
    "wallets": {"withholding_rate": "TEXT NOT NULL DEFAULT '0'"},
    "operations": {
        "price_source": "TEXT DEFAULT 'entered'",
        "split_old_rate": "TEXT",
        "split_new_rate": "TEXT",
        "event_id": "TEXT",
        "fx_rate": "TEXT",
        "withholding": "TEXT",
        "gross": "TEXT",
        "description": "TEXT",
        "payment_date": "TEXT",
    },
}


class SqliteWalletRepository(WalletRepository):
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)
            _add_missing_columns(conn)

    def add(self, wallet: Wallet) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO wallets (id, owner_id, name, currency, withholding_rate) VALUES (?, ?, ?, ?, ?)",
                (str(wallet.id), wallet.owner_id, wallet.name, wallet.currency.value, str(wallet.withholding_rate)),
            )
            _insert_operations(conn, wallet)
            _insert_checked_periods(conn, wallet)
            _insert_dividend_events(conn, wallet)
            _insert_orders(conn, wallet)

    def update(self, wallet: Wallet) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE wallets SET owner_id = ?, name = ?, currency = ?, withholding_rate = ? WHERE id = ?",
                (wallet.owner_id, wallet.name, wallet.currency.value, str(wallet.withholding_rate), str(wallet.id)),
            )
            # Operations can be changed or removed, so they are replaced as a whole, in the same transaction.
            conn.execute("DELETE FROM operations WHERE wallet_id = ?", (str(wallet.id),))
            _insert_operations(conn, wallet)
            conn.execute("DELETE FROM checked_periods WHERE wallet_id = ?", (str(wallet.id),))
            _insert_checked_periods(conn, wallet)
            conn.execute("DELETE FROM dividend_events WHERE wallet_id = ?", (str(wallet.id),))
            _insert_dividend_events(conn, wallet)
            conn.execute("DELETE FROM orders WHERE wallet_id = ?", (str(wallet.id),))
            _insert_orders(conn, wallet)

    def get(self, wallet_id: UUID) -> Wallet | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, owner_id, name, currency, withholding_rate FROM wallets WHERE id = ?", (str(wallet_id),)
            ).fetchone()
            if row is None:
                return None
            operation_rows = conn.execute(
                "SELECT id, type, timestamp, amount, fees, symbol, quantity, price, price_currency, price_source, "
                "split_old_rate, split_new_rate, event_id, fx_rate, withholding, gross, description, payment_date "
                "FROM operations WHERE wallet_id = ? ORDER BY timestamp, rowid",
                (str(wallet_id),),
            ).fetchall()
            period_rows = conn.execute("SELECT symbol, start, end FROM checked_periods WHERE wallet_id = ?", (str(wallet_id),)).fetchall()
            dividend_rows = conn.execute(
                "SELECT event_id, symbol, ex_date, payable_date, per_share, currency, fx_rate FROM dividend_events "
                "WHERE wallet_id = ? ORDER BY rowid",
                (str(wallet_id),),
            ).fetchall()
            order_rows = conn.execute(
                "SELECT id, side, symbol, quantity, placed_at, reason, status, closed_at, rejection FROM orders "
                "WHERE wallet_id = ? ORDER BY rowid",
                (str(wallet_id),),
            ).fetchall()
        return Wallet(
            id=UUID(row[0]),
            owner_id=row[1],
            name=row[2],
            currency=Currency(row[3]),
            operations=tuple(_operation_from_row(op) for op in operation_rows),
            checked={symbol: CheckedPeriod(date.fromisoformat(start), date.fromisoformat(end)) for symbol, start, end in period_rows},
            dividend_events=tuple(_dividend_from_row(row) for row in dividend_rows),
            withholding_rate=Decimal(row[4]),
            orders=tuple(_order_from_row(order) for order in order_rows),
        )

    def delete(self, wallet_id: UUID) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM operations WHERE wallet_id = ?", (str(wallet_id),))
            conn.execute("DELETE FROM checked_periods WHERE wallet_id = ?", (str(wallet_id),))
            conn.execute("DELETE FROM dividend_events WHERE wallet_id = ?", (str(wallet_id),))
            conn.execute("DELETE FROM orders WHERE wallet_id = ?", (str(wallet_id),))
            conn.execute("DELETE FROM wallets WHERE id = ?", (str(wallet_id),))

    def all_ids(self) -> list[UUID]:
        with closing(self._connect()) as conn:
            return [UUID(row[0]) for row in conn.execute("SELECT id FROM wallets ORDER BY rowid")]

    def list_by_owner(self, owner_id: str) -> list[Wallet]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT id FROM wallets WHERE owner_id = ? ORDER BY rowid", (owner_id,)).fetchall()
        wallets = [self.get(UUID(row[0])) for row in rows]
        return [wallet for wallet in wallets if wallet is not None]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)


def _insert_operations(conn: sqlite3.Connection, wallet: Wallet) -> None:
    # In timeline order, so equal timestamps read back in the same order (ORDER BY timestamp, rowid).
    conn.executemany(
        "INSERT INTO operations (id, wallet_id, type, timestamp, amount, fees, "
        "symbol, quantity, price, price_currency, price_source, split_old_rate, split_new_rate, event_id, fx_rate, "
        "withholding, gross, description, payment_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [_operation_to_row(wallet.id, op) for op in wallet.operations],
    )


def _insert_checked_periods(conn: sqlite3.Connection, wallet: Wallet) -> None:
    conn.executemany(
        "INSERT INTO checked_periods (wallet_id, symbol, start, end) VALUES (?, ?, ?, ?)",
        [(str(wallet.id), symbol, period.start.isoformat(), period.end.isoformat()) for symbol, period in wallet.checked.items()],
    )


def _insert_orders(conn: sqlite3.Connection, wallet: Wallet) -> None:
    # In the order they were placed, so they read back in it (ORDER BY rowid).
    conn.executemany(
        "INSERT INTO orders (id, wallet_id, side, symbol, quantity, placed_at, reason, status, closed_at, rejection) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                str(order.id),
                str(wallet.id),
                order.side.value,
                order.symbol,
                str(order.quantity),
                order.placed_at.isoformat(),
                order.reason,
                order.status.value,
                None if order.closed_at is None else order.closed_at.isoformat(),
                order.rejection,
            )
            for order in wallet.orders
        ],
    )


def _order_from_row(row: tuple[str, ...]) -> Order:
    order_id, side, symbol, quantity, placed_at, reason, status, closed_at, rejection = row
    return Order(
        id=UUID(order_id),
        side=OrderSide(side),
        symbol=symbol,
        quantity=Decimal(quantity),
        placed_at=datetime.fromisoformat(placed_at),
        reason=reason,
        status=OrderStatus(status),
        closed_at=None if closed_at is None else datetime.fromisoformat(closed_at),
        rejection=rejection,
    )


def _insert_dividend_events(conn: sqlite3.Connection, wallet: Wallet) -> None:
    conn.executemany(
        "INSERT INTO dividend_events (wallet_id, event_id, symbol, ex_date, payable_date, per_share, currency, fx_rate) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                str(wallet.id),
                recorded.event.event_id,
                recorded.event.symbol,
                recorded.event.ex_date.isoformat(),
                None if recorded.event.payable_date is None else recorded.event.payable_date.isoformat(),
                str(recorded.event.per_share),
                recorded.event.currency.value,
                None if recorded.fx_rate is None else str(recorded.fx_rate),
            )
            for recorded in wallet.dividend_events
        ],
    )


def _dividend_from_row(row: tuple[str, ...]) -> RecordedDividend:
    event_id, symbol, ex_date, payable_date, per_share, currency, fx_rate = row
    event = DividendEvent(
        symbol,
        date.fromisoformat(ex_date),
        None if payable_date is None else date.fromisoformat(payable_date),
        Decimal(per_share),
        Currency(currency),
        event_id,
    )
    return RecordedDividend(event, None if fx_rate is None else Decimal(fx_rate))


def _operation_to_row(wallet_id: UUID, op: Operation) -> tuple[str | None, ...]:
    """One row per operation; columns that do not apply to its kind are NULL."""
    symbol = quantity = price = price_currency = price_source = old_rate = new_rate = event_id = fx_rate = None
    withholding = gross = description = payment_date = None
    match op:
        case Deposit() | Withdrawal():
            amount, fees = op.amount, Decimal(0)
        case Buy() | Sell():
            amount, fees, trade = op.settled_amount, op.fees, op.trade
            symbol, quantity, price = trade.symbol, str(trade.quantity), str(trade.price)
            price_currency, price_source = trade.price_currency.value, trade.price_source.value
        case Split():
            amount, fees = Decimal(0), Decimal(0)
            symbol, old_rate, new_rate, event_id = op.symbol, str(op.old_rate), str(op.new_rate), op.event_id
        case Dividend():
            # quantity: the shares that qualified; price: the amount per share, in its currency; amount: net of withholding.
            amount, fees, withholding = op.amount, Decimal(0), str(op.withholding)
            symbol, quantity, price, price_currency, event_id = op.symbol, str(op.shares), str(op.per_share), op.currency.value, op.event_id
            fx_rate = None if op.fx_rate is None else str(op.fx_rate)
        case ImportedDividend():
            # From a statement, so no event: amount credited; fees, withholding and gross in the dividend's currency.
            amount, fees, withholding, gross = op.amount, op.fee, str(op.tax), str(op.gross)
            symbol, price_currency, payment_date = op.symbol, op.currency, op.payment_date.isoformat()
        case Fee() | Income():
            amount, fees, description = op.amount, Decimal(0), op.description
        case SharesReceived():
            amount, fees, symbol, quantity = op.cost, Decimal(0), op.symbol, str(op.quantity)
    return (
        str(op.id),
        str(wallet_id),
        op.type.value,
        op.timestamp.astimezone(UTC).isoformat(),
        str(amount),
        str(fees),
        symbol,
        quantity,
        price,
        price_currency,
        price_source,
        old_rate,
        new_rate,
        event_id,
        fx_rate,
        withholding,
        gross,
        description,
        payment_date,
    )


def _operation_from_row(row: tuple[str | None, ...]) -> Operation:
    (
        op_id,
        op_type,
        timestamp,
        amount,
        fees,
        symbol,
        quantity,
        price,
        price_currency,
        price_source,
        old_rate,
        new_rate,
        event_id,
        fx_rate,
        withholding,
        gross,
        description,
        payment_date,
    ) = row
    assert op_id and op_type and timestamp and amount and fees
    id_, at, value = UUID(op_id), datetime.fromisoformat(timestamp), Decimal(amount)
    match OperationType(op_type):
        case OperationType.DEPOSIT:
            return Deposit(id_, at, value)
        case OperationType.WITHDRAWAL:
            return Withdrawal(id_, at, value)
        case OperationType.BUY | OperationType.SELL as kind:
            assert symbol and quantity and price and price_currency
            source = PriceSource(price_source) if price_source else PriceSource.ENTERED
            trade = Trade(symbol, Decimal(quantity), Decimal(price), Currency(price_currency), source)
            trade_class = Buy if kind is OperationType.BUY else Sell
            return trade_class(id_, at, trade, value, Decimal(fees))
        case OperationType.SPLIT:
            assert symbol and old_rate and new_rate and event_id
            return Split(id_, at, symbol, Decimal(old_rate), Decimal(new_rate), event_id)
        case OperationType.FEE:
            assert description is not None
            return Fee(id_, at, value, description)
        case OperationType.SHARES_RECEIVED:
            assert symbol and quantity
            return SharesReceived(id_, at, symbol, Decimal(quantity), value)
        case OperationType.INCOME:
            assert description is not None
            return Income(id_, at, value, description)
        case OperationType.DIVIDEND if event_id is None:
            assert symbol and price_currency and gross and withholding and payment_date
            paid = date.fromisoformat(payment_date)
            return ImportedDividend(id_, at, symbol, price_currency, Decimal(gross), Decimal(withholding), Decimal(fees), value, paid)
        case OperationType.DIVIDEND:
            assert symbol and quantity and price and price_currency and event_id
            rate = None if fx_rate is None else Decimal(fx_rate)
            withheld = Decimal(withholding) if withholding is not None else Decimal(0)
            return Dividend(id_, at, symbol, Decimal(price), Currency(price_currency), Decimal(quantity), rate, value, event_id, withheld)


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Brings an existing database up to the current schema by adding columns introduced since it was created."""
    for table, columns in _ADDED_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
