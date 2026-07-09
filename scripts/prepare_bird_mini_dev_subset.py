from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a local BIRD Mini-Dev JSON file into Data Subagent eval JSONL."
    )
    parser.add_argument("--input", required=True, help="Path to BIRD Mini-Dev JSON file.")
    parser.add_argument("--output", required=True, help="Output eval JSONL path.")
    parser.add_argument("--db-id", default=None, help="Only include records for this db_id.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of cases to emit.")
    parser.add_argument(
        "--include-non-select",
        action="store_true",
        help="Include non-SELECT gold SQL. By default only SELECT/WITH SQL is emitted.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    records = _load_records(input_path)

    emitted = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for index, record in enumerate(records, start=1):
            db_id = str(record.get("db_id") or record.get("database_id") or "").strip()
            if args.db_id and db_id != args.db_id:
                continue

            gold_sql = str(record.get("SQL") or record.get("sql") or record.get("query") or "").strip()
            if not args.include_non_select and not _is_readonly_sql(gold_sql):
                continue

            question = str(record.get("question") or record.get("Question") or "").strip()
            if not question:
                continue

            eval_case = {
                "eval_id": _eval_id(db_id, index),
                "dataset": "bird_mini_dev",
                "db_id": db_id or "unknown",
                "question": question,
                "evidence": str(record.get("evidence") or record.get("Evidence") or "").strip(),
                "gold_sql": gold_sql,
                "expected_status": "success",
                "expected_sql_contains": _expected_sql_fragments(gold_sql),
            }
            file.write(json.dumps(eval_case, ensure_ascii=False) + "\n")
            emitted += 1
            if args.limit and emitted >= args.limit:
                break

    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output_path),
                "db_id": args.db_id,
                "emitted": emitted,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _load_records(path: Path) -> list[dict[str, Any]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    if isinstance(loaded, dict):
        for key in ("data", "records", "examples"):
            value = loaded.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError(f"Unsupported BIRD JSON shape: {path}")


def _is_readonly_sql(sql: str) -> bool:
    lowered = sql.strip().lower()
    return lowered.startswith("select") or lowered.startswith("with")


def _expected_sql_fragments(gold_sql: str) -> list[str]:
    lowered = gold_sql.lower()
    fragments = ["select"]
    for keyword in ("join", "group by", "order by", "limit", "count", "sum", "avg", "max", "min"):
        if keyword in lowered:
            fragments.append(keyword)
    return fragments


def _eval_id(db_id: str, index: int) -> str:
    safe_db = "".join(char if char.isalnum() or char in "-_" else "_" for char in (db_id or "unknown"))
    return f"bird_{safe_db}_{index:04d}"


if __name__ == "__main__":
    main()
