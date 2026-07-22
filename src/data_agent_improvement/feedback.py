from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence import load_trace_by_id, project_relative_path, resolve_evidence_path
from .ingestion import (
    _context_identity,
    _context_identity_missing,
    _runtime_identity_missing,
    _trace_schema_version,
)
from .models import (
    Actor,
    CorrectionPair,
    EvidenceRef,
    ExpectedCorrection,
    FeedbackRecord,
    FeedbackType,
    FailureCase,
    FailurePhase,
    ObservedCorrection,
    Provenance,
    Sentiment,
    Signal,
    SourceIdentity,
    SourceType,
    TriageStatus,
    deterministic_case_id,
    new_feedback_id,
    sha256_text,
)
from .store import ImprovementStore


@dataclass(frozen=True)
class FeedbackCreationResult:
    feedback: FeedbackRecord
    case: FailureCase | None
    feedback_path: Path
    case_path: Path | None
    case_created: bool


def record_feedback(
    *,
    store: ImprovementStore,
    project_root: Path,
    trace_path: Path,
    trace_id: str,
    feedback_type: FeedbackType,
    sentiment: Sentiment,
    comment: str,
    provenance: Provenance,
    actor: Actor,
    expected_answer: str | None = None,
    expected_sql: str | None = None,
    business_statements: list[str] | None = None,
    supersedes_feedback_id: str | None = None,
    allow_missing_trace: bool = False,
) -> FeedbackCreationResult:
    resolved_trace_path = resolve_evidence_path(
        trace_path,
        project_root,
        require_exists=not allow_missing_trace,
    )
    trace = (
        load_trace_by_id(resolved_trace_path, trace_id)
        if resolved_trace_path.is_file()
        else None
    )
    if trace is None and not allow_missing_trace:
        raise ValueError(f"Trace not found: {trace_id}")
    statements = list(business_statements or [])
    has_expected = bool(expected_answer or expected_sql or statements)
    if trace is None and has_expected:
        raise ValueError("A correction pair requires the observed trace.")
    if supersedes_feedback_id is not None:
        store.get_feedback(supersedes_feedback_id)
    correction_pair = None
    if has_expected and trace is not None:
        correction_pair = CorrectionPair(
            observed=ObservedCorrection(
                trace_id=trace_id,
                answer_sha256=sha256_text(_optional_text(trace.get("answer"))),
                sql_sha256=sha256_text(_optional_text(trace.get("final_sql"))),
            ),
            expected=ExpectedCorrection(
                answer=expected_answer,
                sql=expected_sql,
                business_statements=statements,
            ),
        )
    created_at = datetime.now(timezone.utc).isoformat()
    feedback = FeedbackRecord(
        schema_version=1,
        feedback_id=new_feedback_id(),
        trace_id=trace_id,
        feedback_type=feedback_type,
        sentiment=sentiment,
        comment=comment,
        correction_pair=correction_pair,
        provenance=provenance,
        actor=actor,
        created_at=created_at,
        supersedes_feedback_id=supersedes_feedback_id,
    )
    feedback_path = store.create_feedback(feedback)
    if not _creates_failure_case(feedback):
        return FeedbackCreationResult(
            feedback=feedback,
            case=None,
            feedback_path=feedback_path,
            case_path=None,
            case_created=False,
        )
    case = failure_case_from_feedback(
        feedback=feedback,
        trace=trace,
        trace_path=project_relative_path(resolved_trace_path, project_root),
        feedback_path=project_relative_path(feedback_path, project_root),
    )
    case_path, case_created = store.create_case(case)
    return FeedbackCreationResult(
        feedback=feedback,
        case=case,
        feedback_path=feedback_path,
        case_path=case_path,
        case_created=case_created,
    )


def verify_observed_hashes(feedback: FeedbackRecord, trace: dict[str, Any]) -> None:
    pair = feedback.correction_pair
    if pair is None:
        return
    actual_answer = sha256_text(_optional_text(trace.get("answer")))
    actual_sql = sha256_text(_optional_text(trace.get("final_sql")))
    if pair.observed.answer_sha256 != actual_answer:
        raise ValueError("Observed answer hash does not match the referenced trace.")
    if pair.observed.sql_sha256 != actual_sql:
        raise ValueError("Observed SQL hash does not match the referenced trace.")


def failure_case_from_feedback(
    *,
    feedback: FeedbackRecord,
    trace: dict[str, Any] | None,
    trace_path: str,
    feedback_path: str,
) -> FailureCase:
    canonical = f"USER_FEEDBACK:{feedback.feedback_id}"
    signals = [
        Signal(
            signal_type=f"FEEDBACK_{feedback.feedback_type.value}",
            message=feedback.comment or f"{feedback.feedback_type.value} feedback recorded.",
            value=feedback.sentiment.value,
        )
    ]
    refs = [EvidenceRef("FEEDBACK", feedback.feedback_id, feedback_path)]
    if trace is not None:
        verify_observed_hashes(feedback, trace)
        refs.insert(0, EvidenceRef("TRACE", feedback.trace_id, trace_path))
    return FailureCase(
        schema_version=1,
        case_id=deterministic_case_id(canonical),
        source_type=SourceType.USER_FEEDBACK,
        source_identity=SourceIdentity(
            trace_id=feedback.trace_id,
            feedback_id=feedback.feedback_id,
        ),
        context_identity=_context_identity(trace or {}),
        question=str((trace or {}).get("question") or "(question unavailable)"),
        observed_status=str((trace or {}).get("status") or "feedback_only"),
        failure_phase=FailurePhase.USER_FEEDBACK,
        signals=signals,
        evidence_refs=refs,
        triage_status=TriageStatus.UNTRIAGED,
        root_cause=None,
        created_at=feedback.created_at,
        updated_at=feedback.created_at,
        trace_schema_version=_trace_schema_version(trace),
        runtime_identity_missing=_runtime_identity_missing(trace or {}),
        context_identity_missing=_context_identity_missing(trace or {}),
    )


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _creates_failure_case(feedback: FeedbackRecord) -> bool:
    return feedback.sentiment == Sentiment.NEGATIVE or feedback.feedback_type in {
        FeedbackType.CORRECTION,
        FeedbackType.BUSINESS_TRUTH,
        FeedbackType.EXPECTED_ANSWER,
        FeedbackType.EXPECTED_SQL,
    }
