"""WalletRepository backed by a SQLite file."""

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from shadowfolio.domain.corporate_actions import CheckedPeriod
from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Deposit, Operation, OperationType, PriceSource, Sell, Split, Trade, Withdrawal
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.wallet_repository import WalletRepository

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    currency TEXT NOT NULL
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
    event_id TEXT
);
CREATE TABLE IF NOT EXISTS checked_periods (
    wallet_id TEXT NOT NULL REFERENCES wallets (id),
    symbol TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    PRIMARY KEY (wallet_id, symbol)
);
"""

# Columns added after a database may already exist, with what existing rows get. Trades stored before
# price_source existed were all typed in from a broker; split columns only apply to splits, added later.
_ADDED_COLUMNS = {
    "operations": {"price_source": "TEXT DEFAULT 'entered'", "split_old_rate": "TEXT", "split_new_rate": "TEXT", "event_id": "TEXT"}
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
                "INSERT INTO wallets (id, owner_id, name, currency) VALUES (?, ?, ?, ?)",
                (str(wallet.id), wallet.owner_id, wallet.name, wallet.currency.value),
            )
            _insert_operations(conn, wallet)
            _insert_checked_periods(conn, wallet)

    def update(self, wallet: Wallet) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE wallets SET owner_id = ?, name = ?, currency = ? WHERE id = ?",
                (wallet.owner_id, wallet.name, wallet.currency.value, str(wallet.id)),
            )
            # Operations can be changed or removed, so they are replaced as a whole, in the same transaction.
            conn.execute("DELETE FROM operations WHERE wallet_id = ?", (str(wallet.id),))
            _insert_operations(conn, wallet)
            conn.execute("DELETE FROM checked_periods WHERE wallet_id = ?", (str(wallet.id),))
            _insert_checked_periods(conn, wallet)

    def get(self, wallet_id: UUID) -> Wallet | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT id, owner_id, name, currency FROM wallets WHERE id = ?", (str(wallet_id),)).fetchone()
            if row is None:
                return None
            operation_rows = conn.execute(
                "SELECT id, type, timestamp, amount, fees, symbol, quantity, price, price_currency, price_source, "
                "split_old_rate, split_new_rate, event_id "
                "FROM operations WHERE wallet_id = ? ORDER BY timestamp, rowid",
                (str(wallet_id),),
            ).fetchall()
            period_rows = conn.execute("SELECT symbol, start, end FROM checked_periods WHERE wallet_id = ?", (str(wallet_id),)).fetchall()
        return Wallet(
            id=UUID(row[0]),
            owner_id=row[1],
            name=row[2],
            currency=Currency(row[3]),
            operations=tuple(_operation_from_row(op) for op in operation_rows),
            checked={symbol: CheckedPeriod(date.fromisoformat(start), date.fromisoformat(end)) for symbol, start, end in period_rows},
        )

    def delete(self, wallet_id: UUID) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM operations WHERE wallet_id = ?", (str(wallet_id),))
            conn.execute("DELETE FROM checked_periods WHERE wallet_id = ?", (str(wallet_id),))
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
        "symbol, quantity, price, price_currency, price_source, split_old_rate, split_new_rate, event_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [_operation_to_row(wallet.id, op) for op in wallet.operations],
    )


def _insert_checked_periods(conn: sqlite3.Connection, wallet: Wallet) -> None:
    conn.executemany(
        "INSERT INTO checked_periods (wallet_id, symbol, start, end) VALUES (?, ?, ?, ?)",
        [(str(wallet.id), symbol, period.start.isoformat(), period.end.isoformat()) for symbol, period in wallet.checked.items()],
    )


def _operation_to_row(wallet_id: UUID, op: Operation) -> tuple[str | None, ...]:
    """One row per operation; columns that do not apply to its kind are NULL."""
    trade, split = None, None
    match op:
        case Deposit() | Withdrawal():
            amount, fees = op.amount, Decimal(0)
        case Buy() | Sell():
            amount, fees, trade = op.settled_amount, op.fees, op.trade
        case Split():
            amount, fees, split = Decimal(0), Decimal(0), op
    return (
        str(op.id),
        str(wallet_id),
        op.type.value,
        op.timestamp.astimezone(UTC).isoformat(),
        str(amount),
        str(fees),
        trade.symbol if trade else split.symbol if split else None,
        str(trade.quantity) if trade else None,
        str(trade.price) if trade else None,
        trade.price_currency.value if trade else None,
        trade.price_source.value if trade else None,
        str(split.old_rate) if split else None,
        str(split.new_rate) if split else None,
        split.event_id if split else None,
    )


def _operation_from_row(row: tuple[str | None, ...]) -> Operation:
    (op_id, op_type, timestamp, amount, fees, symbol, quantity, price, price_currency, price_source, old_rate, new_rate, event_id) = row
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


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Brings an existing database up to the current schema by adding columns introduced since it was created."""
    for table, columns in _ADDED_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
