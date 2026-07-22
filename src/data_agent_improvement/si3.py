from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .evaluation import (
    CandidateEvaluation,
    CandidateEvaluationReason,
    CandidateEvaluationStatus,
    classify_candidate_evaluation,
)
from .models import (
    BoundedCodexTask,
    CandidateResultStatus,
    EvalTargetStatus,
    JobStatus,
    JobTargetType,
    new_record_id,
)
from .si2 import _canonical_sha256, _package_evidence, verify_job_integrity
from .routing import require_source_routing_decision, routing_decision_sha256
from .source_plan import (
    SourceEvaluationCommand,
    load_source_evaluation_plan,
    source_evaluation_plan,
    source_evaluation_plan_sha256,
)
from .store import ImprovementStore
from .triage import eval_target_content_sha256, require_finding_authority


DEFAULT_SOURCE_FORBIDDEN_PATHS = (
    ".git/**",
    "data/improvement_registry/**",
    "data/tmp/**",
    "data/traces/**",
    "deepseek_apikey.txt",
    "中转配置及apikey.txt",
    ".env",
    ".env.*",
)

SOURCE_DEVELOPMENT_ONLY_WARNING = (
    "DEVELOPMENT_ONLY SI3 host execution uses a linked Git worktree and the current "
    "host Codex session. It creates no formal JobResult, cannot authorize a pull "
    "request, merge, or deployment, and leaves the Job PREPARED."
)


@dataclass(frozen=True)
class SourceCandidateExecution:
    ok: bool
    outcome: str
    summary: str | None = None
    error: str | None = None


class SourceCandidateExecutor(Protocol):
    def execute(
        self,
        *,
        job: BoundedCodexTask,
        instruction: str,
        worktree_path: Path,
        evidence_dir: Path,
    ) -> SourceCandidateExecution:
        ...


