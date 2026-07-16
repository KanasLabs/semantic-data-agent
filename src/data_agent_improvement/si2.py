from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from data_subagent.trace_identity import fingerprint_wren_project

from .isolation import verify_isolation_receipt
from .models import (
    BoundedCodexTask,
    CandidateResultStatus,
    EvalTargetStatus,
    ImprovementJobResult,
    IsolationReceipt,
    JobStatus,
    JobTargetType,
    new_record_id,
)
from .store import ImprovementStore
from .triage import eval_target_content_sha256, require_finding_authority


@dataclass(frozen=True)
class CandidateExecution:
    ok: bool
    outcome: str
    revision_id: str | None = None
    candidate_id: str | None = None
    candidate_project_dir: str | None = None
    evaluation_summary: dict[str, Any] | None = None
    error: str | None = None


class SemanticCandidateExecutor(Protocol):
    def execute(
        self,
        *,
        job: BoundedCodexTask,
        instruction: str,
        target_eval_path: Path,
    ) -> CandidateExecution:
        ...


def prepare_semantic_job(
    *,
    store: ImprovementStore,
    eval_target_id: str,
    base_candidate_id: str,
    base_snapshot_path: Path,
    data_identity: dict[str, str | None] | None = None,
    risk_level: str = "MEDIUM",
    target_eval_repetitions: int = 3,
    timeout_seconds: int = 900,
    max_repair_rounds: int = 2,
) -> BoundedCodexTask:
    target = store.get_eval_target(eval_target_id)
    if target.status != EvalTargetStatus.FROZEN:
        raise ValueError("SI2 requires a FROZEN EvalTarget.")
    expected_hash = eval_target_content_sha256(target)
    if target.frozen_sha256 != expected_hash:
        raise ValueError("Frozen EvalTarget hash does not match its acceptance content.")
    finding = store.get_finding(target.finding_id)
    require_finding_authority(store, finding)
    resolved_base = base_snapshot_path.resolve()
    if not resolved_base.is_dir():
        raise FileNotFoundError(f"Base candidate snapshot not found: {resolved_base}")

    job_id = new_record_id("job")
    evidence_dir = store.job_dir(job_id) / "evidence"
    target_eval_path = _package_evidence(
        store=store,
        job_id=job_id,
        target=target,
        finding=finding,
    )
    manifest_path = evidence_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = _canonical_sha256(manifest)
    resolved_data_identity = dict(data_identity or {})
    if not resolved_data_identity.get("schema_fingerprint"):
        resolved_data_identity["schema_fingerprint"] = fingerprint_wren_project(
            resolved_base
        )
    if not resolved_data_identity.get("schema_fingerprint"):
        raise ValueError("SI2 requires a fingerprintable Wren base snapshot.")
    resolved_data_identity.setdefault("snapshot_id", None)
    task = BoundedCodexTask(
        schema_version=1,
        job_id=job_id,
        finding_id=finding.finding_id,
        eval_target_id=target.eval_target_id,
        eval_target_sha256=target.frozen_sha256,
        target_type=JobTargetType.WREN_CONTEXT,
        risk_level=risk_level,
        base_candidate_id=base_candidate_id,
        read_only_roots=[str(evidence_dir.resolve()), str(resolved_base)],
        evidence_manifest_sha256=manifest_hash,
        data_identity=resolved_data_identity,
        writable_root="context_builder_candidate_workspace",
        allowed_paths=["models/**", "relationships.yml", "knowledge/**", "onboarding/**"],
        forbidden_paths=["data/context_registry/**", "src/**", ".git/**"],
        required_suites=["frozen_target", "context_smoke", "regression"],
        target_eval_repetitions=target_eval_repetitions,
        timeout_seconds=timeout_seconds,
        max_repair_rounds=max_repair_rounds,
        database_access=False,
        network_access=False,
        status=JobStatus.PREPARED,
        created_at=_utc_now(),
    )
    store.create_job(task)
    if not target_eval_path.is_file():
        raise RuntimeError("Target eval packaging did not produce its suite.")
    return task


