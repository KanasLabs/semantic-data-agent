from __future__ import annotations

import argparse
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TableSpec:
    name: str
    key_columns: tuple[str, ...]
    distribution_column: str
    columns: tuple[tuple[str, str], ...]


TABLE_SPECS = (
    TableSpec(
        "customers",
        ("CustomerID",),
        "CustomerID",
        (
            ("CustomerID", "BIGINT NOT NULL"),
            ("Segment", "VARCHAR(32)"),
            ("Currency", "VARCHAR(8)"),
        ),
    ),
    TableSpec(
        "gasstations",
        ("GasStationID",),
        "GasStationID",
        (
            ("GasStationID", "BIGINT NOT NULL"),
            ("ChainID", "BIGINT"),
            ("Country", "VARCHAR(8)"),
            ("Segment", "VARCHAR(32)"),
        ),
    ),
    TableSpec(
        "products",
        ("ProductID",),
        "ProductID",
        (
            ("ProductID", "BIGINT NOT NULL"),
            ("Description", "VARCHAR(255)"),
        ),
    ),
    TableSpec(
        "transactions_1k",
        ("TransactionID",),
        "TransactionID",
        (
            ("TransactionID", "BIGINT NOT NULL"),
            ("Date", "DATE"),
            ("Time", "VARCHAR(16)"),
            ("CustomerID", "BIGINT"),
            ("CardID", "BIGINT"),
            ("GasStationID", "BIGINT"),
            ("ProductID", "BIGINT"),
            ("Amount", "BIGINT"),
            ("Price", "DOUBLE"),
        ),
    ),
    TableSpec(
        "yearmonth",
        ("Date", "CustomerID"),
        "CustomerID",
        (
            ("Date", "VARCHAR(6) NOT NULL"),
            ("CustomerID", "BIGINT NOT NULL"),
            ("Consumption", "DOUBLE"),
        ),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load BIRD Mini-Dev debit_card_specializing into StarRocks."
    )
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19030)
    parser.add_argument("--database", default="bird_debit_card_specializing")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password-env", default="CONTEXT_BUILDER_STARROCKS_PASSWORD")
    parser.add_argument("--allow-empty-password", action="store_true")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path).resolve()
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    database = validate_identifier(args.database)
    if args.batch_size < 1:
        raise ValueError("batch-size must be at least one.")

    password = os.environ.get(args.password_env)
    if password is None and not args.allow_empty_password:
        raise RuntimeError(
            f"Set {args.password_env} or pass --allow-empty-password for an isolated local fixture."
        )

    source = sqlite3.connect(sqlite_path)
    try:
        source_counts = verify_source(source)
        loaded_counts = load_starrocks(
            source=source,
            host=args.host,
            port=args.port,
            database=database,
            user=args.user,
            password=password or "",
            batch_size=args.batch_size,
            force=args.force,
        )
    finally:
        source.close()

    if loaded_counts != source_counts:
        raise RuntimeError(
            f"StarRocks row counts differ from SQLite source: {loaded_counts} != {source_counts}"
        )
    print("BIRD Mini-Dev StarRocks fixture ready")
    print(f"database: {database}")
    for table, count in loaded_counts.items():
        print(f"{table}: {count}")


def verify_source(source: sqlite3.Connection) -> dict[str, int]:
    available = {
        str(row[0])
        for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    required = {spec.name for spec in TABLE_SPECS}
    missing = sorted(required - available)
    if missing:
        raise ValueError(f"SQLite database is missing required tables: {', '.join(missing)}")
    return {
        spec.name: int(source.execute(f'SELECT COUNT(*) FROM "{spec.name}"').fetchone()[0])
        for spec in TABLE_SPECS
    }


def load_starrocks(
    *,
    source: sqlite3.Connection,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    batch_size: int,
    force: bool,
) -> dict[str, int]:
    try:
        import MySQLdb
    except ImportError as exc:
        raise RuntimeError('Install the Wren MySQL extra: pip install "wrenai[mysql]"') from exc

    connection = MySQLdb.connect(
        host=host,
        port=port,
        user=user,
        passwd=password,
        connect_timeout=15,
        read_timeout=180,
        write_timeout=180,
        charset="utf8mb4",
    )
    try:
        connection.autocommit(True)
        cursor = connection.cursor()
        try:
            if force:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}`")
            cursor.execute(f"USE `{database}`")
            for spec in TABLE_SPECS:
                cursor.execute(f"DROP TABLE IF EXISTS `{spec.name}`")
                cursor.execute(create_table_sql(spec))
                insert_table(source, cursor, spec, batch_size=batch_size)
            return verify_starrocks_counts(cursor)
        finally:
            cursor.close()
    finally:
        connection.close()


def create_table_sql(spec: TableSpec) -> str:
    columns = ",\n    ".join(f"`{name}` {column_type}" for name, column_type in spec.columns)
    keys = ", ".join(f"`{name}`" for name in spec.key_columns)
    return f'''CREATE TABLE `{spec.name}` (
    {columns}
)
ENGINE = OLAP
DUPLICATE KEY({keys})
DISTRIBUTED BY HASH(`{spec.distribution_column}`) BUCKETS 1
PROPERTIES ("replication_num" = "1")'''


def insert_table(
    source: sqlite3.Connection,
    cursor: Any,
    spec: TableSpec,
    *,
    batch_size: int,
) -> None:
    column_names = [name for name, _ in spec.columns]
    source_columns = ", ".join(f'"{name}"' for name in column_names)
    target_columns = ", ".join(f"`{name}`" for name in column_names)
    source_cursor = source.execute(f'SELECT {source_columns} FROM "{spec.name}"')
    placeholders = ", ".join(["%s"] * len(column_names))
    insert_sql = f"INSERT INTO `{spec.name}` ({target_columns}) VALUES ({placeholders})"
    while True:
        rows = source_cursor.fetchmany(batch_size)
        if not rows:
            return
        cursor.executemany(insert_sql, rows)


def verify_starrocks_counts(cursor: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for spec in TABLE_SPECS:
        cursor.execute(f"SELECT COUNT(*) FROM `{spec.name}`")
        counts[spec.name] = int(cursor.fetchone()[0])
    return counts


def validate_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


if __name__ == "__main__":
    main()
