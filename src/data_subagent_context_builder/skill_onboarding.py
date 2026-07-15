from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml

from .codex_runtime import (
    CodexCliRunner,
    build_codex_generate_mdl_repair_prompt,
    prepare_codex_generate_mdl,
)
from .report import write_onboarding_report
from .wren_cli import CommandResult, WrenCliRunner


class WrenRunner(Protocol):
    def run(self, args: list[str]) -> CommandResult:
        ...


def prepare_sqlite_skill_onboarding(
    *,
    sqlite_path: Path,
    project_name: str,
    project_dir: Path,
    duckdb_path: Path,
    wren_home: Path,
    wren_bin: Path,
    project_root: Path,
    smoke_sql: str | None = None,
    extra_instructions: str | None = None,
    prompt_output_path: Path | None = None,
    execute_codex: bool = False,
    force: bool = False,
    timeout_seconds: int = 60,
    codex_bin: str = "codex",
    codex_model: str | None = None,
    codex_last_message_path: Path | None = None,
    codex_timeout_seconds: int = 900,
    max_repair_rounds: int = 2,
    post_validate: bool = True,
    report_path: Path | None = None,
    wren_runner: WrenRunner | None = None,
    codex_runner: CodexCliRunner | None = None,
) -> dict[str, Any]:
    prepare_sqlite = _load_prepare_sqlite_script()
    sqlite_path = sqlite_path.resolve()
    project_dir = project_dir.resolve()
    duckdb_path = duckdb_path.resolve()
    wren_home = wren_home.resolve()
    wren_bin = wren_bin.resolve()
    project_root = project_root.resolve()

    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    if (project_dir / "wren_project.yml").exists() and not force:
        raise FileExistsError(f"Wren project already exists: {project_dir}. Use --force.")
    if (duckdb_path.exists() or duckdb_path.with_name(f"{duckdb_path.name}.wal").exists()) and not force:
        raise FileExistsError(f"DuckDB file already exists: {duckdb_path}. Use --force.")

    project_dir.mkdir(parents=True, exist_ok=True)
    active_wren_runner = wren_runner or WrenCliRunner(
        wren_bin=wren_bin,
        project_dir=project_dir,
        wren_home=wren_home,
        timeout_seconds=timeout_seconds,
    )
    init_args = ["context", "init", "--path", str(project_dir), "--empty"]
    if force:
        init_args.append("--force")
    context_init = active_wren_runner.run(init_args)

    prepare_sqlite._remove_duckdb_files(duckdb_path)
    tables, relationships = prepare_sqlite.convert_sqlite_to_duckdb(sqlite_path, duckdb_path)
    prepare_sqlite.write_duckdb_profile(wren_home, project_name, duckdb_path)

    manifest_path = project_dir / "onboarding" / "schema_manifest.json"
    manifest = _schema_manifest(
        project_name=project_name,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        tables=tables,
        relationships=relationships,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    codex_result = prepare_codex_generate_mdl(
        project_root=project_root,
        wren_project_dir=project_dir,
        wren_home=wren_home,
        wren_bin=wren_bin,
        schema_manifest_path=manifest_path,
        duckdb_path=duckdb_path,
        smoke_sql=smoke_sql,
        extra_instructions=extra_instructions,
        prompt_output_path=prompt_output_path,
        execute=False,
        codex_bin=codex_bin,
        codex_model=codex_model,
        last_message_path=codex_last_message_path,
        timeout_seconds=codex_timeout_seconds,
        runner=codex_runner,
    )
    if execute_codex:
        codex_result = execute_codex_generate_mdl_loop(
            initial_result=codex_result,
            project_root=project_root,
            project_dir=project_dir,
            wren_home=wren_home,
            wren_bin=wren_bin,
            schema_manifest_path=manifest_path,
            duckdb_path=duckdb_path,
            smoke_sql=smoke_sql,
            extra_instructions=extra_instructions,
            codex_bin=codex_bin,
            codex_model=codex_model,
            codex_last_message_path=codex_last_message_path,
            codex_timeout_seconds=codex_timeout_seconds,
            max_repair_rounds=max_repair_rounds,
            post_validate=post_validate,
            wren_runner=active_wren_runner,
            codex_runner=codex_runner,
        )

    project_summary = _actual_project_summary(project_dir)
    result = {
        "ok": context_init.ok and bool(codex_result["ok"]),
        "mode": "skill",
        "source": str(sqlite_path),
        "project_name": project_name,
        "wren_project_dir": str(project_dir),
        "duckdb_path": str(duckdb_path),
        "wren_home": str(wren_home),
        "schema_manifest_path": str(manifest_path),
        "models": project_summary["models"] or [table.name for table in tables],
        "relationship_count": project_summary["relationship_count"]
        if project_summary["models"]
        else len(relationships),
        "wren_commands": {"context_init": context_init.to_dict()},
        "codex": codex_result,
    }
    if report_path:
        report_path = report_path.resolve()
        write_onboarding_report(report_path, result)
        result["report_path"] = str(report_path)
    return result


def execute_codex_generate_mdl_loop(
    *,
    initial_result: dict[str, Any],
    project_root: Path,
    project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    schema_manifest_path: Path | None,
    duckdb_path: Path | None,
    smoke_sql: str | None,
    extra_instructions: str | None,
    codex_bin: str,
    codex_model: str | None,
    codex_last_message_path: Path | None,
    codex_timeout_seconds: int,
    max_repair_rounds: int,
    post_validate: bool,
    wren_runner: WrenRunner,
    codex_runner: CodexCliRunner | None,
    repair_prompt_builder: Callable[[dict[str, Any], int], str] | None = None,
    additional_validation: Callable[[], dict[str, object]] | None = None,
    additional_validation_name: str = "onboarding_artifacts",
    additional_validations: dict[str, Callable[[], dict[str, object]]] | None = None,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    active_codex_runner = codex_runner or CodexCliRunner(
        codex_bin=codex_bin,
        project_root=project_root,
        model=codex_model,
        timeout_seconds=codex_timeout_seconds,
    )
    max_repair_rounds = max(0, max_repair_rounds)
    prompt = str(initial_result["prompt"])
    rounds: list[dict[str, Any]] = []
    final_validation: dict[str, dict[str, object]] | None = None
    ok = False

    for round_index in range(max_repair_rounds + 1):
        prompt_path = _artifact_path(
            project_dir,
            "prompts",
            round_index,
            ".md",
            artifact_root=artifact_root,
        )
        prompt_path.write_text(prompt, encoding="utf-8")
        last_message_path = (
            codex_last_message_path.resolve()
            if round_index == 0 and codex_last_message_path
            else _artifact_path(
                project_dir,
                "codex_last_messages",
                round_index,
                ".md",
                artifact_root=artifact_root,
            )
        )
        command = active_codex_runner.run(prompt, last_message_path=last_message_path)
        round_record: dict[str, Any] = {
            "round": round_index,
            "kind": "initial" if round_index == 0 else "repair",
            "prompt_path": str(prompt_path),
            "codex_command": command.to_dict(),
        }
        if not command.ok:
            rounds.append(round_record)
            ok = False
            break

        if not post_validate:
            rounds.append(round_record)
            ok = True
            break

        final_validation = _run_validation_commands(wren_runner, smoke_sql=smoke_sql)
        if additional_validation:
            final_validation[additional_validation_name] = additional_validation()
        for name, validator in (additional_validations or {}).items():
            final_validation[name] = validator()
        validation_path = _artifact_path(
            project_dir,
            "validation",
            round_index,
            ".json",
            artifact_root=artifact_root,
        )
        validation_path.write_text(
            json.dumps(final_validation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        round_record["validation_path"] = str(validation_path)
        round_record["validation"] = final_validation
        rounds.append(round_record)
        if _commands_ok(final_validation):
            ok = True
            break
        if round_index >= max_repair_rounds:
            ok = False
            break
        if repair_prompt_builder:
            prompt = repair_prompt_builder(final_validation, round_index + 1)
        else:
            if schema_manifest_path is None:
                raise ValueError("schema_manifest_path is required for the default repair prompt.")
            prompt = build_codex_generate_mdl_repair_prompt(
                project_root=project_root,
                wren_project_dir=project_dir,
                wren_home=wren_home,
                wren_bin=wren_bin,
                schema_manifest_path=schema_manifest_path,
                duckdb_path=duckdb_path,
                smoke_sql=smoke_sql,
                validation_result=final_validation,
                round_index=round_index + 1,
                extra_instructions=extra_instructions,
            )

    result = dict(initial_result)
    result["ok"] = ok
    result["executed"] = True
    result.pop("codex_command", None)
    result["rounds"] = rounds
    result["max_repair_rounds"] = max_repair_rounds
    result["post_validate"] = post_validate
    result["repair_rounds_used"] = max(0, len(rounds) - 1)
    result["final_validation"] = final_validation
    return result


def _run_validation_commands(runner: WrenRunner, *, smoke_sql: str | None) -> dict[str, dict[str, object]]:
    commands = {
        "context_validate": runner.run(["context", "validate"]).to_dict(),
        "context_build": runner.run(["context", "build"]).to_dict(),
    }
    if smoke_sql:
        commands["dry_run"] = runner.run(["dry-run", "--sql", smoke_sql]).to_dict()
    return commands


def _commands_ok(commands: dict[str, dict[str, object]]) -> bool:
    return all(command.get("returncode") == 0 for command in commands.values())


def _artifact_path(
    project_dir: Path,
    folder: str,
    round_index: int,
    suffix: str,
    *,
    artifact_root: Path | None = None,
) -> Path:
    root = artifact_root.resolve() if artifact_root else project_dir / "onboarding"
    path = root / folder / f"round_{round_index}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _actual_project_summary(project_dir: Path) -> dict[str, Any]:
    models: list[str] = []
    models_dir = project_dir / "models"
    if models_dir.exists():
        for path in sorted(models_dir.glob("*/metadata.yml")):
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and loaded.get("name"):
                models.append(str(loaded["name"]))
    relationship_count = 0
    relationships_path = project_dir / "relationships.yml"
    if relationships_path.exists():
        loaded = yaml.safe_load(relationships_path.read_text(encoding="utf-8"))
        relationships = loaded.get("relationships") if isinstance(loaded, dict) else None
        if isinstance(relationships, list):
            relationship_count = len(relationships)
    return {"models": models, "relationship_count": relationship_count}


def _schema_manifest(
    *,
    project_name: str,
    sqlite_path: Path,
    duckdb_path: Path,
    tables: list[Any],
    relationships: list[Any],
) -> dict[str, Any]:
    return {
        "project_name": project_name,
        "source": {
            "type": "sqlite",
            "path": str(sqlite_path),
        },
        "runtime": {
            "type": "duckdb",
            "path": str(duckdb_path),
            "profile_name": project_name,
        },
        "tables": [
            {
                "name": table.name,
                "primary_key": table.primary_key,
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
        "notes": [
            "This manifest is factual input for an agent following WrenAI's generate-mdl skill.",
            "It is not a finished semantic layer.",
        ],
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
