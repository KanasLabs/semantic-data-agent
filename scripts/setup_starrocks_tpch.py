from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb


@dataclass(frozen=True)
class TableSpec:
    name: str
    key_columns: tuple[str, ...]
    columns: tuple[tuple[str, str], ...]


TABLE_SPECS = (
    TableSpec(
        "region",
        ("r_regionkey",),
        (
            ("r_regionkey", "INT NOT NULL"),
            ("r_name", "VARCHAR(25) NOT NULL"),
            ("r_comment", "VARCHAR(152)"),
        ),
    ),
    TableSpec(
        "nation",
        ("n_nationkey",),
        (
            ("n_nationkey", "INT NOT NULL"),
            ("n_name", "VARCHAR(25) NOT NULL"),
            ("n_regionkey", "INT NOT NULL"),
            ("n_comment", "VARCHAR(152)"),
        ),
    ),
    TableSpec(
        "supplier",
        ("s_suppkey",),
        (
            ("s_suppkey", "INT NOT NULL"),
            ("s_name", "VARCHAR(25) NOT NULL"),
            ("s_address", "VARCHAR(40) NOT NULL"),
            ("s_nationkey", "INT NOT NULL"),
            ("s_phone", "VARCHAR(15) NOT NULL"),
            ("s_acctbal", "DECIMAL(15, 2) NOT NULL"),
            ("s_comment", "VARCHAR(101) NOT NULL"),
        ),
    ),
    TableSpec(
        "customer",
        ("c_custkey",),
        (
            ("c_custkey", "INT NOT NULL"),
            ("c_name", "VARCHAR(25) NOT NULL"),
            ("c_address", "VARCHAR(40) NOT NULL"),
            ("c_nationkey", "INT NOT NULL"),
            ("c_phone", "VARCHAR(15) NOT NULL"),
            ("c_acctbal", "DECIMAL(15, 2) NOT NULL"),
            ("c_mktsegment", "VARCHAR(10) NOT NULL"),
            ("c_comment", "VARCHAR(117) NOT NULL"),
        ),
    ),
    TableSpec(
        "part",
        ("p_partkey",),
        (
            ("p_partkey", "INT NOT NULL"),
            ("p_name", "VARCHAR(55) NOT NULL"),
            ("p_mfgr", "VARCHAR(25) NOT NULL"),
            ("p_brand", "VARCHAR(10) NOT NULL"),
            ("p_type", "VARCHAR(25) NOT NULL"),
            ("p_size", "INT NOT NULL"),
            ("p_container", "VARCHAR(10) NOT NULL"),
            ("p_retailprice", "DECIMAL(15, 2) NOT NULL"),
            ("p_comment", "VARCHAR(23) NOT NULL"),
        ),
    ),
    TableSpec(
        "partsupp",
        ("ps_partkey", "ps_suppkey"),
        (
            ("ps_partkey", "INT NOT NULL"),
            ("ps_suppkey", "INT NOT NULL"),
            ("ps_availqty", "INT NOT NULL"),
            ("ps_supplycost", "DECIMAL(15, 2) NOT NULL"),
            ("ps_comment", "VARCHAR(199) NOT NULL"),
        ),
    ),
    TableSpec(
        "orders",
        ("o_orderkey",),
        (
            ("o_orderkey", "BIGINT NOT NULL"),
            ("o_custkey", "INT NOT NULL"),
            ("o_orderstatus", "VARCHAR(1) NOT NULL"),
            ("o_totalprice", "DECIMAL(15, 2) NOT NULL"),
            ("o_orderdate", "DATE NOT NULL"),
            ("o_orderpriority", "VARCHAR(15) NOT NULL"),
            ("o_clerk", "VARCHAR(15) NOT NULL"),
            ("o_shippriority", "INT NOT NULL"),
            ("o_comment", "VARCHAR(79) NOT NULL"),
        ),
    ),
    TableSpec(
        "lineitem",
        ("l_orderkey", "l_partkey", "l_suppkey", "l_linenumber"),
        (
            ("l_orderkey", "BIGINT NOT NULL"),
            ("l_partkey", "INT NOT NULL"),
            ("l_suppkey", "INT NOT NULL"),
            ("l_linenumber", "INT NOT NULL"),
            ("l_quantity", "DECIMAL(15, 2) NOT NULL"),
            ("l_extendedprice", "DECIMAL(15, 2) NOT NULL"),
            ("l_discount", "DECIMAL(15, 2) NOT NULL"),
            ("l_tax", "DECIMAL(15, 2) NOT NULL"),
            ("l_returnflag", "VARCHAR(1) NOT NULL"),
            ("l_linestatus", "VARCHAR(1) NOT NULL"),
            ("l_shipdate", "DATE NOT NULL"),
            ("l_commitdate", "DATE NOT NULL"),
            ("l_receiptdate", "DATE NOT NULL"),
            ("l_shipinstruct", "VARCHAR(25) NOT NULL"),
            ("l_shipmode", "VARCHAR(10) NOT NULL"),
            ("l_comment", "VARCHAR(44) NOT NULL"),
        ),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a reproducible TPC-H fixture into StarRocks.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19030)
    parser.add_argument("--database", default="tpch_sf001")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password-env", default="CONTEXT_BUILDER_STARROCKS_PASSWORD")
    parser.add_argument("--allow-empty-password", action="store_true")
    parser.add_argument("--scale-factor", type=float, default=0.01)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--extension-dir", default="data/duckdb_extensions")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    database = validate_identifier(args.database)
    if args.scale_factor <= 0:
        raise ValueError("scale-factor must be greater than zero.")
    if args.batch_size < 1:
        raise ValueError("batch-size must be at least one.")

    password = os.environ.get(args.password_env)
    if password is None and not args.allow_empty_password:
        raise RuntimeError(
            f"Set {args.password_env} or pass --allow-empty-password for an isolated local fixture."
        )

    source = generate_tpch_source(
        scale_factor=args.scale_factor,
        extension_dir=Path(args.extension_dir),
    )
    try:
        result = load_starrocks(
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

    print("TPC-H StarRocks fixture ready")
    print(f"database: {database}")
    print(f"scale_factor: {args.scale_factor}")
    for table, count in result.items():
        print(f"{table}: {count}")


def generate_tpch_source(*, scale_factor: float, extension_dir: Path) -> duckdb.DuckDBPyConnection:
    extension_dir = extension_dir.resolve()
    extension_dir.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    connection.execute(f"SET extension_directory='{extension_dir.as_posix()}'")
    try:
        connection.execute("LOAD tpch")
    except duckdb.Error:
        connection.execute("INSTALL tpch")
        connection.execute("LOAD tpch")
    connection.execute("CALL dbgen(sf = ?)", [scale_factor])
    return connection


def load_starrocks(
    *,
    source: duckdb.DuckDBPyConnection,
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
        read_timeout=120,
        write_timeout=120,
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
            return verify_counts(cursor)
        finally:
            cursor.close()
    finally:
        connection.close()


def create_table_sql(spec: TableSpec) -> str:
    columns = ",\n    ".join(f"`{name}` {column_type}" for name, column_type in spec.columns)
    keys = ", ".join(f"`{name}`" for name in spec.key_columns)
    distribution_key = spec.key_columns[0]
    return f"""CREATE TABLE `{spec.name}` (
    {columns}
)
ENGINE = OLAP
DUPLICATE KEY({keys})
DISTRIBUTED BY HASH(`{distribution_key}`) BUCKETS 1
PROPERTIES ("replication_num" = "1")"""


def insert_table(source: duckdb.DuckDBPyConnection, cursor: Any, spec: TableSpec, *, batch_size: int) -> None:
    source_cursor = source.execute(f'SELECT * FROM "{spec.name}"')
    placeholders = ", ".join(["%s"] * len(spec.columns))
    insert_sql = f"INSERT INTO `{spec.name}` VALUES ({placeholders})"
    while True:
        rows = source_cursor.fetchmany(batch_size)
        if not rows:
            return
        cursor.executemany(insert_sql, rows)


def verify_counts(cursor: Any) -> dict[str, int]:
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