class SourceCandidateEvaluator(Protocol):
    def evaluate(
        self,
        *,
        job: BoundedCodexTask,
        worktree_path: Path,
        target_eval_path: Path,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class SourcePullRequestCandidate:
    schema_version: int
    candidate_id: str
    job_id: str
    base_commit: str
    branch_name: str
    worktree_path: str
    changed_paths: list[str]
    patch_path: str
    patch_sha256: str
    evaluation: CandidateEvaluation
    development_only: bool
    release_eligible: bool
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("SourcePullRequestCandidate schema_version must be 1.")
        if not self.candidate_id.startswith("sourcecandidate_"):
            raise ValueError("Source candidate ID must start with sourcecandidate_.")
        if not self.changed_paths:
            raise ValueError("Source PR candidate must contain at least one changed path.")
        if self.release_eligible and self.development_only:
            raise ValueError("Development-only source candidates cannot be release eligible.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "job_id": self.job_id,
            "base_commit": self.base_commit,
            "branch_name": self.branch_name,
            "worktree_path": self.worktree_path,
            "changed_paths": list(self.changed_paths),
            "patch_path": self.patch_path,
            "patch_sha256": self.patch_sha256,
            "evaluation": self.evaluation.to_dict(),
            "development_only": self.development_only,
            "release_eligible": self.release_eligible,
            "created_at": self.created_at,
        }


def prepare_source_job(
    *,
    store: ImprovementStore,
    eval_target_id: str,
    routing_decision_id: str,
    repository_root: Path,
    allowed_paths: list[str],
    evaluation_commands: list[SourceEvaluationCommand],
    base_ref: str = "HEAD",
    forbidden_paths: list[str] | None = None,
    risk_level: str = "HIGH",
    target_eval_repetitions: int = 1,
    timeout_seconds: int = 900,
    max_repair_rounds: int = 2,
) -> BoundedCodexTask:
    target = store.get_eval_target(eval_target_id)
    if target.status != EvalTargetStatus.FROZEN:
        raise ValueError("SI3 requires a FROZEN EvalTarget.")
    expected_hash = eval_target_content_sha256(target)
    if target.frozen_sha256 != expected_hash:
        raise ValueError("Frozen EvalTarget hash does not match its acceptance content.")
    finding = store.get_finding(target.finding_id)
    require_finding_authority(store, finding)
    routing_decision = require_source_routing_decision(
        store=store,
        routing_decision_id=routing_decision_id,
        finding_id=finding.finding_id,
        eval_target_id=target.eval_target_id,
    )
    repository = _resolve_repository(repository_root)
    base_commit = _git_text(repository, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    normalized_allowed = _normalize_patterns(allowed_paths, name="allowed_paths")
    normalized_forbidden = _normalize_patterns(
        [*DEFAULT_SOURCE_FORBIDDEN_PATHS, *(forbidden_paths or [])],
        name="forbidden_paths",
    )
    evaluation_plan = source_evaluation_plan(evaluation_commands)
    suites = [command.name for command in evaluation_commands]

    job_id = new_record_id("job")
    evidence_dir = store.job_dir(job_id) / "evidence"
    _package_evidence(
        store=store,
        job_id=job_id,
        target=target,
        finding=finding,
        eval_namespace="si3",
        additional_records={
            "routing_decision.json": routing_decision.to_dict(),
        },
    )
    store.write_job_artifact(
        job_id,
        Path("control/source_evaluation_plan.json"),
        evaluation_plan,
    )
    manifest = json.loads(
        (evidence_dir / "manifest.json").read_text(encoding="utf-8")
    )
    tree_fingerprint = _git_tree_fingerprint(repository, base_commit)
    task = BoundedCodexTask(
        schema_version=1,
        job_id=job_id,
        finding_id=finding.finding_id,
        eval_target_id=target.eval_target_id,
        eval_target_sha256=target.frozen_sha256,
        target_type=JobTargetType.SOURCE_CODE,
        risk_level=risk_level,
        base_candidate_id=base_commit,
        read_only_roots=[str(evidence_dir.resolve()), str(repository)],
        evidence_manifest_sha256=_canonical_sha256(manifest),
        data_identity={
            "schema_fingerprint": tree_fingerprint,
            "snapshot_id": base_commit,
            "evaluation_plan_sha256": source_evaluation_plan_sha256(evaluation_plan),
            "routing_decision_sha256": routing_decision_sha256(routing_decision),
        },
        writable_root="source_worktree",
        allowed_paths=normalized_allowed,
        forbidden_paths=normalized_forbidden,
        required_suites=suites,
        target_eval_repetitions=target_eval_repetitions,
        timeout_seconds=timeout_seconds,
        max_repair_rounds=max_repair_rounds,
        database_access=False,
        network_access=False,
        status=JobStatus.PREPARED,
        created_at=_utc_now(),
        routing_decision_id=routing_decision.routing_decision_id,
    )
    store.create_job(task)
    return task


def execute_source_job_development(
    *,
    store: ImprovementStore,
    job_id: str,
    executor: SourceCandidateExecutor,
    evaluator: SourceCandidateEvaluator,
) -> dict[str, Any]:
    job = store.get_job(job_id)
    if job.target_type != JobTargetType.SOURCE_CODE:
        raise ValueError("SI3 development execution requires a SOURCE_CODE Job.")
    if job.status != JobStatus.PREPARED:
        raise ValueError(f"Job {job_id} is {job.status.value}, not PREPARED.")
    integrity_error = verify_source_job_integrity(store=store, job=job)
    if integrity_error:
        return _development_report(job=job, error=integrity_error)

    repository = Path(job.read_only_roots[1]).resolve()
    worktree_path = store.job_dir(job_id) / "workspace" / "source"
    branch_name = f"si3/{job.job_id}"
    try:
        _create_worktree(
            repository=repository,
            worktree_path=worktree_path,
            branch_name=branch_name,
            base_commit=job.base_candidate_id,
        )
    except Exception as exc:
        return _development_report(
            job=job,
            worktree_path=worktree_path,
            branch_name=branch_name,
            error=f"Failed to create source worktree: {exc}",
        )

    evidence_dir = store.job_dir(job_id) / "evidence"
    instruction = "\n".join(
        [
            SOURCE_DEVELOPMENT_ONLY_WARNING,
            "",
            build_source_job_instruction(store=store, job=job, worktree_path=worktree_path),
        ]
    )
    try:
        execution = executor.execute(
            job=job,
            instruction=instruction,
            worktree_path=worktree_path,
            evidence_dir=evidence_dir,
        )
    except Exception as exc:
        execution = SourceCandidateExecution(
            ok=False,
            outcome="inconclusive",
            error=f"Source candidate executor failed: {exc}",
        )
    normalized_outcome = execution.outcome.strip().lower()
    if normalized_outcome == "clarification_required":
        return _development_report(
            job=job,
            worktree_path=worktree_path,
            branch_name=branch_name,
            status=CandidateResultStatus.NEEDS_BUSINESS_REVIEW,
            error=execution.error,
        )
    if not execution.ok:
        return _development_report(
            job=job,
            worktree_path=worktree_path,
            branch_name=branch_name,
            error=execution.error or "Source candidate executor did not complete.",
        )

    post_execution_error = verify_source_job_integrity(store=store, job=job)
    if post_execution_error:
        return _development_report(
            job=job,
            worktree_path=worktree_path,
            branch_name=branch_name,
            status=_integrity_status(post_execution_error),
            error=post_execution_error,
        )
    if _git_text(worktree_path, "rev-parse", "HEAD") != job.base_candidate_id:
        return _development_report(
            job=job,
            worktree_path=worktree_path,
            branch_name=branch_name,
            error="Source executor changed Git history; SI3 permits file edits only.",
        )
    changed_paths = _changed_paths(worktree_path, job.base_candidate_id)
    policy_error = _changed_path_policy_error(job=job, changed_paths=changed_paths)
    if policy_error:
        return _development_report(
            job=job,
            worktree_path=worktree_path,
            branch_name=branch_name,
            status=CandidateResultStatus.FAIL,
            evaluation=_policy_failure(policy_error, changed_paths),
            changed_paths=changed_paths,
            error=policy_error,
        )

    target_eval_path = evidence_dir / "target_eval.jsonl"
    try:
        raw_evaluation = evaluator.evaluate(
            job=job,
            worktree_path=worktree_path,
            target_eval_path=target_eval_path,
        )
    except Exception as exc:
        return _development_report(
            job=job,
            worktree_path=worktree_path,
            branch_name=branch_name,
            changed_paths=changed_paths,
            error=f"Source candidate evaluator failed: {exc}",
        )
    post_evaluation_error = verify_source_job_integrity(store=store, job=job)
    if post_evaluation_error:
        return _development_report(
            job=job,
            worktree_path=worktree_path,
            branch_name=branch_name,
            changed_paths=changed_paths,
            status=_integrity_status(post_evaluation_error),
            error=post_evaluation_error,
        )
    changed_after_evaluation = _changed_paths(worktree_path, job.base_candidate_id)
    if changed_after_evaluation != changed_paths:
        return _development_report(
            job=job,
            worktree_path=worktree_path,
            branch_name=branch_name,
            changed_paths=changed_after_evaluation,
            error="Outer evaluation modified the source candidate worktree.",
        )

    evaluation = classify_candidate_evaluation(dict(raw_evaluation or {}))
    candidate = _write_pull_request_candidate(
        store=store,
        job=job,
        worktree_path=worktree_path,
        branch_name=branch_name,
        changed_paths=changed_paths,
        evaluation=evaluation,
    )
    return _development_report(
        job=job,
        worktree_path=worktree_path,
        branch_name=branch_name,
        status=_candidate_result_status(evaluation),
        evaluation=evaluation,
        evaluation_summary=raw_evaluation,
        changed_paths=changed_paths,
        candidate=candidate,
    )


def verify_source_job_integrity(
    *,
    store: ImprovementStore,
    job: BoundedCodexTask,
) -> str | None:
    if job.target_type != JobTargetType.SOURCE_CODE:
        return f"Job target type is {job.target_type.value}, not SOURCE_CODE."
    if not job.routing_decision_id:
        return "Source Job does not identify a RoutingDecision."
    try:
        routing_decision = require_source_routing_decision(
            store=store,
            routing_decision_id=job.routing_decision_id,
            finding_id=job.finding_id,
            eval_target_id=job.eval_target_id,
        )
    except ValueError as exc:
        return str(exc)
    if routing_decision_sha256(routing_decision) != job.data_identity.get(
        "routing_decision_sha256"
    ):
        return "RoutingDecision content/hash changed after Job preparation."
    evidence_error = verify_job_integrity(store=store, job=job)
    if evidence_error:
        return evidence_error
    if len(job.read_only_roots) < 2:
        return "Source Job does not identify its base repository."
    try:
        repository = _resolve_repository(Path(job.read_only_roots[1]))
        resolved_commit = _git_text(
            repository,
            "rev-parse",
            "--verify",
            f"{job.base_candidate_id}^{{commit}}",
        )
    except (ValueError, RuntimeError) as exc:
        return f"Source base repository or commit is unavailable: {exc}"
    if resolved_commit != job.base_candidate_id:
        return "Source base commit identity changed after Job preparation."
    if job.data_identity.get("snapshot_id") != job.base_candidate_id:
        return "Source Job snapshot_id does not match its base commit."
    if _git_tree_fingerprint(repository, resolved_commit) != job.data_identity.get(
        "schema_fingerprint"
    ):
        return "Source base tree fingerprint changed after Job preparation."
    plan_hash = job.data_identity.get("evaluation_plan_sha256")
    if not plan_hash:
        return "Source Job does not bind an evaluation plan."
    try:
        commands = load_source_evaluation_plan(
            path=store.job_dir(job.job_id) / "control" / "source_evaluation_plan.json",
            expected_sha256=plan_hash,
        )
    except ValueError as exc:
        return str(exc)
    if [command.name for command in commands] != job.required_suites:
        return "Source evaluation plan suites do not match the Job contract."
    return None


def build_source_job_instruction(
    *,
    store: ImprovementStore,
    job: BoundedCodexTask,
    worktree_path: Path,
) -> str:
    evidence_dir = store.job_dir(job.job_id) / "evidence"
    return "\n".join(
        [
            "This is a bounded SI3 source-code candidate task.",
            "",
            f"Job ID: {job.job_id}",
            f"Base commit: {job.base_candidate_id}",
            f"Frozen EvalTarget SHA-256: {job.eval_target_sha256}",
            f"Reviewed RoutingDecision: {job.routing_decision_id}",
            f"Writable Git worktree: {worktree_path.resolve()}",
            f"Read-only evidence bundle: {evidence_dir.resolve()}",
            "",
            "Required boundaries:",
            "- Read AGENTS.md and the evidence manifest before editing.",
            "- Treat the EvalTarget and evidence bundle as immutable outer-owned inputs.",
            f"- Modify only these paths: {', '.join(job.allowed_paths)}",
            f"- Never modify these paths: {', '.join(job.forbidden_paths)}",
            "- Do not commit, branch, push, merge, open a PR, approve, or deploy.",
            "- Do not change Git history, repository configuration, or hooks.",
            "- Do not access credentials, the network, databases, or paths outside the worktree ",
            "  except the explicitly named read-only evidence bundle.",
            "- If business truth is missing, return clarification_required instead of guessing.",
            "",
            "Acceptance:",
            f"- Required outer suites: {', '.join(job.required_suites)}",
            f"- Frozen target repetitions: {job.target_eval_repetitions}",
            "- The outer controller, not Codex, decides PASS, FAIL, or BLOCKED.",
            "- Stop after producing reviewable file edits; the controller creates the patch.",
        ]
    )


def _write_pull_request_candidate(
    *,
    store: ImprovementStore,
    job: BoundedCodexTask,
    worktree_path: Path,
    branch_name: str,
    changed_paths: list[str],
    evaluation: CandidateEvaluation,
) -> SourcePullRequestCandidate:
    untracked = _git_lines(worktree_path, "ls-files", "--others", "--exclude-standard")
    if untracked:
        _run_git(worktree_path, "add", "--intent-to-add", "--", *untracked)
    patch = _git_text(
        worktree_path,
        "diff",
        "--binary",
        "--no-ext-diff",
        job.base_candidate_id,
        "--",
        strip=False,
    )
    if not patch:
        raise RuntimeError("Source candidate patch is empty.")
    patch_path = store.write_job_text_artifact(
        job.job_id,
        Path("artifacts/pr_candidate.patch"),
        patch,
    )
    candidate = SourcePullRequestCandidate(
        schema_version=1,
        candidate_id=f"sourcecandidate_{uuid.uuid4().hex}",
        job_id=job.job_id,
        base_commit=job.base_candidate_id,
        branch_name=branch_name,
        worktree_path=str(worktree_path.resolve()),
        changed_paths=changed_paths,
        patch_path=str(patch_path.resolve()),
        patch_sha256=_file_sha256(patch_path),
        evaluation=evaluation,
        development_only=True,
        release_eligible=False,
        created_at=_utc_now(),
    )
    store.write_job_artifact(
        job.job_id,
        Path("artifacts/pr_candidate.json"),
        candidate.to_dict(),
    )
    return candidate


def _development_report(
    *,
    job: BoundedCodexTask,
    worktree_path: Path | None = None,
    branch_name: str | None = None,
    status: CandidateResultStatus = CandidateResultStatus.INCONCLUSIVE,
    evaluation: CandidateEvaluation | None = None,
    evaluation_summary: dict[str, Any] | None = None,
    changed_paths: list[str] | None = None,
    candidate: SourcePullRequestCandidate | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "job_id": job.job_id,
        "target_type": job.target_type.value,
        "development_only": True,
        "formal_result_recorded": False,
        "isolation_receipt_used": False,
        "release_eligible": False,
        "candidate_status": status.value,
        "candidate_id": candidate.candidate_id if candidate else None,
        "branch_name": branch_name,
        "worktree_path": str(worktree_path.resolve()) if worktree_path else None,
        "changed_paths": list(changed_paths or []),
        "candidate_evaluation": evaluation.to_dict() if evaluation else None,
        "evaluation_summary": dict(evaluation_summary or {}),
        "pr_candidate": candidate.to_dict() if candidate else None,
        "error": error,
        "job_status_after": JobStatus.PREPARED.value,
        "warning": SOURCE_DEVELOPMENT_ONLY_WARNING,
        "completed_at": _utc_now(),
    }


def _candidate_result_status(
    evaluation: CandidateEvaluation,
) -> CandidateResultStatus:
    if evaluation.status == CandidateEvaluationStatus.PASS:
        return CandidateResultStatus.PASS
    if evaluation.status == CandidateEvaluationStatus.FAIL:
        return CandidateResultStatus.FAIL
    if evaluation.reason == CandidateEvaluationReason.EVAL_TARGET_INVALID:
        return CandidateResultStatus.EVAL_TARGET_INVALID
    return CandidateResultStatus.INCONCLUSIVE


def _policy_failure(message: str, changed_paths: list[str]) -> CandidateEvaluation:
    return CandidateEvaluation(
        schema_version=1,
        status=CandidateEvaluationStatus.FAIL,
        reason=CandidateEvaluationReason.ASSERTION_FAILED,
        message=message,
        details={"changed_paths": changed_paths},
    )


def _integrity_status(error: str) -> CandidateResultStatus:
    return (
        CandidateResultStatus.EVAL_TARGET_INVALID
        if error.startswith("EvalTarget")
        else CandidateResultStatus.INCONCLUSIVE
    )


def _resolve_repository(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"Git repository not found: {resolved}")
    top_level = Path(_git_text(resolved, "rev-parse", "--show-toplevel")).resolve()
    if top_level != resolved:
        raise ValueError(f"repository_root must be the Git top-level directory: {top_level}")
    return resolved


def _create_worktree(
    *,
    repository: Path,
    worktree_path: Path,
    branch_name: str,
    base_commit: str,
) -> None:
    if worktree_path.exists():
        raise FileExistsError(f"Source worktree already exists: {worktree_path}")
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    _run_git(
        repository,
        "worktree",
        "add",
        "--no-track",
        "-b",
        branch_name,
        str(worktree_path.resolve()),
        base_commit,
    )


def _changed_paths(worktree_path: Path, base_commit: str) -> list[str]:
    tracked = _git_lines(
        worktree_path,
        "diff",
        "--name-only",
        "--relative",
        base_commit,
        "--",
    )
    staged = _git_lines(
        worktree_path,
        "diff",
        "--cached",
        "--name-only",
        "--relative",
        base_commit,
        "--",
    )
    untracked = _git_lines(
        worktree_path,
        "ls-files",
        "--others",
        "--exclude-standard",
    )
    return sorted({_normalize_changed_path(path) for path in [*tracked, *staged, *untracked]})


def _changed_path_policy_error(
    *,
    job: BoundedCodexTask,
    changed_paths: list[str],
) -> str | None:
    if not changed_paths:
        return "Source candidate made no reviewable file changes."
    forbidden = [
        path
        for path in changed_paths
        if any(_path_matches(path, pattern) for pattern in job.forbidden_paths)
    ]
    if forbidden:
        return "Source candidate changed forbidden paths: " + ", ".join(forbidden)
    outside = [
        path
        for path in changed_paths
        if not any(_path_matches(path, pattern) for pattern in job.allowed_paths)
    ]
    if outside:
        return "Source candidate changed paths outside the allowlist: " + ", ".join(outside)
    return None


def _normalize_patterns(patterns: list[str], *, name: str) -> list[str]:
    normalized: list[str] = []
    for pattern in patterns:
        value = pattern.strip().replace("\\", "/")
        pure = PurePosixPath(value)
        if not value or pure.is_absolute() or ".." in pure.parts:
            raise ValueError(f"{name} must contain only relative project glob patterns.")
        normalized.append(value)
    if name == "allowed_paths" and not normalized:
        raise ValueError("SI3 requires at least one allowed source path.")
    return list(dict.fromkeys(normalized))


def _normalize_changed_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    pure = PurePosixPath(normalized)
    if not normalized or pure.is_absolute() or ".." in pure.parts:
        raise RuntimeError(f"Git reported an unsafe changed path: {path!r}")
    return normalized


def _path_matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**") and path == pattern[:-3].rstrip("/"):
        return True
    return fnmatch.fnmatchcase(path, pattern)


def _git_tree_fingerprint(repository: Path, commit: str) -> str:
    listing = _run_git(
        repository,
        "ls-tree",
        "-r",
        "--full-tree",
        commit,
    ).stdout
    return f"sha256:{hashlib.sha256(listing).hexdigest()}"


def _run_git(repository: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed with {completed.returncode}")
    return completed


def _git_text(
    repository: Path,
    *args: str,
    strip: bool = True,
) -> str:
    text = _run_git(repository, *args).stdout.decode("utf-8", errors="replace")
    return text.strip() if strip else text


def _git_lines(repository: Path, *args: str) -> list[str]:
    output = _git_text(repository, *args)
    return [line for line in output.splitlines() if line]


def _file_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