def execute_semantic_job(
    *,
    store: ImprovementStore,
    job_id: str,
    executor: SemanticCandidateExecutor,
    isolation_receipt: IsolationReceipt,
    isolation_hmac_key: str,
    isolation_environment_id: str,
) -> ImprovementJobResult:
    job = store.get_job(job_id)
    if job.status != JobStatus.PREPARED:
        raise ValueError(f"Job {job_id} is {job.status.value}, not PREPARED.")
    isolation_error = verify_isolation_receipt(
        job=job,
        receipt=isolation_receipt,
        hmac_key=isolation_hmac_key,
        environment_id=isolation_environment_id,
    )
    if isolation_error:
        raise ValueError(f"SI2 isolation receipt rejected: {isolation_error}")
    integrity_error = verify_job_integrity(store=store, job=job)
    if integrity_error:
        return _finish_without_execution(
            store=store,
            job=job,
            status=_integrity_status(integrity_error),
            error=integrity_error,
        )
    target = store.get_eval_target(job.eval_target_id)
    finding = store.get_finding(job.finding_id)
    require_finding_authority(store, finding)
    store.create_isolation_receipt(isolation_receipt)
    running = replace(job, status=JobStatus.RUNNING)
    store.replace_job(running, expected_status=JobStatus.PREPARED)
    instruction = build_semantic_job_instruction(store=store, job=running)
    target_eval_path = store.job_dir(job_id) / "evidence" / "target_eval.jsonl"
    try:
        execution = executor.execute(
            job=running,
            instruction=instruction,
            target_eval_path=target_eval_path,
        )
    except Exception as exc:
        execution = CandidateExecution(
            ok=False,
            outcome="inconclusive",
            error=f"Candidate executor failed: {exc}",
        )
    post_integrity_error = verify_job_integrity(store=store, job=running)
    if post_integrity_error:
        integrity_status = _integrity_status(post_integrity_error)
        execution = CandidateExecution(
            ok=False,
            outcome=(
                "eval_target_invalid"
                if integrity_status == CandidateResultStatus.EVAL_TARGET_INVALID
                else "inconclusive"
            ),
            revision_id=execution.revision_id,
            candidate_id=execution.candidate_id,
            candidate_project_dir=execution.candidate_project_dir,
            evaluation_summary=execution.evaluation_summary,
            error=post_integrity_error,
        )
    result_status = _result_status(execution)
    result = ImprovementJobResult(
        schema_version=1,
        job_id=job_id,
        status=result_status,
        revision_id=execution.revision_id,
        candidate_id=execution.candidate_id,
        candidate_project_dir=execution.candidate_project_dir,
        evaluation_summary=dict(execution.evaluation_summary or {}),
        error=execution.error,
        completed_at=_utc_now(),
    )
    store.create_job_result(result)
    final_job_status = {
        CandidateResultStatus.PASS: JobStatus.REVIEW_REQUIRED,
        CandidateResultStatus.FAIL: JobStatus.FAILED,
        CandidateResultStatus.INCONCLUSIVE: JobStatus.INCONCLUSIVE,
        CandidateResultStatus.NEEDS_BUSINESS_REVIEW: JobStatus.NEEDS_BUSINESS_REVIEW,
        CandidateResultStatus.EVAL_TARGET_INVALID: JobStatus.EVAL_TARGET_INVALID,
    }[result_status]
    store.replace_job(
        replace(running, status=final_job_status),
        expected_status=JobStatus.RUNNING,
    )
    return result


def verify_job_integrity(
    *,
    store: ImprovementStore,
    job: BoundedCodexTask,
) -> str | None:
    target = store.get_eval_target(job.eval_target_id)
    if target.status != EvalTargetStatus.FROZEN:
        return f"EvalTarget is no longer FROZEN: {target.status.value}"
    content_hash = eval_target_content_sha256(target)
    if content_hash != job.eval_target_sha256 or target.frozen_sha256 != content_hash:
        return "EvalTarget content/hash changed after job preparation."
    evidence_dir = store.job_dir(job.job_id) / "evidence"
    manifest_path = evidence_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return f"Evidence manifest is unavailable or invalid: {exc}"
    if _canonical_sha256(manifest) != job.evidence_manifest_sha256:
        return "Evidence manifest hash changed after job preparation."
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, list):
        return "Evidence manifest files list is invalid."
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            return "Evidence manifest contains an invalid file entry."
        path = (evidence_dir / entry["path"]).resolve()
        try:
            path.relative_to(evidence_dir.resolve())
        except ValueError:
            return "Evidence manifest path escapes the evidence directory."
        if not path.is_file() or _file_sha256(path) != entry.get("sha256"):
            return f"Evidence file hash mismatch: {entry['path']}"
    return None


def build_semantic_job_instruction(
    *,
    store: ImprovementStore,
    job: BoundedCodexTask,
) -> str:
    evidence_dir = store.job_dir(job.job_id) / "evidence"
    return "\n".join(
        [
            "This is a bounded SI2 Wren Context candidate task.",
            "",
            f"Job ID: {job.job_id}",
            f"Frozen EvalTarget SHA-256: {job.eval_target_sha256}",
            f"Read-only evidence bundle: {evidence_dir.resolve()}",
            "",
            "Required boundaries:",
            "- Read manifest.json first and use only the packaged evidence.",
            "- Do not edit the evidence bundle, base candidate, Registry, source code, or Git state.",
            "- Modify only the isolated Wren candidate created by the outer Context Builder.",
            f"- Allowed candidate paths: {', '.join(job.allowed_paths)}",
            f"- Forbidden paths: {', '.join(job.forbidden_paths)}",
            "- Do not use network access or direct database credentials.",
            "- Do not approve, publish, merge, deploy, or weaken the frozen target.",
            "- If business truth is missing, return clarification_required instead of guessing.",
            "",
            "Acceptance:",
            f"- Target suite: {(evidence_dir / 'target_eval.jsonl').resolve()}",
            f"- Required repetitions: {job.target_eval_repetitions}",
            "- The outer controller runs target, smoke, and regression suites.",
            "- Stop at a reviewable candidate; publication is a separate human action.",
        ]
    )


