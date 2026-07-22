from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from data_subagent_context_builder.codex_runtime import CodexCliRunner

from .models import BoundedCodexTask
from .si3 import SourceCandidateExecution
from .source_plan import SourceEvaluationCommand


class CommandSourceCandidateEvaluator:
    def __init__(self, commands: list[SourceEvaluationCommand]) -> None:
        self.commands = list(commands)
        names = [command.name for command in self.commands]
        if len(names) != len(set(names)):
            raise ValueError("Source evaluation command names must be unique.")

    def evaluate(
        self,
        *,
        job: BoundedCodexTask,
        worktree_path: Path,
        target_eval_path: Path,
    ) -> dict[str, Any]:
        by_name = {command.name: command for command in self.commands}
        missing = [name for name in job.required_suites if name not in by_name]
        if missing:
            return {
                "ok": False,
                "smoke": {"ok": True},
                "regression": {
                    "ok": False,
                    "suites": [
                        {
                            "ok": False,
                            "suite_path": name,
                            "error": f"Required evaluation suite not configured: {name}",
                        }
                        for name in missing
                    ],
                },
            }

        suites: list[dict[str, Any]] = []
        for name in job.required_suites:
            command = by_name[name]
            execution = _run_evaluation_command(
                command=command,
                worktree_path=worktree_path,
                target_eval_path=target_eval_path,
            )
            suites.append(
                {
                    "ok": bool(execution["ok"]),
                    "suite_path": name,
                    "execution": execution,
                }
            )
        return {
            "ok": all(suite["ok"] for suite in suites),
            "smoke": {"ok": True},
            "regression": {
                "ok": all(suite["ok"] for suite in suites),
                "suites": suites,
            },
        }


class CodexCliSourceExecutor:
    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        codex_model: str | None = None,
        host_session_development: bool = False,
        runner_factory: Callable[[Path, Path], Any] | None = None,
    ) -> None:
        self.codex_bin = codex_bin
        self.codex_model = codex_model
        self.host_session_development = host_session_development
        self.runner_factory = runner_factory

    def execute(
        self,
        *,
        job: BoundedCodexTask,
        instruction: str,
        worktree_path: Path,
        evidence_dir: Path,
    ) -> SourceCandidateExecution:
        control_dir = evidence_dir.parent / "control"
        control_dir.mkdir(parents=True, exist_ok=True)
        output_schema_path = control_dir / "source_codex_final.schema.json"
        output_schema_path.write_text(
            json.dumps(_source_codex_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        last_message_path = control_dir / "source_codex_last_message.json"
        runner = (
            self.runner_factory(worktree_path, output_schema_path)
            if self.runner_factory is not None
            else CodexCliRunner(
                codex_bin=self.codex_bin,
                project_root=worktree_path,
                sandbox="workspace-write",
                model=self.codex_model,
                timeout_seconds=job.timeout_seconds,
                ephemeral=True,
                ignore_user_config=not self.host_session_development,
                approval_policy="never",
                output_schema_path=output_schema_path,
                sanitized_environment=True,
            )
        )
        result = runner.run(instruction, last_message_path=last_message_path)
        if not result.ok:
            return SourceCandidateExecution(
                ok=False,
                outcome="inconclusive",
                error=_bounded_text(result.stderr or result.stdout or "Codex execution failed."),
            )
        try:
            payload = json.loads(last_message_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            return SourceCandidateExecution(
                ok=False,
                outcome="inconclusive",
                error=f"Codex final response is unavailable or invalid: {exc}",
            )
        status = str(payload.get("status") or "")
        if status not in {"completed", "clarification_required"}:
            return SourceCandidateExecution(
                ok=False,
                outcome="inconclusive",
                error=f"Unsupported Codex source outcome: {status!r}",
            )
        return SourceCandidateExecution(
            ok=status == "completed",
            outcome=status,
            summary=str(payload.get("summary") or "").strip() or None,
            error=None,
        )


def _run_evaluation_command(
    *,
    command: SourceEvaluationCommand,
    worktree_path: Path,
    target_eval_path: Path,
) -> dict[str, Any]:
    replacements = {
        "{worktree}": str(worktree_path.resolve()),
        "{target_eval}": str(target_eval_path.resolve()),
    }
    args = [
        _replace_placeholders(arg, replacements)
        for arg in command.args
    ]
    try:
        completed = subprocess.run(
            args,
            cwd=worktree_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=command.timeout_seconds,
            env=_evaluation_environment(command.environment),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": 124,
            "stdout": _bounded_text(exc.stdout or ""),
            "stderr": _bounded_text(exc.stderr or ""),
            "error": f"Evaluation timed out after {command.timeout_seconds} seconds.",
            "summary": None,
        }
    except OSError as exc:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": "",
            "error": f"Evaluation process failed to start: {exc}",
            "summary": None,
        }
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": _bounded_text(completed.stdout),
        "stderr": _bounded_text(completed.stderr),
        "summary": {"completed": True},
    }


def _evaluation_environment(extra: dict[str, str]) -> dict[str, str]:
    allowed_names = (
        "COMSPEC",
        "HOME",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    )
    environment = {
        name: os.environ[name]
        for name in allowed_names
        if name in os.environ
    }
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": "src",
            **extra,
        }
    )
    return environment


def _replace_placeholders(value: str, replacements: dict[str, str]) -> str:
    resolved = value
    for marker, replacement in replacements.items():
        resolved = resolved.replace(marker, replacement)
    return resolved


def _source_codex_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "summary"],
        "properties": {
            "status": {
                "type": "string",
                "enum": ["completed", "clarification_required"],
            },
            "summary": {"type": "string"},
        },
    }


def _bounded_text(value: str, limit: int = 4000) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[-limit:]
