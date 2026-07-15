from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Protocol

import yaml

from .report import write_onboarding_report
from .wren_cli import CommandResult, WrenCliRunner


class WrenRunner(Protocol):
    def run(self, args: list[str]) -> CommandResult:
        ...


def generate_from_sqlite(
    *,
    sqlite_path: Path,
    project_name: str,
    project_dir: Path,
    duckdb_path: Path,
    wren_home: Path,
    wren_bin: Path,
    smoke_sql: str | None = None,
    report_path: Path | None = None,
    force: bool = False,
    timeout_seconds: int = 60,
    runner: WrenRunner | None = None,
) -> dict[str, Any]:
    prepare_sqlite = _load_prepare_sqlite_script()
    sqlite_path = sqlite_path.resolve()
    project_dir = project_dir.resolve()
    duckdb_path = duckdb_path.resolve()
    wren_home = wren_home.resolve()
    wren_bin = wren_bin.resolve()

    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    if (project_dir / "wren_project.yml").exists() and not force:
        raise FileExistsError(f"Wren project already exists: {project_dir}. Use --force.")
    if (duckdb_path.exists() or duckdb_path.with_name(f"{duckdb_path.name}.wal").exists()) and not force:
        raise FileExistsError(f"DuckDB file already exists: {duckdb_path}. Use --force.")

    project_dir.mkdir(parents=True, exist_ok=True)
    active_runner = runner or WrenCliRunner(
        wren_bin=wren_bin,
        project_dir=project_dir,
        wren_home=wren_home,
        timeout_seconds=timeout_seconds,
    )
    init_args = ["context", "init", "--path", str(project_dir), "--empty"]
    if force:
        init_args.append("--force")
    context_init = active_runner.run(init_args)

    prepare_sqlite._remove_duckdb_files(duckdb_path)
    tables, relationships = prepare_sqlite.convert_sqlite_to_duckdb(sqlite_path, duckdb_path)
    files = prepare_sqlite.generate_wren_project_files(
        tables=tables,
        relationships=relationships,
        project_name=project_name,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
    )
    prepare_sqlite._write_files(project_dir, files)
    prepare_sqlite.write_duckdb_profile(wren_home, project_name, duckdb_path)

    result = _base_result(
        project_name=project_name,
        source=sqlite_path,
        project_dir=project_dir,
        duckdb_path=duckdb_path,
        wren_home=wren_home,
        tables=tables,
        relationships=relationships,
    )
    result["wren_commands"] = {
        "context_init": context_init.to_dict(),
        **_run_validation_commands(active_runner, smoke_sql=smoke_sql),
    }
    result["ok"] = all(command["returncode"] == 0 for command in result["wren_commands"].values())

    if report_path:
        write_onboarding_report(report_path.resolve(), result)
        result["report_path"] = str(report_path.resolve())
    return result


def validate_project(
    *,
    project_name: str | None,
    project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    smoke_sql: str | None = None,
    report_path: Path | None = None,
    timeout_seconds: int = 60,
    runner: WrenRunner | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    wren_home = wren_home.resolve()
    wren_bin = wren_bin.resolve()
    active_runner = runner or WrenCliRunner(
        wren_bin=wren_bin,
        project_dir=project_dir,
        wren_home=wren_home,
        timeout_seconds=timeout_seconds,
    )
    project_summary = _project_summary(project_dir)
    result: dict[str, Any] = {
        "ok": False,
        "project_name": project_name or project_dir.name,
        "source": "existing_wren_project",
        "wren_project_dir": str(project_dir),
        "duckdb_path": None,
        "wren_home": str(wren_home),
        "models": project_summary["models"],
        "relationship_count": project_summary["relationship_count"],
        "wren_commands": _run_validation_commands(active_runner, smoke_sql=smoke_sql),
    }
    result["ok"] = all(command["returncode"] == 0 for command in result["wren_commands"].values())
    if report_path:
        write_onboarding_report(report_path.resolve(), result)
        result["report_path"] = str(report_path.resolve())
    return result


def _project_summary(project_dir: Path) -> dict[str, Any]:
    models: list[str] = []
    for path in sorted((project_dir / "models").glob("*/metadata.yml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and loaded.get("name"):
            models.append(str(loaded["name"]))
    relationship_count = 0
    relationships_path = project_dir / "relationships.yml"
    if relationships_path.exists():
        loaded = yaml.safe_load(relationships_path.read_text(encoding="utf-8"))
        relationships = loaded.get("relationships") if isinstance(loaded, dict) else loaded
        if isinstance(relationships, list):
            relationship_count = len(relationships)
    return {"models": models, "relationship_count": relationship_count}


def _run_validation_commands(runner: WrenRunner, *, smoke_sql: str | None) -> dict[str, dict[str, object]]:
    commands = {
        "context_validate": runner.run(["context", "validate"]).to_dict(),
        "context_build": runner.run(["context", "build"]).to_dict(),
    }
    if smoke_sql:
        commands["dry_run"] = runner.run(["dry-run", "--sql", smoke_sql]).to_dict()
    return commands


def _base_result(
    *,
    project_name: str,
    source: Path,
    project_dir: Path,
    duckdb_path: Path,
    wren_home: Path,
    tables: list[Any],
    relationships: list[Any],
) -> dict[str, Any]:
    return {
        "ok": False,
        "project_name": project_name,
        "source": str(source),
        "wren_project_dir": str(project_dir),
        "duckdb_path": str(duckdb_path),
        "wren_home": str(wren_home),
        "models": [table.name for table in tables],
        "relationship_count": len(relationships),
    }


def _load_prepare_sqlite_script():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "prepare_sqlite_wren_project.py"
    spec = importlib.util.spec_from_file_location("prepare_sqlite_wren_project", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