def _package_evidence(
    *,
    store: ImprovementStore,
    job_id: str,
    target: Any,
    finding: Any,
) -> Path:
    case_records = [store.get_case(case_id).to_dict() for case_id in finding.case_ids]
    feedback_records = [
        store.get_feedback(feedback_id).to_dict()
        for feedback_id in finding.confirmed_business_truth_feedback_ids
    ]
    authority_records = [
        store.get_authority_decision(authority_id).to_dict()
        for authority_id in finding.authority_decision_ids
    ]
    artifacts: list[Path] = []
    artifacts.append(
        store.write_job_artifact(job_id, Path("evidence/finding.json"), finding.to_dict())
    )
    artifacts.append(
        store.write_job_artifact(job_id, Path("evidence/eval_target.json"), target.to_dict())
    )
    artifacts.append(
        store.write_job_artifact(job_id, Path("evidence/cases.json"), case_records)
    )
    artifacts.append(
        store.write_job_artifact(job_id, Path("evidence/feedback.json"), feedback_records)
    )
    artifacts.append(
        store.write_job_artifact(job_id, Path("evidence/authority.json"), authority_records)
    )
    target_eval_path = store.write_job_text_artifact(
        job_id,
        Path("evidence/target_eval.jsonl"),
        json.dumps(_target_eval_case(target), ensure_ascii=False),
    )
    artifacts.append(target_eval_path)
    evidence_dir = store.job_dir(job_id) / "evidence"
    manifest = {
        "schema_version": 1,
        "job_id": job_id,
        "files": [
            {
                "path": path.relative_to(evidence_dir).as_posix(),
                "sha256": _file_sha256(path),
            }
            for path in sorted(artifacts)
        ],
        "excludes": [
            "raw trace payloads",
            "result_preview rows",
            "credentials and environment values",
        ],
    }
    store.write_job_artifact(job_id, Path("evidence/manifest.json"), manifest)
    return target_eval_path


def _target_eval_case(target: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "eval_id": f"si2_{target.eval_target_id[-12:]}",
        "question": target.question,
        "dataset": "si2_frozen_target",
        "db_id": "candidate_context",
        "expected_status": "success",
        "expected_answer_contains": list(target.semantic_constraints.required_units),
        "expected_answer_not_contains": list(target.semantic_constraints.forbidden_units),
        "expected_sql_contains": list(target.semantic_constraints.required_filters),
    }
    if target.result_contract.expected_value is not None:
        case["expected_any_values"] = [target.result_contract.expected_value]
    if target.result_contract.numeric_tolerance is not None:
        case["expected_numeric_tolerance"] = target.result_contract.numeric_tolerance
    return case


def _finish_without_execution(
    *,
    store: ImprovementStore,
    job: BoundedCodexTask,
    status: CandidateResultStatus,
    error: str,
) -> ImprovementJobResult:
    result = ImprovementJobResult(
        schema_version=1,
        job_id=job.job_id,
        status=status,
        revision_id=None,
        candidate_id=None,
        candidate_project_dir=None,
        evaluation_summary={},
        error=error,
        completed_at=_utc_now(),
    )
    store.create_job_result(result)
    final_status = (
        JobStatus.EVAL_TARGET_INVALID
        if status == CandidateResultStatus.EVAL_TARGET_INVALID
        else JobStatus.INCONCLUSIVE
    )
    store.replace_job(replace(job, status=final_status), expected_status=JobStatus.PREPARED)
    return result


def _result_status(execution: CandidateExecution) -> CandidateResultStatus:
    normalized = execution.outcome.strip().lower()
    if normalized == "clarification_required":
        return CandidateResultStatus.NEEDS_BUSINESS_REVIEW
    if normalized == "eval_target_invalid":
        return CandidateResultStatus.EVAL_TARGET_INVALID
    if normalized == "inconclusive":
        return CandidateResultStatus.INCONCLUSIVE
    return CandidateResultStatus.PASS if execution.ok else CandidateResultStatus.FAIL


def _integrity_status(error: str) -> CandidateResultStatus:
    return (
        CandidateResultStatus.EVAL_TARGET_INVALID
        if error.startswith("EvalTarget")
        else CandidateResultStatus.INCONCLUSIVE
    )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _file_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
