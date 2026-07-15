from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

import yaml

from .codex_runtime import (
    CodexCliRunner,
    build_codex_starrocks_generate_mdl_prompt,
    build_codex_starrocks_repair_prompt,
)
from .report import write_onboarding_report
from .wren_cli import CommandResult, WrenCliRunner


class WrenRunner(Protocol):
    def run(self, args: list[str]) -> CommandResult:
        ...


def prepare_starrocks_skill_onboarding(
    *,
    project_name: str,
    project_dir: Path,
    project_root: Path,
    wren_home: Path,
    wren_bin: Path,
    host: str,
    port: int,
    database: str,
    user: str,
    password_env: str = "CONTEXT_BUILDER_STARROCKS_PASSWORD",
    allow_empty_password: bool = False,
    profile_name: str | None = None,
    allowed_catalogs: tuple[str, ...] = ("default_catalog",),
    allowed_databases: tuple[str, ...] | None = None,
    max_query_rows: int = 100,
    query_timeout_seconds: int = 15,
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
    project_root = project_root.resolve()
    project_dir = project_dir.resolve()
    wren_home = wren_home.resolve()
    wren_bin = wren_bin.resolve()
    profile_name = profile_name or project_name
    allowed_databases = allowed_databases or (database,)

    if not allow_empty_password and not os.environ.get(password_env):
        raise RuntimeError(f"Required StarRocks password environment variable is not set: {password_env}")
    if (project_dir / "wren_project.yml").exists() and not force:
        raise FileExistsError(f"Wren project already exists: {project_dir}. Use --force.")
    if not allowed_catalogs:
        raise ValueError("At least one allowed StarRocks catalog is required.")
    if database.lower() not in {item.lower() for item in allowed_databases}:
        raise ValueError("The active StarRocks database must be present in allowed_databases.")
    if max_query_rows < 1 or query_timeout_seconds < 1:
        raise ValueError("StarRocks query limits must be positive.")

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
    if context_init.ok:
        _set_wren_project_name(project_dir / "wren_project.yml", project_name)

    onboarding_dir = project_dir / "onboarding"
    onboarding_dir.mkdir(parents=True, exist_ok=True)
    connection_path = onboarding_dir / "starrocks_connection.yml"
    connection_path.write_text(
        yaml.safe_dump(
            {
                "datasource": "doris",
                "host": host,
                "port": port,
                "database": database,
                "user": user,
                "password": None if allow_empty_password else f"${{{password_env}}}",
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    profile_add = active_wren_runner.run(
        ["profile", "add", profile_name, "--from-file", str(connection_path)]
    )
    set_profile = active_wren_runner.run(
        ["context", "set-profile", profile_name, "--path", str(project_dir)]
    )

    discovery_snapshot_path = onboarding_dir / "discovery_snapshot.json"
    schema_manifest_path = onboarding_dir / "schema_manifest.json"
    evidence_path = onboarding_dir / "starrocks_query_evidence.jsonl"
    query_command = build_starrocks_query_command(
        project_root=project_root,
        host=host,
        port=port,
        database=database,
        user=user,
        password_env=password_env,
        allow_empty_password=allow_empty_password,
        allowed_catalogs=allowed_catalogs,
        allowed_databases=allowed_databases,
        max_query_rows=max_query_rows,
        query_timeout_seconds=query_timeout_seconds,
        evidence_path=evidence_path,
    )
    prompt = build_codex_starrocks_generate_mdl_prompt(
        project_root=project_root,
        wren_project_dir=project_dir,
        wren_home=wren_home,
        wren_bin=wren_bin,
        query_command=query_command,
        discovery_snapshot_path=discovery_snapshot_path,
        schema_manifest_path=schema_manifest_path,
        evidence_path=evidence_path,
        smoke_sql=smoke_sql,
        extra_instructions=extra_instructions,
    )
    if prompt_output_path:
        prompt_output_path = prompt_output_path.resolve()
        prompt_output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_output_path.write_text(prompt, encoding="utf-8")

    codex_result: dict[str, Any] = {
        "ok": True,
        "executed": False,
        "prompt": prompt,
        "post_validate": post_validate,
        "max_repair_rounds": max(0, max_repair_rounds),
        "repair_rounds_used": 0,
        "rounds": [],
        "final_validation": None,
    }
    if execute_codex:
        codex_result = _execute_codex_loop(
            initial_prompt=prompt,
            project_root=project_root,
            project_dir=project_dir,
            wren_home=wren_home,
            wren_bin=wren_bin,
            query_command=query_command,
            discovery_snapshot_path=discovery_snapshot_path,
            schema_manifest_path=schema_manifest_path,
            evidence_path=evidence_path,
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
    commands = {
        "context_init": context_init.to_dict(),
        "profile_add": profile_add.to_dict(),
        "context_set_profile": set_profile.to_dict(),
    }
    result = {
        "ok": all(command.ok for command in (context_init, profile_add, set_profile))
        and bool(codex_result["ok"]),
        "mode": "skill",
        "source": f"starrocks://{host}:{port}/{database}",
        "project_name": project_name,
        "wren_project_dir": str(project_dir),
        "wren_home": str(wren_home),
        "duckdb_path": None,
        "profile_name": profile_name,
        "connection_path": str(connection_path),
        "discovery_snapshot_path": str(discovery_snapshot_path),
        "schema_manifest_path": str(schema_manifest_path),
        "evidence_path": str(evidence_path),
        "models": project_summary["models"],
        "relationship_count": project_summary["relationship_count"],
        "wren_commands": commands,
        "codex": codex_result,
    }
    if prompt_output_path:
        result["prompt_output_path"] = str(prompt_output_path)
    if report_path:
        report_path = report_path.resolve()
        write_onboarding_report(report_path, result)
        result["report_path"] = str(report_path)
    return result


def build_starrocks_query_command(
    *,
    project_root: Path,
    host: str,
    port: int,
    database: str,
    user: str,
    password_env: str,
    allow_empty_password: bool,
    allowed_catalogs: tuple[str, ...],
    allowed_databases: tuple[str, ...],
    max_query_rows: int,
    query_timeout_seconds: int,
    evidence_path: Path,
) -> str:
    python_bin = project_root / ".venv-wren" / "python.exe"
    arguments = [
        f"$env:PYTHONPATH={_ps_quote(str(project_root / 'src'))};",
        "&",
        _ps_quote(str(python_bin)),
        "-m data_subagent_context_builder.cli",
        "--project-root",
        _ps_quote(str(project_root)),
        "starrocks-query",
        "--host",
        _ps_quote(host),
        "--port",
        str(port),
        "--database",
        _ps_quote(database),
        "--user",
        _ps_quote(user),
        "--password-env",
        _ps_quote(password_env),
    ]
    if allow_empty_password:
        arguments.append("--allow-empty-password")
    for catalog in allowed_catalogs:
        arguments.extend(["--allowed-catalog", _ps_quote(catalog)])
    for allowed_database in allowed_databases:
        arguments.extend(["--allowed-database", _ps_quote(allowed_database)])
    arguments.extend(
        [
            "--max-rows",
            str(max_query_rows),
            "--query-timeout-seconds",
            str(query_timeout_seconds),
            "--evidence-path",
            _ps_quote(str(evidence_path)),
            "--sql",
            '"<READ_ONLY_SQL>"',
        ]
    )
    return " ".join(arguments)


def _execute_codex_loop(
    *,
    initial_prompt: str,
    project_root: Path,
    project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    query_command: str,
    discovery_snapshot_path: Path,
    schema_manifest_path: Path,
    evidence_path: Path,
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
) -> dict[str, Any]:
    active_codex_runner = codex_runner or CodexCliRunner(
        codex_bin=codex_bin,
        project_root=project_root,
        model=codex_model,
        timeout_seconds=codex_timeout_seconds,
    )
    prompt = initial_prompt
    rounds: list[dict[str, Any]] = []
    final_validation: dict[str, dict[str, object]] | None = None
    ok = False
    completion_status = "failed"
    max_repair_rounds = max(0, max_repair_rounds)

    for round_index in range(max_repair_rounds + 1):
        prompt_path = _artifact_path(project_dir, "prompts", round_index, ".md")
        prompt_path.write_text(prompt, encoding="utf-8")
        last_message_path = (
            codex_last_message_path.resolve()
            if round_index == 0 and codex_last_message_path
            else _artifact_path(project_dir, "codex_last_messages", round_index, ".md")
        )
        command = active_codex_runner.run(prompt, last_message_path=last_message_path)
        round_record: dict[str, Any] = {
            "round": round_index,
            "kind": "initial" if round_index == 0 else "repair",
            "prompt_path": str(prompt_path),
            "codex_command": command.to_dict(),
        }
        if not command.ok:
            if command.returncode == 124 and post_validate and _has_candidate_artifacts(project_dir):
                final_validation = _run_validation_commands(
                    wren_runner,
                    smoke_sql=smoke_sql,
                    discovery_snapshot_path=discovery_snapshot_path,
                    schema_manifest_path=schema_manifest_path,
                    evidence_path=evidence_path,
                )
                validation_path = _artifact_path(project_dir, "validation", round_index, ".json")
                validation_path.write_text(
                    json.dumps(final_validation, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                round_record["validation_path"] = str(validation_path)
                round_record["validation"] = final_validation
                round_record["accepted_after_timeout"] = all(
                    command_result.get("returncode") == 0
                    for command_result in final_validation.values()
                )
                ok = bool(round_record["accepted_after_timeout"])
                if ok:
                    completion_status = "accepted_after_timeout"
            rounds.append(round_record)
            break
        if not post_validate:
            rounds.append(round_record)
            ok = True
            completion_status = "completed_without_post_validation"
            break

        final_validation = _run_validation_commands(
            wren_runner,
            smoke_sql=smoke_sql,
            discovery_snapshot_path=discovery_snapshot_path,
            schema_manifest_path=schema_manifest_path,
            evidence_path=evidence_path,
        )
        validation_path = _artifact_path(project_dir, "validation", round_index, ".json")
        validation_path.write_text(
            json.dumps(final_validation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        round_record["validation_path"] = str(validation_path)
        round_record["validation"] = final_validation
        rounds.append(round_record)
        if all(command_result.get("returncode") == 0 for command_result in final_validation.values()):
            ok = True
            completion_status = "validated"
            break
        if round_index >= max_repair_rounds:
            break
        prompt = build_codex_starrocks_repair_prompt(
            project_root=project_root,
            wren_project_dir=project_dir,
            wren_home=wren_home,
            wren_bin=wren_bin,
            query_command=query_command,
            discovery_snapshot_path=discovery_snapshot_path,
            schema_manifest_path=schema_manifest_path,
            evidence_path=evidence_path,
            smoke_sql=smoke_sql,
            validation_result=final_validation,
            round_index=round_index + 1,
            extra_instructions=extra_instructions,
        )

    return {
        "ok": ok,
        "executed": True,
        "rounds": rounds,
        "max_repair_rounds": max_repair_rounds,
        "post_validate": post_validate,
        "repair_rounds_used": max(0, len(rounds) - 1),
        "final_validation": final_validation,
        "completion_status": completion_status,
    }


def _run_validation_commands(
    runner: WrenRunner,
    *,
    smoke_sql: str | None,
    discovery_snapshot_path: Path,
    schema_manifest_path: Path,
    evidence_path: Path,
) -> dict[str, dict[str, object]]:
    commands = {
        "context_validate": runner.run(["context", "validate"]).to_dict(),
        "context_build": runner.run(["context", "build"]).to_dict(),
    }
    if smoke_sql:
        commands["dry_run"] = runner.run(["dry-run", "--sql", smoke_sql]).to_dict()
    commands["onboarding_artifacts"] = validate_starrocks_onboarding_artifacts(
        discovery_snapshot_path=discovery_snapshot_path,
        schema_manifest_path=schema_manifest_path,
        evidence_path=evidence_path,
    )
    return commands


def validate_starrocks_onboarding_artifacts(
    *,
    discovery_snapshot_path: Path,
    schema_manifest_path: Path,
    evidence_path: Path,
) -> dict[str, object]:
    errors: list[str] = []
    for label, path in (
        ("discovery snapshot", discovery_snapshot_path),
        ("schema manifest", schema_manifest_path),
    ):
        if not path.exists():
            errors.append(f"Missing {label}: {path}")
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid {label}: {exc}")
            continue
        if not isinstance(loaded, dict):
            errors.append(f"{label.title()} must contain a JSON object.")

    executed_evidence = 0
    if not evidence_path.exists():
        errors.append(f"Missing query evidence: {evidence_path}")
    else:
        for line_number, line in enumerate(evidence_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"Invalid evidence line {line_number}: {exc}")
                continue
            if isinstance(record, dict) and record.get("status") == "executed":
                executed_evidence += 1
        if executed_evidence == 0:
            errors.append("Query evidence contains no executed discovery query.")

    return {
        "args": ["validate-starrocks-onboarding-artifacts"],
        "returncode": 1 if errors else 0,
        "stdout": f"Valid discovery artifacts with {executed_evidence} executed evidence records."
        if not errors
        else "",
        "stderr": "\n".join(errors),
    }


def _artifact_path(project_dir: Path, folder: str, round_index: int, suffix: str) -> Path:
    path = project_dir / "onboarding" / folder / f"round_{round_index}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _actual_project_summary(project_dir: Path) -> dict[str, Any]:
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


def _has_candidate_artifacts(project_dir: Path) -> bool:
    return (
        any((project_dir / "models").glob("*/metadata.yml"))
        and (project_dir / "onboarding" / "discovery_snapshot.json").exists()
        and (project_dir / "onboarding" / "schema_manifest.json").exists()
    )


def _set_wren_project_name(path: Path, project_name: str) -> None:
    if not path.exists():
        return
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        loaded = {}
    loaded["name"] = project_name
    path.write_text(yaml.safe_dump(loaded, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
