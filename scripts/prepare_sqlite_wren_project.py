from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import yaml

try:
    from wren.type_mapping import parse_type as _wren_parse_type
except Exception:  # pragma: no cover - fallback for non-Wren developer envs
    _wren_parse_type = None


@dataclass
class Column:
    name: str
    raw_type: str
    wren_type: str
    not_null: bool
    primary_key_order: int


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)

    @property
    def primary_key(self) -> str | None:
        keys = sorted(
            [column for column in self.columns if column.primary_key_order > 0],
            key=lambda column: column.primary_key_order,
        )
        if len(keys) == 1:
            return keys[0].name
        return None


@dataclass
class Relationship:
    name: str
    child_table: str
    parent_table: str
    condition: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a local SQLite database into a DuckDB-backed Wren project."
    )
    parser.add_argument("--sqlite-path", required=True, help="Source .sqlite/.db file.")
    parser.add_argument("--output-dir", required=True, help="Output Wren project directory.")
    parser.add_argument(
        "--duckdb-path",
        default=None,
        help="Output .duckdb path. Defaults to <output-dir>/<project-name>.duckdb.",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="Wren project/profile name. Defaults to the SQLite filename stem.",
    )
    parser.add_argument(
        "--wren-home",
        default=None,
        help="WREN_HOME to update when --write-profile is passed.",
    )
    parser.add_argument(
        "--write-profile",
        action="store_true",
        help="Write/update a DuckDB profile in <wren-home>/profiles.yml.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs.")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path).resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    project_name = _safe_identifier(args.project_name or sqlite_path.stem)
    output_dir = Path(args.output_dir).resolve()
    duckdb_path = Path(args.duckdb_path).resolve() if args.duckdb_path else output_dir / f"{project_name}.duckdb"

    if output_dir.exists() and (output_dir / "wren_project.yml").exists() and not args.force:
        raise SystemExit(f"Wren project already exists: {output_dir}. Use --force to overwrite.")
    if duckdb_path.exists() and not args.force:
        raise SystemExit(f"DuckDB file already exists: {duckdb_path}. Use --force to overwrite.")

    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_duckdb_files(duckdb_path)

    tables, relationships = convert_sqlite_to_duckdb(sqlite_path, duckdb_path)
    files = generate_wren_project_files(
        tables=tables,
        relationships=relationships,
        project_name=project_name,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
    )
    _write_files(output_dir, files)

    if args.write_profile:
        if not args.wren_home:
            raise SystemExit("--wren-home is required with --write-profile")
        write_duckdb_profile(Path(args.wren_home).resolve(), project_name, duckdb_path)

    print(
        json.dumps(
            {
                "sqlite_path": str(sqlite_path),
                "duckdb_path": str(duckdb_path),
                "wren_project_dir": str(output_dir),
                "project_name": project_name,
                "models": [table.name for table in tables],
                "relationship_count": len(relationships),
                "profile_written": bool(args.write_profile),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def convert_sqlite_to_duckdb(sqlite_path: Path, duckdb_path: Path) -> tuple[list[Table], list[Relationship]]:
    sqlite_conn = sqlite3.connect(str(sqlite_path))
    duck_conn = duckdb.connect(str(duckdb_path))
    try:
        table_names = _sqlite_table_names(sqlite_conn)
        tables = [_introspect_table(sqlite_conn, table_name) for table_name in table_names]
        relationships = _introspect_relationships(sqlite_conn, table_names)
        if not _copy_with_duckdb_sqlite_scanner(duck_conn, sqlite_path, table_names):
            for table in tables:
                _create_duckdb_table(duck_conn, table)
                _copy_table_rows(sqlite_conn, duck_conn, table)
        _checkpoint_duckdb(duck_conn)
        return tables, relationships
    finally:
        sqlite_conn.close()
        duck_conn.close()


def generate_wren_project_files(
    *,
    tables: list[Table],
    relationships: list[Relationship],
    project_name: str,
    sqlite_path: Path,
    duckdb_path: Path,
) -> dict[str, str]:
    catalog = duckdb_path.stem
    files: dict[str, str] = {
        "wren_project.yml": yaml.safe_dump(
            {
                "schema_version": 5,
                "name": project_name,
                "version": "0.1",
                "catalog": "wren",
                "schema": "public",
                "data_source": "duckdb",
                "profile": project_name,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        "knowledge/knowledge.yml": "schema_version: 1\n",
        "knowledge/rules/general.md": _project_rules(project_name, sqlite_path, duckdb_path, tables, relationships),
        "relationships.yml": yaml.safe_dump(
            {"relationships": [_relationship_to_yaml(item) for item in relationships]},
            sort_keys=False,
            allow_unicode=True,
        ),
    }

    for table in tables:
        model = {
            "name": table.name,
            "table_reference": {
                "catalog": catalog,
                "schema": "main",
                "table": table.name,
            },
            "columns": [_column_to_yaml(column) for column in table.columns],
            "cached": False,
            "properties": {
                "description": f"Table imported from SQLite source {sqlite_path.name}.",
            },
        }
        if table.primary_key:
            model["primary_key"] = table.primary_key
        files[f"models/{_safe_path_segment(table.name)}/metadata.yml"] = yaml.safe_dump(
            model,
            sort_keys=False,
            allow_unicode=True,
        )
    return files


def write_duckdb_profile(wren_home: Path, profile_name: str, duckdb_path: Path) -> None:
    profiles_path = wren_home / "profiles.yml"
    wren_home.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if profiles_path.exists():
        loaded = yaml.safe_load(profiles_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded
    existing.setdefault("profiles", {})
    existing["active"] = profile_name
    existing["profiles"][profile_name] = {
        "datasource": "duckdb",
        "url": str(duckdb_path.parent),
        "format": "duckdb",
    }
    profiles_path.write_text(
        yaml.safe_dump(existing, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _sqlite_table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def _introspect_table(conn: sqlite3.Connection, table_name: str) -> Table:
    rows = conn.execute(f"PRAGMA table_info({_quote_sqlite_string(table_name)})").fetchall()
    columns = [
        Column(
            name=str(row[1]),
            raw_type=str(row[2] or ""),
            wren_type=_sqlite_type_to_wren(str(row[2] or "")),
            not_null=bool(row[3]) or int(row[5] or 0) > 0,
            primary_key_order=int(row[5] or 0),
        )
        for row in rows
    ]
    if not columns:
        raise ValueError(f"Table has no columns: {table_name}")
    return Table(name=table_name, columns=columns)


def _introspect_relationships(conn: sqlite3.Connection, table_names: list[str]) -> list[Relationship]:
    relationships: list[Relationship] = []
    for child_table in table_names:
        rows = conn.execute(f"PRAGMA foreign_key_list({_quote_sqlite_string(child_table)})").fetchall()
        grouped: dict[int, list[sqlite3.Row | tuple[Any, ...]]] = {}
        for row in rows:
            grouped.setdefault(int(row[0]), []).append(row)
        for fk_id, fk_rows in grouped.items():
            parent_table = str(fk_rows[0][2])
            sorted_fk_rows = sorted(fk_rows, key=lambda item: int(item[1]))
            if any(row[3] is None or row[4] is None for row in sorted_fk_rows):
                continue
            conditions = [
                f'"{child_table}"."{row[3]}" = "{parent_table}"."{row[4]}"'
                for row in sorted_fk_rows
            ]
            relationships.append(
                Relationship(
                    name=_safe_identifier(f"{child_table}_to_{parent_table}_{fk_id}"),
                    child_table=child_table,
                    parent_table=parent_table,
                    condition=" AND ".join(conditions),
                )
            )
    return relationships


def _create_duckdb_table(conn: duckdb.DuckDBPyConnection, table: Table) -> None:
    column_defs = ", ".join(
        f"{_quote_identifier(column.name)} {column.wren_type}" for column in table.columns
    )
    conn.execute(f"CREATE TABLE {_quote_identifier(table.name)} ({column_defs})")


def _copy_table_rows(
    sqlite_conn: sqlite3.Connection,
    duck_conn: duckdb.DuckDBPyConnection,
    table: Table,
    chunk_size: int = 1000,
) -> None:
    columns = [_quote_identifier(column.name) for column in table.columns]
    select_sql = f"SELECT {', '.join(columns)} FROM {_quote_identifier(table.name)}"
    insert_sql = (
        f"INSERT INTO {_quote_identifier(table.name)} ({', '.join(columns)}) "
        f"VALUES ({', '.join(['?'] * len(columns))})"
    )
    cursor = sqlite_conn.execute(select_sql)
    while True:
        rows = cursor.fetchmany(chunk_size)
        if not rows:
            break
        duck_conn.executemany(insert_sql, rows)


def _copy_with_duckdb_sqlite_scanner(
    duck_conn: duckdb.DuckDBPyConnection,
    sqlite_path: Path,
    table_names: list[str],
) -> bool:
    """Use DuckDB's SQLite scanner when available; fall back if extension load fails."""
    try:
        extension_dir = (Path("data") / "duckdb_extensions").resolve()
        extension_dir.mkdir(parents=True, exist_ok=True)
        duck_conn.execute(f"SET extension_directory = {_quote_sql_string(str(extension_dir))}")
        duck_conn.execute("INSTALL sqlite_scanner")
        duck_conn.execute("LOAD sqlite_scanner")
        duck_conn.execute(
            f"ATTACH {_quote_sql_string(str(sqlite_path))} AS sqlite_source (TYPE sqlite)"
        )
        for table_name in table_names:
            duck_conn.execute(
                "CREATE TABLE "
                f"{_quote_identifier(table_name)} AS "
                f"SELECT * FROM sqlite_source.{_quote_identifier(table_name)}"
            )
        duck_conn.execute("DETACH sqlite_source")
        return True
    except Exception:
        return False


def _column_to_yaml(column: Column) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": column.name,
        "type": column.wren_type,
        "is_calculated": False,
        "not_null": column.not_null,
        "properties": {
            "source_type": column.raw_type,
        },
    }
    if column.primary_key_order == 1:
        data["is_primary_key"] = True
    return data


def _relationship_to_yaml(relationship: Relationship) -> dict[str, Any]:
    return {
        "name": relationship.name,
        "models": [relationship.child_table, relationship.parent_table],
        "join_type": "MANY_TO_ONE",
        "condition": relationship.condition,
        "properties": {"source": "sqlite_foreign_key"},
    }


def _project_rules(
    project_name: str,
    sqlite_path: Path,
    duckdb_path: Path,
    tables: list[Table],
    relationships: list[Relationship],
) -> str:
    generated = datetime.now(timezone.utc).isoformat()
    return (
        "# Project rules\n\n"
        f"This Wren project was generated for `{project_name}` from a local SQLite database.\n\n"
        f"- Source SQLite: `{sqlite_path}`\n"
        f"- Runtime DuckDB: `{duckdb_path}`\n"
        f"- Generated At: `{generated}`\n"
        f"- Tables: {len(tables)}\n"
        f"- Relationships: {len(relationships)}\n\n"
        "Use read-only analytical SQL. The DuckDB file is the runtime source queried by Wren.\n"
    )


def _sqlite_type_to_wren(raw_type: str) -> str:
    if _wren_parse_type is not None:
        parsed = _wren_parse_type(raw_type.strip(), "sqlite").strip()
        if parsed:
            return parsed
        return "TEXT"
    return _fallback_sqlite_type_to_wren(raw_type)


def _fallback_sqlite_type_to_wren(raw_type: str) -> str:
    normalized = raw_type.strip().upper()
    if not normalized:
        return "TEXT"
    if "INT" in normalized:
        return "BIGINT"
    if any(token in normalized for token in ("CHAR", "CLOB", "TEXT", "VARCHAR")):
        return "TEXT"
    if any(token in normalized for token in ("REAL", "FLOA", "DOUB")):
        return "DOUBLE"
    if "BOOL" in normalized:
        return "BOOLEAN"
    if "DATE" in normalized and "TIME" not in normalized:
        return "DATE"
    if "TIME" in normalized:
        return "TIMESTAMP"
    if any(token in normalized for token in ("NUM", "DEC", "MONEY")):
        return "DOUBLE"
    if "BLOB" in normalized:
        return "BLOB"
    return "TEXT"


def _write_files(output_dir: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = output_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_")
    return cleaned or "wren_project"


def _safe_path_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value).strip("._")
    if not cleaned:
        raise ValueError(f"Invalid path segment from identifier: {value!r}")
    return cleaned


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _quote_sqlite_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _remove_duckdb_files(duckdb_path: Path) -> None:
    for path in (duckdb_path, duckdb_path.with_name(f"{duckdb_path.name}.wal")):
        if path.exists():
            path.unlink()


def _checkpoint_duckdb(conn: duckdb.DuckDBPyConnection) -> None:
    try:
        conn.execute("CHECKPOINT")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
