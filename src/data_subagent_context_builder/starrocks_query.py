from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import sqlglot
import sqlparse
from sqlglot import exp


_IDENTIFIER = r"(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*)"
_QUALIFIED_IDENTIFIER = rf"{_IDENTIFIER}(?:\s*\.\s*{_IDENTIFIER}){{0,2}}"
_DATABASE_SCOPE = rf"{_IDENTIFIER}(?:\s*\.\s*{_IDENTIFIER})?"
_BLOCKED_FUNCTIONS = {"benchmark", "load_file", "sleep"}


class StarRocksQueryError(ValueError):
    pass


class StarRocksQueryExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class StarRocksQueryPolicy:
    allowed_catalogs: tuple[str, ...]
    allowed_databases: tuple[str, ...]
    max_rows: int = 100
    timeout_seconds: int = 15
    allow_information_schema: bool = False

    def __post_init__(self) -> None:
        if not self.allowed_catalogs:
            raise ValueError("At least one allowed StarRocks catalog is required.")
        if not self.allowed_databases:
            raise ValueError("At least one allowed StarRocks database is required.")
        if self.max_rows < 1:
            raise ValueError("max_rows must be at least 1.")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1.")


@dataclass(frozen=True)
class StarRocksConnectionConfig:
    host: str
    port: int
    database: str
    user: str
    password: str


@dataclass(frozen=True)
class QueryRows:
    columns: list[str]
    rows: list[tuple[Any, ...]]


@dataclass(frozen=True)
class ValidatedQuery:
    sql: str
    statement_kind: str


class StarRocksQueryExecutor(Protocol):
    def execute(self, sql: str, *, max_rows: int, timeout_seconds: int) -> QueryRows:
        ...


class MySQLdbStarRocksExecutor:
    def __init__(self, config: StarRocksConnectionConfig) -> None:
        self.config = config

    def execute(self, sql: str, *, max_rows: int, timeout_seconds: int) -> QueryRows:
        try:
            import MySQLdb
        except ImportError as exc:
            raise StarRocksQueryExecutionError(
                "mysqlclient is required for StarRocks MySQL-protocol queries."
            ) from exc

        connection = MySQLdb.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            passwd=self.config.password,
            db=self.config.database,
            connect_timeout=timeout_seconds,
            read_timeout=timeout_seconds,
            write_timeout=timeout_seconds,
            charset="utf8mb4",
        )
        try:
            connection.autocommit(True)
            cursor = connection.cursor()
            try:
                cursor.execute(f"SET query_timeout = {int(timeout_seconds)}")
                cursor.execute(sql)
                columns = [description[0] for description in cursor.description or []]
                rows = list(cursor.fetchmany(max_rows + 1)) if cursor.description else []
                return QueryRows(columns=columns, rows=rows)
            finally:
                cursor.close()
        finally:
            connection.close()


