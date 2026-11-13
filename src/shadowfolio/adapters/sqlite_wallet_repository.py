"""WalletRepository backed by a SQLite file."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Deposit, Operation, OperationType, Sell, Trade, Withdrawal
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
    price_currency TEXT
);
"""


class SqliteWalletRepository(WalletRepository):
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)

    def add(self, wallet: Wallet) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO wallets (id, owner_id, name, currency) VALUES (?, ?, ?, ?)",
                (str(wallet.id), wallet.owner_id, wallet.name, wallet.currency.value),
            )
            _insert_operations(conn, wallet)

    def update(self, wallet: Wallet) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE wallets SET owner_id = ?, name = ?, currency = ? WHERE id = ?",
                (wallet.owner_id, wallet.name, wallet.currency.value, str(wallet.id)),
            )
            # Operations can be changed or removed, so they are replaced as a whole, in the same transaction.
            conn.execute("DELETE FROM operations WHERE wallet_id = ?", (str(wallet.id),))
            _insert_operations(conn, wallet)

    def get(self, wallet_id: UUID) -> Wallet | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT id, owner_id, name, currency FROM wallets WHERE id = ?", (str(wallet_id),)).fetchone()
            if row is None:
                return None
            operation_rows = conn.execute(
                "SELECT id, type, timestamp, amount, fees, symbol, quantity, price, price_currency "
                "FROM operations WHERE wallet_id = ? ORDER BY timestamp, rowid",
                (str(wallet_id),),
            ).fetchall()
        return Wallet(
            id=UUID(row[0]),
            owner_id=row[1],
            name=row[2],
            currency=Currency(row[3]),
            operations=tuple(_operation_from_row(op) for op in operation_rows),
        )

    def delete(self, wallet_id: UUID) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM operations WHERE wallet_id = ?", (str(wallet_id),))
            conn.execute("DELETE FROM wallets WHERE id = ?", (str(wallet_id),))

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
        "symbol, quantity, price, price_currency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [_operation_to_row(wallet.id, op) for op in wallet.operations],
    )


def _operation_to_row(wallet_id: UUID, op: Operation) -> tuple[str | None, ...]:
    """One row per operation; trade columns are NULL for cash operations."""
    match op:
        case Deposit() | Withdrawal():
            amount, fees, trade = op.amount, Decimal(0), None
        case Buy() | Sell():
            amount, fees, trade = op.settled_amount, op.fees, op.trade
    return (
        str(op.id),
        str(wallet_id),
        op.type.value,
        op.timestamp.astimezone(UTC).isoformat(),
        str(amount),
        str(fees),
        trade.symbol if trade else None,
        str(trade.quantity) if trade else None,
        str(trade.price) if trade else None,
        trade.price_currency.value if trade else None,
    )


def _operation_from_row(row: tuple[str | None, ...]) -> Operation:
    op_id, op_type, timestamp, amount, fees, symbol, quantity, price, price_currency = row
    assert op_id and op_type and timestamp and amount and fees
    id_, at, value = UUID(op_id), datetime.fromisoformat(timestamp), Decimal(amount)
    match OperationType(op_type):
        case OperationType.DEPOSIT:
            return Deposit(id_, at, value)
        case OperationType.WITHDRAWAL:
            return Withdrawal(id_, at, value)
        case OperationType.BUY | OperationType.SELL as kind:
            assert symbol and quantity and price and price_currency
            trade = Trade(symbol, Decimal(quantity), Decimal(price), Currency(price_currency))
            trade_class = Buy if kind is OperationType.BUY else Sell
            return trade_class(id_, at, trade, value, Decimal(fees))
