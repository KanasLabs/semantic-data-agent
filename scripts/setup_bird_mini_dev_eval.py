from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_DB_ID = "debit_card_specializing"
DATASET_REPO = "birdsql/bird_mini_dev"
OSS_MINIDEV_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a local BIRD Mini-Dev SQLite subset for Data Subagent eval."
    )
    parser.add_argument(
        "--source-dir",
        default="data/external/bird_mini_dev/raw",
        help="Directory containing BIRD Mini-Dev files, or target directory for --download.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download birdsql/bird_mini_dev from Hugging Face before preparing.",
    )
    parser.add_argument(
        "--download-url",
        default=None,
        help="Download and extract a zip package before preparing, for example the BIRD Mini-Dev OSS URL.",
    )
    parser.add_argument(
        "--download-oss",
        action="store_true",
        help=f"Shortcut for --download-url {OSS_MINIDEV_URL}",
    )
    parser.add_argument(
        "--db-id",
        default=None,
        help=f"Database id to prepare. Defaults to {DEFAULT_DB_ID!r} when present.",
    )
    parser.add_argument("--limit", type=int, default=30, help="Maximum SELECT-only cases to emit.")
    parser.add_argument(
        "--eval-output",
        default=None,
        help="Output eval JSONL path. Defaults to data/evals/cases/bird_mini_dev_<db_id>.jsonl.",
    )
    parser.add_argument(
        "--wren-output-dir",
        default=None,
        help="Output Wren project directory. Defaults to data/wren/bird_<db_id>_wren_project.",
    )
    parser.add_argument(
        "--duckdb-path",
        default=None,
        help="Output DuckDB path. Defaults to data/wren/bird_<db_id>.duckdb.",
    )
    parser.add_argument("--wren-home", default="data/wren/home")
    parser.add_argument("--skip-wren-project", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    if args.download:
        source_dir = download_hf_snapshot(source_dir)
    if args.download_url or args.download_oss:
        source_dir = download_zip_package(
            args.download_url or OSS_MINIDEV_URL,
            source_dir,
            force=args.force,
        )

    records_path = find_records_file(source_dir)
    records = load_records(records_path)
    db_id = choose_db_id(records, args.db_id)
    sqlite_path = find_sqlite_database(source_dir, db_id)

    eval_output = Path(args.eval_output or f"data/evals/cases/bird_mini_dev_{db_id}.jsonl").resolve()
    emitted = write_eval_subset(records, eval_output, db_id=db_id, limit=args.limit)

    wren_project_dir = None
    duckdb_path = None
    if not args.skip_wren_project:
        wren_project_dir = Path(args.wren_output_dir or f"data/wren/bird_{db_id}_wren_project").resolve()
        duckdb_path = Path(args.duckdb_path or f"data/wren/bird_{db_id}.duckdb").resolve()
        prepare_sqlite = _load_script("prepare_sqlite_wren_project.py")
        duckdb_wal_path = duckdb_path.with_name(f"{duckdb_path.name}.wal")
        if duckdb_path.exists() or duckdb_wal_path.exists():
            if not args.force:
                raise SystemExit(f"DuckDB file already exists: {duckdb_path}. Use --force to overwrite.")
            prepare_sqlite._remove_duckdb_files(duckdb_path)
        tables, relationships = prepare_sqlite.convert_sqlite_to_duckdb(sqlite_path, duckdb_path)
        files = prepare_sqlite.generate_wren_project_files(
            tables=tables,
            relationships=relationships,
            project_name=f"bird_{db_id}",
            sqlite_path=sqlite_path,
            duckdb_path=duckdb_path,
        )
        if (wren_project_dir / "wren_project.yml").exists() and not args.force:
            raise SystemExit(f"Wren project already exists: {wren_project_dir}. Use --force to overwrite.")
        prepare_sqlite._write_files(wren_project_dir, files)
        prepare_sqlite.write_duckdb_profile(Path(args.wren_home).resolve(), f"bird_{db_id}", duckdb_path)

    print(
        json.dumps(
            {
                "source_dir": str(source_dir),
                "records_path": str(records_path),
                "db_id": db_id,
                "sqlite_path": str(sqlite_path),
                "eval_output": str(eval_output),
                "emitted": emitted,
                "wren_project_dir": str(wren_project_dir) if wren_project_dir else None,
                "duckdb_path": str(duckdb_path) if duckdb_path else None,
                "next_eval_command": _next_eval_command(
                    eval_output,
                    wren_project_dir,
                    Path(args.wren_home).resolve(),
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def download_hf_snapshot(target_dir: Path) -> Path:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is required for --download. Install it or provide --source-dir."
        ) from exc

    target_dir.mkdir(parents=True, exist_ok=True)
    return Path(
        snapshot_download(
            repo_id=DATASET_REPO,
            repo_type="dataset",
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
        )
    ).resolve()


def download_zip_package(url: str, target_dir: Path, *, force: bool = False) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / Path(url.split("?", 1)[0]).name
    if zip_path.exists() and not force:
        raise SystemExit(f"Zip already exists: {zip_path}. Use --force to re-download.")
    if zip_path.exists() and force:
        zip_path.unlink()

    urllib.request.urlretrieve(url, zip_path)
    extract_dir = target_dir / zip_path.stem
    if extract_dir.exists() and not force:
        raise SystemExit(f"Extract directory already exists: {extract_dir}. Use --force to overwrite.")
    if extract_dir.exists() and force:
        _remove_tree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)
    return extract_dir.resolve()


def find_records_file(source_dir: Path) -> Path:
    if not source_dir.exists():
        raise FileNotFoundError(f"BIRD source directory not found: {source_dir}")
    candidates = sorted(source_dir.rglob("mini_dev_sqlite.json"))
    if not candidates:
        candidates = sorted(source_dir.rglob("*mini*sqlite*.json"))
    if candidates:
        return candidates[0]

    parquet_candidates = sorted(source_dir.rglob("*mini*sqlite*.parquet"))
    if parquet_candidates:
        return parquet_candidates[0]

    raise FileNotFoundError(
        f"Could not find mini_dev_sqlite JSON/parquet under {source_dir}. "
        "Expected files such as mini_dev_sqlite.json or mini_dev_sqlite*.parquet."
    )


def load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".parquet":
        return _load_parquet_records(path)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    if isinstance(loaded, dict):
        for key in ("data", "records", "examples"):
            value = loaded.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError(f"Unsupported records shape: {path}")


def choose_db_id(records: list[dict[str, Any]], requested: str | None = None) -> str:
    counter = Counter(str(record.get("db_id") or record.get("database_id") or "").strip() for record in records)
    counter.pop("", None)
    if requested:
        if requested not in counter:
            available = ", ".join(db_id for db_id, _ in counter.most_common(10))
            raise ValueError(f"db_id {requested!r} not found. Top available db_id values: {available}")
        return requested
    if DEFAULT_DB_ID in counter:
        return DEFAULT_DB_ID
    if not counter:
        raise ValueError("No db_id values found in BIRD records.")
    return counter.most_common(1)[0][0]


def find_sqlite_database(source_dir: Path, db_id: str) -> Path:
    suffixes = {".sqlite", ".sqlite3", ".db"}
    candidates = [path for path in source_dir.rglob("*") if path.is_file() and path.suffix.lower() in suffixes]
    if not candidates:
        raise FileNotFoundError(f"No SQLite database files found under {source_dir}")

    exact = [
        path
        for path in candidates
        if path.stem == db_id or path.parent.name == db_id or db_id in path.parts
    ]
    if exact:
        return sorted(exact, key=lambda path: (path.stem != db_id, len(str(path))))[0]

    fuzzy = [path for path in candidates if db_id.lower() in str(path).lower()]
    if fuzzy:
        return sorted(fuzzy, key=lambda path: len(str(path)))[0]

    sample = ", ".join(str(path.relative_to(source_dir)) for path in candidates[:10])
    raise FileNotFoundError(f"No SQLite database matched db_id {db_id!r}. Sample files: {sample}")


def write_eval_subset(
    records: list[dict[str, Any]],
    output_path: Path,
    *,
    db_id: str,
    limit: int | None,
) -> int:
    bird_converter = _load_script("prepare_bird_mini_dev_subset.py")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    emitted = 0
    with output_path.open("w", encoding="utf-8") as file:
        for index, record in enumerate(records, start=1):
            record_db_id = str(record.get("db_id") or record.get("database_id") or "").strip()
            if record_db_id != db_id:
                continue
            gold_sql = str(record.get("SQL") or record.get("sql") or record.get("query") or "").strip()
            if not bird_converter._is_readonly_sql(gold_sql):
                continue
            question = str(record.get("question") or record.get("Question") or "").strip()
            if not question:
                continue
            eval_case = {
                "eval_id": bird_converter._eval_id(record_db_id, index),
                "dataset": "bird_mini_dev",
                "db_id": record_db_id,
                "question": question,
                "evidence": str(record.get("evidence") or record.get("Evidence") or "").strip(),
                "gold_sql": gold_sql,
                "expected_status": "success",
                "expected_sql_contains": bird_converter._expected_sql_fragments(gold_sql),
            }
            file.write(json.dumps(eval_case, ensure_ascii=False) + "\n")
            emitted += 1
            if limit and emitted >= limit:
                break
    if emitted == 0:
        raise ValueError(f"No SELECT-only cases emitted for db_id {db_id!r}")
    return emitted


def _load_parquet_records(path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit(
            f"Parquet records found at {path}, but pyarrow is not installed. "
            "Install pyarrow or provide mini_dev_sqlite.json."
        ) from exc
    table = pq.read_table(path)
    return [dict(row) for row in table.to_pylist() if isinstance(row, dict)]


def _load_script(filename: str):
    script_path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _remove_tree(path: Path) -> None:
    for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    path.rmdir()


def _next_eval_command(eval_output: Path, wren_project_dir: Path | None, wren_home: Path) -> str:
    parts = [
        "$env:PYTHONPATH='src';",
        ".\\.venv-wren\\python.exe -m data_subagent.cli eval",
        f"--suite {eval_output}",
        "--suite-name bird_mini_dev_subset",
    ]
    if wren_project_dir:
        parts.append(f"--wren-project-dir {wren_project_dir}")
        parts.append(f"--wren-home {wren_home}")
    return " ".join(parts)


if __name__ == "__main__":
    main()
