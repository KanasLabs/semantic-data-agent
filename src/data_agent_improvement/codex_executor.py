from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_subagent_context_builder.codex_runtime import CodexCliRunner
from data_subagent_context_builder.revision_engine import revise_candidate
from data_subagent_context_builder.revision_eval import RevisionEvalRunner
from data_subagent_context_builder.revision_store import RevisionStore, RiskLevel
from data_subagent_context_builder.skill_onboarding import WrenRunner

from .models import BoundedCodexTask
from .si2 import CandidateExecution


class ContextBuilderSemanticExecutor:
    def __init__(
        self,
        *,
        project_root: Path,
        context_registry_root: Path,
        wren_home: Path,
        wren_bin: Path,
        codex_bin: str = "codex",
        codex_model: str | None = None,
        regression_suites: list[Path] | None = None,
        smoke_sql: str | None = None,
        eval_model: str | None = None,
        eval_query_limit: int | None = None,
        eval_timeout_seconds: int = 1800,
        wren_runner: WrenRunner | None = None,
        eval_runner: RevisionEvalRunner | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.context_registry_root = context_registry_root.resolve()
        self.wren_home = wren_home.resolve()
        self.wren_bin = wren_bin.resolve()
        self.codex_bin = codex_bin
        self.codex_model = codex_model
        self.regression_suites = [path.resolve() for path in regression_suites or []]
        self.smoke_sql = smoke_sql
        self.eval_model = eval_model
        self.eval_query_limit = eval_query_limit
        self.eval_timeout_seconds = eval_timeout_seconds
        self.wren_runner = wren_runner
        self.eval_runner = eval_runner

    def execute(
        self,
        *,
        job: BoundedCodexTask,
        instruction: str,
        target_eval_path: Path,
    ) -> CandidateExecution:
        registered_base = RevisionStore(self.context_registry_root).get_candidate(
            job.base_candidate_id
        )
        registered_base_path = Path(registered_base.project_path).resolve()
        declared_base_path = Path(job.read_only_roots[1]).resolve()
        if registered_base_path != declared_base_path:
            raise ValueError(
                "Registered base candidate path does not match the prepared SI2 snapshot."
            )
        control_dir = target_eval_path.parents[1] / "control"
        control_dir.mkdir(parents=True, exist_ok=True)
        output_schema_path = control_dir / "codex_final_response.schema.json"
        output_schema_path.write_text(
            json.dumps(_codex_final_response_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        def runner_factory(candidate_project_dir: Path) -> CodexCliRunner:
            return CodexCliRunner(
                codex_bin=self.codex_bin,
                project_root=candidate_project_dir,
                sandbox="workspace-write",
                model=self.codex_model,
                timeout_seconds=job.timeout_seconds,
                ephemeral=True,
                ignore_user_config=True,
                approval_policy="never",
                output_schema_path=output_schema_path,
                sanitized_environment=True,
            )

        result = revise_candidate(
            registry_root=self.context_registry_root,
            base_candidate_id=job.base_candidate_id,
            user_instruction=instruction,
            project_root=self.project_root,
            wren_home=self.wren_home,
            wren_bin=self.wren_bin,
            requested_scope=job.allowed_paths,
            risk_level=RiskLevel(job.risk_level),
            smoke_sql=self.smoke_sql,
            execute_codex=True,
            codex_bin=self.codex_bin,
            codex_model=self.codex_model,
            codex_timeout_seconds=job.timeout_seconds,
            max_repair_rounds=job.max_repair_rounds,
            run_evals=True,
            regression_suites=(
                [target_eval_path] * job.target_eval_repetitions
                + self.regression_suites
            ),
            eval_model=self.eval_model,
            eval_query_limit=self.eval_query_limit,
            eval_timeout_seconds=self.eval_timeout_seconds,
            wren_runner=self.wren_runner,
            codex_runner_factory=runner_factory,
            eval_runner=self.eval_runner,
        )
        revision_status = str(result.get("revision_status") or "")
        if revision_status == "CLARIFICATION_REQUIRED":
            outcome = "clarification_required"
        else:
            outcome = "completed" if result.get("ok") else "failed"
        return CandidateExecution(
            ok=bool(result.get("ok")),
            outcome=outcome,
            revision_id=_optional_string(result.get("revision_id")),
            candidate_id=_optional_string(result.get("candidate_id")),
            candidate_project_dir=_optional_string(result.get("candidate_project_dir")),
            evaluation_summary=dict(result.get("eval") or {}),
            error=None if result.get("ok") else _execution_error(result),
        )


def _codex_final_response_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "summary", "clarification_questions"],
        "properties": {
            "status": {
                "type": "string",
                "enum": ["completed", "clarification_required"],
            },
            "summary": {"type": "string"},
            "clarification_questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["prompt", "rationale"],
                    "properties": {
                        "prompt": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                },
            },
        },
    }


def _execution_error(result: dict[str, Any]) -> str:
    for key in ("error", "validation_error", "revision_status", "candidate_status"):
        value = result.get(key)
        if value:
            return f"{key}: {value}"
    return "Context Builder candidate execution failed."


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None and str(value).strip() else None
