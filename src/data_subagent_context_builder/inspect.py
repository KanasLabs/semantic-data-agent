from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def inspect_sqlite_schema(
    *,
    sqlite_path: Path,
    project_name: str | None = None,
    report_path: Path | None = None,
    json_output_path: Path | None = None,
) -> dict[str, Any]:
    prepare_sqlite = _load_prepare_sqlite_script()
    sqlite_path = sqlite_path.resolve()
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    conn = sqlite3.connect(str(sqlite_path))
    try:
        table_names = prepare_sqlite._sqlite_table_names(conn)
        tables = [prepare_sqlite._introspect_table(conn, table_name) for table_name in table_names]
        relationships = prepare_sqlite._introspect_relationships(conn, table_names)
        raw_fk_warnings = _invalid_sqlite_fk_warnings(conn, table_names)
    finally:
        conn.close()

    result = _schema_report(
        project_name=project_name or prepare_sqlite._safe_identifier(sqlite_path.stem),
        sqlite_path=sqlite_path,
        tables=tables,
        relationships=relationships,
        extra_warnings=raw_fk_warnings,
    )
    if json_output_path:
        json_output_path = json_output_path.resolve()
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["json_output_path"] = str(json_output_path)
    if report_path:
        report_path = report_path.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(_render_markdown_report(result), encoding="utf-8")
        result["report_path"] = str(report_path)
    return result


def _schema_report(
    *,
    project_name: str,
    sqlite_path: Path,
    tables: list[Any],
    relationships: list[Any],
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    relationship_warnings = [*_relationship_warnings(relationships), *(extra_warnings or [])]
    return {
        "ok": not relationship_warnings,
        "project_name": project_name,
        "source": {
            "type": "sqlite",
            "path": str(sqlite_path),
        },
        "inspected_at": datetime.now(timezone.utc).isoformat(),
        "table_count": len(tables),
        "relationship_count": len(relationships),
        "tables": [
            {
                "name": table.name,
                "primary_key": table.primary_key,
                "column_count": len(table.columns),
                "columns": [
                    {
                        "name": column.name,
                        "raw_type": column.raw_type,
                        "normalized_type": column.wren_type,
                        "not_null": column.not_null,
                        "primary_key_order": column.primary_key_order,
                    }
                    for column in table.columns
                ],
            }
            for table in tables
        ],
        "relationships": [
            {
                "name": relationship.name,
                "child_table": relationship.child_table,
                "parent_table": relationship.parent_table,
                "condition": relationship.condition,
                "source": "sqlite_foreign_key",
            }
            for relationship in relationships
        ],
        "warnings": relationship_warnings,
        "notes": [
            "This is a schema inspection report, not finished Wren MDL.",
            "Use it as factual input for Wren generate-mdl onboarding or manual semantic review.",
        ],
    }


def _relationship_warnings(relationships: list[Any]) -> list[str]:
    warnings: list[str] = []
    for relationship in relationships:
        condition = str(relationship.condition)
        if '"None"' in condition or ".None" in condition:
            warnings.append(
                f"Relationship {relationship.name} has an invalid-looking join condition: {condition}"
            )
        if not condition.strip():
            warnings.append(f"Relationship {relationship.name} has an empty join condition.")
    return warnings


def _invalid_sqlite_fk_warnings(conn: sqlite3.Connection, table_names: list[str]) -> list[str]:
    warnings: list[str] = []
    for child_table in table_names:
        rows = conn.execute(f"PRAGMA foreign_key_list({_quote_sqlite_string(child_table)})").fetchall()
        for row in rows:
            parent_table = row[2]
            child_column = row[3]
            parent_column = row[4]
            if child_column is None or parent_column is None:
                warnings.append(
                    "SQLite foreign key metadata is incomplete for "
                    f"{child_table} -> {parent_table}: "
                    f"child_column={child_column!r}, parent_column={parent_column!r}. "
                    "Context Builder will not generate this relationship automatically."
                )
    return warnings


def _render_markdown_report(result: dict[str, Any]) -> str:
    tables = result.get("tables") or []
    relationships = result.get("relationships") or []
    warnings = result.get("warnings") or []
    sections = [
        "# SQLite Schema Inspection Report",
        "",
        f"Generated at: {result.get('inspected_at')}",
        "",
        "## Summary",
        "",
        f"- Status: {'OK' if result.get('ok') else 'WARNINGS'}",
        f"- Project name: `{result.get('project_name')}`",
        f"- Source: `{(result.get('source') or {}).get('path')}`",
        f"- Tables: {result.get('table_count')}",
        f"- Relationships: {result.get('relationship_count')}",
        "",
        "## Tables",
        "",
    ]
    if tables:
        for table in tables:
            sections.extend(
                [
                    f"### {table.get('name')}",
                    "",
                    f"- Primary key: `{table.get('primary_key')}`",
                    f"- Columns: {table.get('column_count')}",
                    "",
                    "| Column | Raw Type | Wren Type | Not Null | PK Order |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for column in table.get("columns", []):
                sections.append(
                    "| "
                    f"`{column.get('name')}` | "
                    f"`{column.get('raw_type')}` | "
                    f"`{column.get('normalized_type')}` | "
                    f"{column.get('not_null')} | "
                    f"{column.get('primary_key_order')} |"
                )
            sections.append("")
    else:
        sections.extend(["No tables found.", ""])

    sections.extend(["## Relationships", ""])
    if relationships:
        for relationship in relationships:
            sections.extend(
                [
                    f"- `{relationship.get('name')}`: "
                    f"`{relationship.get('child_table')}` -> `{relationship.get('parent_table')}`",
                    f"  - condition: `{relationship.get('condition')}`",
                ]
            )
    else:
        sections.append("No relationships found.")

    sections.extend(["", "## Warnings", ""])
    sections.extend([f"- {warning}" for warning in warnings] or ["No warnings."])
    sections.extend(
        [
            "",
            "## Notes",
            "",
            "- This report is schema evidence for Context Builder onboarding.",
            "- It does not imply business-ready semantics, metrics, synonyms, or examples.",
            "",
        ]
    )
    return "\n".join(sections)


def _load_prepare_sqlite_script():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "prepare_sqlite_wren_project.py"
    spec = importlib.util.spec_from_file_location("prepare_sqlite_wren_project", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _quote_sqlite_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
