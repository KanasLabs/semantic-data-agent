from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CodexCommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    last_message_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "args": self.args,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "last_message_path": self.last_message_path,
        }


class CodexCliRunner:
    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        project_root: Path,
        sandbox: str = "workspace-write",
        model: str | None = None,
        timeout_seconds: int = 900,
        ephemeral: bool = False,
        ignore_user_config: bool = False,
        approval_policy: str | None = None,
        output_schema_path: Path | None = None,
        sanitized_environment: bool = False,
    ) -> None:
        self.codex_bin = codex_bin
        self.project_root = project_root
        self.sandbox = sandbox
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.ephemeral = ephemeral
        self.ignore_user_config = ignore_user_config
        self.approval_policy = approval_policy
        self.output_schema_path = output_schema_path
        self.sanitized_environment = sanitized_environment

    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        resolved_codex_bin = shutil.which(self.codex_bin) or self.codex_bin
        args = [resolved_codex_bin]
        if self.approval_policy:
            args.extend(["--ask-for-approval", self.approval_policy])
        args.extend(
            [
            "exec",
            "--cd",
            str(self.project_root),
            "--sandbox",
            self.sandbox,
            "--color",
            "never",
            ]
        )
        if self.ephemeral:
            args.append("--ephemeral")
        if self.ignore_user_config:
            args.append("--ignore-user-config")
        if self.output_schema_path:
            args.extend(["--output-schema", str(self.output_schema_path.resolve())])
        if self.model:
            args.extend(["--model", self.model])
        if last_message_path:
            last_message_path.parent.mkdir(parents=True, exist_ok=True)
            args.extend(["--output-last-message", str(last_message_path)])
        args.append("-")

        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                process = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    creationflags=creation_flags,
                    start_new_session=os.name != "nt",
                    env=_codex_environment() if self.sanitized_environment else None,
                )
            except OSError as exc:
                return CodexCommandResult(
                    args=args[1:],
                    returncode=127,
                    stdout="",
                    stderr=f"Failed to start Codex executable {resolved_codex_bin!r}: {exc}",
                    last_message_path=str(last_message_path) if last_message_path else None,
                )
            timed_out = False
            try:
                process.communicate(input=prompt.encode("utf-8"), timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace")
        if timed_out:
            timeout_message = f"Codex command timed out after {self.timeout_seconds} seconds."
            stderr = f"{stderr.rstrip()}\n{timeout_message}".strip()
        returncode = 124 if timed_out else process.returncode
        return CodexCommandResult(
            args=args[1:],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            last_message_path=str(last_message_path) if last_message_path else None,
        )


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _codex_environment() -> dict[str, str]:
    allowed = {
        "APPDATA",
        "CODEX_HOME",
        "COMSPEC",
        "HOME",
        "LANG",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def prepare_codex_enrichment(
    *,
    project_root: Path,
    wren_project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    smoke_sql: str | None = None,
    extra_instructions: str | None = None,
    prompt_output_path: Path | None = None,
    execute: bool = False,
    codex_bin: str = "codex",
    codex_model: str | None = None,
    last_message_path: Path | None = None,
    timeout_seconds: int = 900,
    runner: CodexCliRunner | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    wren_project_dir = wren_project_dir.resolve()
    wren_home = wren_home.resolve()
    wren_bin = wren_bin.resolve()
    prompt = build_codex_enrichment_prompt(
        project_root=project_root,
        wren_project_dir=wren_project_dir,
        wren_home=wren_home,
        wren_bin=wren_bin,
        smoke_sql=smoke_sql,
        extra_instructions=extra_instructions,
    )
    result: dict[str, Any] = {
        "ok": True,
        "executed": False,
        "project_root": str(project_root),
        "wren_project_dir": str(wren_project_dir),
        "wren_home": str(wren_home),
        "wren_bin": str(wren_bin),
        "prompt": prompt,
    }
    if prompt_output_path:
        prompt_output_path = prompt_output_path.resolve()
        prompt_output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_output_path.write_text(prompt, encoding="utf-8")
        result["prompt_output_path"] = str(prompt_output_path)

    if execute:
        active_runner = runner or CodexCliRunner(
            codex_bin=codex_bin,
            project_root=project_root,
            model=codex_model,
            timeout_seconds=timeout_seconds,
        )
        command = active_runner.run(prompt, last_message_path=last_message_path)
        result["executed"] = True
        result["ok"] = command.ok
        result["codex_command"] = command.to_dict()
    return result


def prepare_codex_generate_mdl(
    *,
    project_root: Path,
    wren_project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    schema_manifest_path: Path,
    duckdb_path: Path | None = None,
    smoke_sql: str | None = None,
    extra_instructions: str | None = None,
    prompt_output_path: Path | None = None,
    execute: bool = False,
    codex_bin: str = "codex",
    codex_model: str | None = None,
    last_message_path: Path | None = None,
    timeout_seconds: int = 900,
    runner: CodexCliRunner | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    wren_project_dir = wren_project_dir.resolve()
    wren_home = wren_home.resolve()
    wren_bin = wren_bin.resolve()
    schema_manifest_path = schema_manifest_path.resolve()
    duckdb_path = duckdb_path.resolve() if duckdb_path else None
    prompt = build_codex_generate_mdl_prompt(
        project_root=project_root,
        wren_project_dir=wren_project_dir,
        wren_home=wren_home,
        wren_bin=wren_bin,
        schema_manifest_path=schema_manifest_path,
        duckdb_path=duckdb_path,
        smoke_sql=smoke_sql,
        extra_instructions=extra_instructions,
    )
    result: dict[str, Any] = {
        "ok": True,
        "executed": False,
        "project_root": str(project_root),
        "wren_project_dir": str(wren_project_dir),
        "wren_home": str(wren_home),
        "wren_bin": str(wren_bin),
        "schema_manifest_path": str(schema_manifest_path),
        "duckdb_path": str(duckdb_path) if duckdb_path else None,
        "prompt": prompt,
    }
    if prompt_output_path:
        prompt_output_path = prompt_output_path.resolve()
        prompt_output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_output_path.write_text(prompt, encoding="utf-8")
        result["prompt_output_path"] = str(prompt_output_path)

    if execute:
        active_runner = runner or CodexCliRunner(
            codex_bin=codex_bin,
            project_root=project_root,
            model=codex_model,
            timeout_seconds=timeout_seconds,
        )
        command = active_runner.run(prompt, last_message_path=last_message_path)
        result["executed"] = True
        result["ok"] = command.ok
        result["codex_command"] = command.to_dict()
    return result


def build_codex_enrichment_prompt(
    *,
    project_root: Path,
    wren_project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    smoke_sql: str | None,
    extra_instructions: str | None,
) -> str:
    lines = [
        "You are working on the WrenAI Context Builder / MDL onboarding workstream.",
        "",
        "Read these files first:",
        "1. AGENTS.md",
        "2. docs/data_subagent_progress_and_pitfalls.md",
        "3. docs/wren_context_builder_plan.md",
        "4. docs/wren_context_builder_feasibility.md",
        "5. docs/wren_context_builder_methods.html",
        "",
        "Do not modify the Data Subagent online question-answering runtime unless a small interface bug blocks this onboarding task.",
        "",
        "Goal:",
        "- Improve the existing Wren project as an upstream context/MDL onboarding artifact.",
        "- Treat auto-generated schema-level MDL as a draft, not as finished business semantics.",
        "- Use WrenAI native commands as the validator and build step.",
        "",
        "Wren inputs:",
        f"- Project root: {project_root}",
        f"- Wren project dir: {wren_project_dir}",
        f"- Wren home: {wren_home}",
        f"- Wren CLI: {wren_bin}",
        "",
        "Before editing, run or inspect the installed Wren workflow guide:",
        f"- {wren_bin} skills get generate-mdl",
        "",
        "Allowed edits:",
        "- Wren project YAML under the target Wren project directory.",
        "- Knowledge rules/examples under the target Wren project directory.",
        "- Onboarding reports or smoke evals if directly useful.",
        "",
        "Do not:",
        "- Print or copy secrets.",
        "- Edit generated Wren home state directly unless the task requires profile setup.",
        "- Claim that schema-level MDL is high-quality business semantics.",
        "",
        "Validation commands to run after changes:",
        f"- Set WREN_HOME to {wren_home}",
        f"- {wren_bin} context validate",
        f"- {wren_bin} context build",
    ]
    if smoke_sql:
        lines.append(f"- {wren_bin} dry-run --sql \"{smoke_sql}\"")
    if extra_instructions:
        lines.extend(["", "Additional task instructions:", extra_instructions.strip()])
    lines.extend(
        [
            "",
            "Final response requirements:",
            "- Summarize changed files.",
            "- Include validate/build/dry-run results.",
            "- List remaining semantic-layer gaps.",
        ]
    )
    return "\n".join(lines)


def build_codex_generate_mdl_prompt(
    *,
    project_root: Path,
    wren_project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    schema_manifest_path: Path,
    duckdb_path: Path | None,
    smoke_sql: str | None,
    extra_instructions: str | None,
) -> str:
    lines = [
        "You are working on the WrenAI Context Builder / MDL onboarding workstream.",
        "",
        "Read these files first:",
        "1. AGENTS.md",
        "2. docs/data_subagent_progress_and_pitfalls.md",
        "3. docs/wren_context_builder_plan.md",
        "4. docs/wren_context_builder_feasibility.md",
        "5. docs/wren_context_builder_methods.html",
        "",
        "Primary rule:",
        "- Follow WrenAI's installed generate-mdl skill as the source of truth for creating MDL/context YAML.",
        "- If this prompt conflicts with the installed generate-mdl skill, prefer the Wren skill.",
        "- Do not treat deterministic schema dumps as finished business semantics.",
        "- Do not modify the Data Subagent online question-answering runtime.",
        "",
        "Before writing MDL, inspect the installed Wren workflow guide:",
        f"- {wren_bin} skills get generate-mdl",
        "",
        "Onboarding inputs:",
        f"- Project root: {project_root}",
        f"- Target Wren project dir: {wren_project_dir}",
        f"- Wren home: {wren_home}",
        f"- Wren CLI: {wren_bin}",
        f"- Schema manifest seed: {schema_manifest_path}",
    ]
    if duckdb_path:
        lines.append(f"- Runtime DuckDB database for direct inspection and validation: {duckdb_path}")
    lines.extend(
        [
            "",
            "Task:",
            "- Use the schema manifest as seed evidence, not as the complete semantic model.",
            "- Inspect the runtime database directly when the Wren generate-mdl skill calls for schema checks, sample queries, relationship validation, or orphan checks.",
            "- Generate or update Wren YAML under the target project using the generate-mdl skill workflow.",
            "- Use Wren type normalization guidance from the skill; keep source_type properties where useful.",
            "- Add relationships only when they are defensible from schema evidence and runtime validation.",
            "- Add descriptions, rules, and examples only when they are grounded in the manifest, runtime data, user instructions, or other explicit evidence.",
            "- Leave uncertain business semantics explicit instead of guessing metrics, currencies, or time meanings.",
            "- Keep all edits inside the target Wren project unless writing a requested report or smoke eval.",
            "",
            "Validation commands to run after editing:",
            f"- Set WREN_HOME to {wren_home}",
            f"- {wren_bin} context validate",
            f"- {wren_bin} context build",
        ]
    )
    if smoke_sql:
        lines.append(f"- {wren_bin} dry-run --sql \"{smoke_sql}\"")
    if extra_instructions:
        lines.extend(["", "Additional task instructions:", extra_instructions.strip()])
    lines.extend(
        [
            "",
            "Final response requirements:",
            "- Summarize generated or changed Wren files.",
            "- Include validate/build/dry-run results.",
            "- List remaining semantic-layer gaps and assumptions.",
        ]
    )
    return "\n".join(lines)


def build_codex_generate_mdl_repair_prompt(
    *,
    project_root: Path,
    wren_project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    schema_manifest_path: Path,
    duckdb_path: Path | None,
    smoke_sql: str | None,
    validation_result: dict[str, Any],
    round_index: int,
    extra_instructions: str | None,
) -> str:
    lines = [
        "You are continuing the WrenAI Context Builder / MDL onboarding workstream.",
        "",
        "The outer Context Builder ran Wren validation after your previous Codex round, and it failed.",
        "Fix only the target Wren project. Do not restart from scratch unless the current files are unusable.",
        "",
        "Read or reuse these inputs:",
        f"- Project root: {project_root}",
        f"- Target Wren project dir: {wren_project_dir}",
        f"- Wren home: {wren_home}",
        f"- Wren CLI: {wren_bin}",
        f"- Schema manifest: {schema_manifest_path}",
    ]
    if duckdb_path:
        lines.append(f"- Runtime DuckDB database: {duckdb_path}")
    lines.extend(
        [
            "",
        "Primary rule:",
        "- Follow WrenAI's installed generate-mdl skill as the source of truth.",
        "- If this repair prompt conflicts with the installed generate-mdl skill, prefer the Wren skill.",
        "- Keep edits inside the target Wren project.",
        "- Preserve defensible YAML that already works; only change what is needed to pass validation.",
        "- Do not modify the Data Subagent online question-answering runtime.",
        "- Use the schema manifest as seed evidence and inspect the runtime database directly when needed.",
            "",
            f"Repair round: {round_index}",
            "",
            "Outer Wren validation result:",
            "```json",
            _compact_json(validation_result),
            "```",
            "",
            "Required checks before your final response:",
            f"- Set WREN_HOME to {wren_home}",
            f"- {wren_bin} context validate",
            f"- {wren_bin} context build",
        ]
    )
    if smoke_sql:
        lines.append(f"- {wren_bin} dry-run --sql \"{smoke_sql}\"")
    if extra_instructions:
        lines.extend(["", "Additional task instructions:", extra_instructions.strip()])
    lines.extend(
        [
            "",
            "Final response requirements:",
            "- Summarize the fix.",
            "- Include validate/build/dry-run results.",
            "- List any remaining semantic-layer assumptions.",
        ]
    )
    return "\n".join(lines)


def build_codex_starrocks_generate_mdl_prompt(
    *,
    project_root: Path,
    wren_project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    query_command: str,
    discovery_snapshot_path: Path,
    schema_manifest_path: Path,
    evidence_path: Path,
    smoke_sql: str | None,
    extra_instructions: str | None,
) -> str:
    lines = [
        "You are working on the WrenAI Context Builder / MDL onboarding workstream.",
        "",
        "Read these files first:",
        "1. AGENTS.md",
        "2. docs/data_subagent_progress_and_pitfalls.md",
        "3. docs/wren_context_builder_plan.md",
        "4. docs/wren_context_builder_feasibility.md",
        "5. docs/wren_context_builder_methods.html",
        "",
        "Primary rule:",
        "- Follow WrenAI's installed generate-mdl skill as the source of truth.",
        "- If this prompt conflicts with the installed generate-mdl skill, prefer the Wren skill.",
        "- Do not modify the Data Subagent online question-answering runtime.",
        "- Treat the generated Context Layer as a reviewable candidate, not production truth.",
        "- Keep all writes inside the target Wren project. Do not update repository progress docs or unrelated files.",
        "- Do not run wren memory index, memory fetch, or memory recall; they are outside this onboarding acceptance path.",
        "",
        "Before discovery, inspect the installed Wren workflow guide:",
        f"- {wren_bin} skills get generate-mdl",
        "",
        "Onboarding workspace:",
        f"- Project root: {project_root}",
        f"- Target Wren project: {wren_project_dir}",
        f"- Wren home: {wren_home}",
        f"- Wren CLI: {wren_bin}",
        f"- Discovery snapshot output: {discovery_snapshot_path}",
        f"- Schema manifest output: {schema_manifest_path}",
        f"- Builder-owned query evidence: {evidence_path}",
        "",
        "Controlled StarRocks access:",
        "- Use only the Builder command below for database discovery and validation.",
        "- Replace <READ_ONLY_SQL> with one SHOW, DESCRIBE, SELECT, WITH, or EXPLAIN statement.",
        "- Do not use mysql clients, Docker exec, arbitrary scripts, or another database connection path.",
        "```powershell",
        query_command,
        "```",
        "",
        "Discovery and modelling task:",
        "- Decide which read-only queries are needed by following the Wren generate-mdl skill.",
        "- Inspect only the allowlisted Catalog and Database exposed by the controlled command.",
        "- Ground table, column, key, partition, distribution, index, sample, and relationship claims in query evidence.",
        "- Use small samples and aggregate checks; do not request broad table dumps.",
        "- Validate candidate relationships with join coverage and orphan checks before adding them.",
        "- Write discovery_snapshot.json as a concise record of inspected objects, query result hashes, findings, and open questions.",
        "- Write schema_manifest.json from the discovery evidence. It is process evidence, not a finished semantic model.",
        "- Generate Wren Models, defensible Relationships, grounded descriptions, rules, and SQL examples inside the target project.",
        "- Do not guess business metrics, currencies, time semantics, or relationship cardinality.",
        "",
        "Validation commands to run after editing:",
        f"- Set WREN_HOME to {wren_home}",
        f"- Run {wren_bin} context validate from {wren_project_dir}",
        f"- Run {wren_bin} context build from {wren_project_dir}",
    ]
    if smoke_sql:
        lines.append(f"- Run {wren_bin} dry-run --sql \"{smoke_sql}\" from {wren_project_dir}")
    if extra_instructions:
        lines.extend(["", "Additional task instructions:", extra_instructions.strip()])
    lines.extend(
        [
            "",
            "Final response requirements:",
            "- Summarize discovery evidence and generated Wren files.",
            "- Include validate/build/dry-run results.",
            "- List assumptions, rejected relationship candidates, and business questions requiring expert review.",
        ]
    )
    return "\n".join(lines)


def build_codex_starrocks_repair_prompt(
    *,
    project_root: Path,
    wren_project_dir: Path,
    wren_home: Path,
    wren_bin: Path,
    query_command: str,
    discovery_snapshot_path: Path,
    schema_manifest_path: Path,
    evidence_path: Path,
    smoke_sql: str | None,
    validation_result: dict[str, Any],
    round_index: int,
    extra_instructions: str | None,
) -> str:
    lines = [
        "You are repairing a candidate StarRocks Wren Context Layer.",
        "",
        "Primary rule:",
        "- Follow WrenAI's installed generate-mdl skill as the source of truth.",
        "- Fix only the target Wren project and its onboarding discovery artifacts.",
        "- Preserve valid, evidence-grounded work and do not guess missing business semantics.",
        "- Do not modify the Data Subagent online question-answering runtime.",
        "- Do not update repository progress docs or unrelated files.",
        "- Do not run wren memory index, memory fetch, or memory recall.",
        "",
        f"- Project root: {project_root}",
        f"- Target Wren project: {wren_project_dir}",
        f"- Wren home: {wren_home}",
        f"- Wren CLI: {wren_bin}",
        f"- Discovery snapshot: {discovery_snapshot_path}",
        f"- Schema manifest: {schema_manifest_path}",
        f"- Builder-owned query evidence: {evidence_path}",
        "",
        "Use only this controlled command if more StarRocks evidence is needed:",
        "```powershell",
        query_command,
        "```",
        "",
        f"Repair round: {round_index}",
        "",
        "Outer Builder validation result:",
        "```json",
        _compact_json(validation_result),
        "```",
        "",
        "Required checks before final response:",
        f"- Set WREN_HOME to {wren_home}",
        f"- Run {wren_bin} context validate from {wren_project_dir}",
        f"- Run {wren_bin} context build from {wren_project_dir}",
    ]
    if smoke_sql:
        lines.append(f"- Run {wren_bin} dry-run --sql \"{smoke_sql}\" from {wren_project_dir}")
    if extra_instructions:
        lines.extend(["", "Additional task instructions:", extra_instructions.strip()])
    lines.extend(
        [
            "",
            "Final response requirements:",
            "- Summarize the repair and evidence used.",
            "- Include validate/build/dry-run results.",
            "- List remaining semantic assumptions and open questions.",
        ]
    )
    return "\n".join(lines)


def _compact_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