def run_starrocks_query(
    *,
    sql: str,
    database: str,
    policy: StarRocksQueryPolicy,
    evidence_path: Path,
    executor: StarRocksQueryExecutor,
    include_evidence_rows: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    evidence_base = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "database": database,
        "allowed_catalogs": list(policy.allowed_catalogs),
        "allowed_databases": list(policy.allowed_databases),
        "max_rows": policy.max_rows,
        "timeout_seconds": policy.timeout_seconds,
        "sql": sql,
    }

    try:
        validated = validate_starrocks_readonly_sql(sql, policy)
    except StarRocksQueryError as exc:
        _append_evidence(
            evidence_path,
            {
                **evidence_base,
                "status": "rejected",
                "error": str(exc),
                "duration_ms": _duration_ms(started),
            },
        )
        raise

    try:
        query_rows = executor.execute(
            validated.sql,
            max_rows=policy.max_rows,
            timeout_seconds=policy.timeout_seconds,
        )
    except Exception as exc:
        _append_evidence(
            evidence_path,
            {
                **evidence_base,
                "status": "error",
                "statement_kind": validated.statement_kind,
                "error": f"{type(exc).__name__}: {exc}",
                "duration_ms": _duration_ms(started),
            },
        )
        if isinstance(exc, StarRocksQueryExecutionError):
            raise
        raise StarRocksQueryExecutionError(str(exc)) from exc

    filtered_rows = _filter_discovery_rows(validated.statement_kind, query_rows.rows, policy)
    truncated = len(filtered_rows) > policy.max_rows
    returned_rows = filtered_rows[: policy.max_rows]
    serialized_rows = [
        {column: _json_value(value) for column, value in zip(query_rows.columns, row)}
        for row in returned_rows
    ]
    result_hash = hashlib.sha256(
        json.dumps(serialized_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    duration_ms = _duration_ms(started)

    evidence = {
        **evidence_base,
        "status": "executed",
        "statement_kind": validated.statement_kind,
        "columns": query_rows.columns,
        "returned_row_count": len(serialized_rows),
        "truncated": truncated,
        "result_sha256": result_hash,
        "duration_ms": duration_ms,
    }
    if include_evidence_rows:
        evidence["rows"] = serialized_rows
    _append_evidence(evidence_path, evidence)

    return {
        "ok": True,
        "statement_kind": validated.statement_kind,
        "database": database,
        "columns": query_rows.columns,
        "rows": serialized_rows,
        "returned_row_count": len(serialized_rows),
        "truncated": truncated,
        "result_sha256": result_hash,
        "duration_ms": duration_ms,
        "evidence_path": str(evidence_path.resolve()),
    }


def validate_starrocks_readonly_sql(
    sql: str, policy: StarRocksQueryPolicy
) -> ValidatedQuery:
    statements = [statement.strip() for statement in sqlparse.split(sql) if statement.strip()]
    if not statements:
        raise StarRocksQueryError("SQL is empty.")
    if len(statements) != 1:
        raise StarRocksQueryError("Only one SQL statement is allowed.")

    normalized = statements[0]
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    first_keyword = _first_keyword(normalized)

    if first_keyword == "SHOW":
        return ValidatedQuery(normalized, _validate_show(normalized, policy))
    if first_keyword in {"DESCRIBE", "DESC"}:
        return ValidatedQuery(normalized, _validate_describe(normalized, policy))
    if first_keyword in {"SELECT", "WITH", "EXPLAIN"}:
        return ValidatedQuery(normalized, _validate_query_expression(normalized, first_keyword, policy))
    raise StarRocksQueryError("Only SHOW, DESCRIBE, SELECT, WITH, and EXPLAIN are allowed.")


def _validate_show(sql: str, policy: StarRocksQueryPolicy) -> str:
    collapsed = re.sub(r"\s+", " ", sql).strip()
    if re.fullmatch(r"SHOW CATALOGS(?: LIKE (?:'[^']*'|\"[^\"]*\"))?", collapsed, re.IGNORECASE):
        return "show_catalogs"

    databases = re.fullmatch(
        rf"SHOW (?:DATABASES|SCHEMAS)(?: FROM (?P<catalog>{_IDENTIFIER}))?"
        rf"(?: LIKE (?:'[^']*'|\"[^\"]*\"))?",
        collapsed,
        re.IGNORECASE,
    )
    if databases:
        if databases.group("catalog"):
            _check_catalog(databases.group("catalog"), policy)
        return "show_databases"

    tables = re.fullmatch(
        rf"SHOW (?:FULL )?TABLES(?: (?:FROM|IN) (?P<database>{_DATABASE_SCOPE}))?"
        rf"(?: LIKE (?:'[^']*'|\"[^\"]*\"))?",
        collapsed,
        re.IGNORECASE,
    )
    if tables:
        if tables.group("database"):
            _check_database_scope(tables.group("database"), policy)
        return "show_tables"

    metadata_patterns = [
        rf"SHOW (?:FULL )?COLUMNS (?:FROM|IN) (?P<target>{_QUALIFIED_IDENTIFIER})"
        rf"(?: (?:FROM|IN) (?P<database>{_IDENTIFIER}))?",
        rf"SHOW CREATE TABLE (?P<target>{_QUALIFIED_IDENTIFIER})",
        rf"SHOW (?:INDEX|INDEXES|KEYS) (?:FROM|IN) (?P<target>{_QUALIFIED_IDENTIFIER})",
        rf"SHOW PARTITIONS FROM (?P<target>{_QUALIFIED_IDENTIFIER})",
    ]
    for pattern in metadata_patterns:
        match = re.fullmatch(pattern, collapsed, re.IGNORECASE)
        if not match:
            continue
        target = match.groupdict().get("target")
        database = match.groupdict().get("database")
        if database:
            _check_database(database, policy)
        if target:
            _check_qualified_identifier(target, policy)
        return "show_metadata"

    raise StarRocksQueryError(
        "SHOW command is outside the discovery allowlist. Allowed forms cover catalogs, "
        "databases, tables, columns, create table, indexes, and partitions."
    )


def _validate_describe(sql: str, policy: StarRocksQueryPolicy) -> str:
    match = re.fullmatch(
        rf"(?:DESCRIBE|DESC)(?: TABLE)? (?P<target>{_QUALIFIED_IDENTIFIER})",
        re.sub(r"\s+", " ", sql).strip(),
        re.IGNORECASE,
    )
    if not match:
        raise StarRocksQueryError("DESCRIBE must target exactly one table.")
    _check_qualified_identifier(match.group("target"), policy)
    return "describe_table"


def _validate_query_expression(
    sql: str, first_keyword: str, policy: StarRocksQueryPolicy
) -> str:
    try:
        expression = sqlglot.parse_one(sql, read="mysql")
    except sqlglot.errors.ParseError as exc:
        raise StarRocksQueryError(f"SQL could not be safely parsed: {exc}") from exc

    query_expression: exp.Expression = expression
    if first_keyword == "EXPLAIN":
        if not isinstance(expression, exp.Describe) or not isinstance(expression.this, exp.Query):
            raise StarRocksQueryError("EXPLAIN is allowed only for a SELECT/WITH query.")
        query_expression = expression.this
    elif not isinstance(expression, exp.Query):
        raise StarRocksQueryError("Only read-only query expressions are allowed.")

    for function in query_expression.find_all(exp.Anonymous):
        if function.name.lower() in _BLOCKED_FUNCTIONS:
            raise StarRocksQueryError(f"Function {function.name} is not allowed.")

    for table in query_expression.find_all(exp.Table):
        catalog = table.catalog
        database = table.db
        if catalog:
            _check_catalog(catalog, policy)
        if database:
            if database.lower() == "information_schema" and not policy.allow_information_schema:
                raise StarRocksQueryError(
                    "Direct information_schema queries are disabled; use SHOW/DESCRIBE discovery commands."
                )
            if database.lower() != "information_schema":
                _check_database(database, policy)

    return "explain_query" if first_keyword == "EXPLAIN" else "select_query"


def _first_keyword(sql: str) -> str:
    parsed = sqlparse.parse(sql)
    if not parsed:
        return ""
    token = parsed[0].token_first(skip_ws=True, skip_cm=True)
    return token.normalized.upper().split()[0] if token else ""


def _check_qualified_identifier(identifier: str, policy: StarRocksQueryPolicy) -> None:
    parts = [_unquote_identifier(part.strip()) for part in identifier.split(".")]
    if len(parts) == 2:
        _check_database(parts[0], policy)
    elif len(parts) == 3:
        _check_catalog(parts[0], policy)
        _check_database(parts[1], policy)
    elif len(parts) != 1:
        raise StarRocksQueryError("Unsupported qualified identifier.")


def _check_database_scope(identifier: str, policy: StarRocksQueryPolicy) -> None:
    parts = [_unquote_identifier(part.strip()) for part in identifier.split(".")]
    if len(parts) == 1:
        _check_database(parts[0], policy)
    elif len(parts) == 2:
        _check_catalog(parts[0], policy)
        _check_database(parts[1], policy)
    else:
        raise StarRocksQueryError("Unsupported catalog/database scope.")


def _check_catalog(catalog: str, policy: StarRocksQueryPolicy) -> None:
    value = _unquote_identifier(catalog).lower()
    if value not in _normalized_set(policy.allowed_catalogs):
        raise StarRocksQueryError(f"Catalog is outside the allowlist: {value}")


def _check_database(database: str, policy: StarRocksQueryPolicy) -> None:
    value = _unquote_identifier(database).lower()
    if value not in _normalized_set(policy.allowed_databases):
        raise StarRocksQueryError(f"Database is outside the allowlist: {value}")


def _filter_discovery_rows(
    statement_kind: str,
    rows: list[tuple[Any, ...]],
    policy: StarRocksQueryPolicy,
) -> list[tuple[Any, ...]]:
    if statement_kind == "show_catalogs":
        allowed = _normalized_set(policy.allowed_catalogs)
    elif statement_kind == "show_databases":
        allowed = _normalized_set(policy.allowed_databases)
    else:
        return rows
    return [row for row in rows if row and str(row[0]).lower() in allowed]


def _normalized_set(values: tuple[str, ...]) -> set[str]:
    return {value.lower() for value in values}


def _unquote_identifier(value: str) -> str:
    return value[1:-1] if value.startswith("`") and value.endswith("`") else value


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _append_evidence(path: Path, record: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _duration_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
