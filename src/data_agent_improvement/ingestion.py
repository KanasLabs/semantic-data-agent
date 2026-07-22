from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import project_relative_path, read_jsonl_objects, resolve_evidence_path
from .models import (
    ContextIdentity,
    EvidenceRef,
    FailureCase,
    FailurePhase,
    Signal,
    SourceIdentity,
    SourceType,
    TriageStatus,
    deterministic_case_id,
)
from .store import ImprovementStore


@dataclass(frozen=True)
class IngestionSummary:
    scanned: int
    eligible: int
    created: int
    existing: int
    case_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "eligible": self.eligible,
            "created": self.created,
            "existing": self.existing,
            "case_ids": self.case_ids,
        }


def ingest_traces(
    *,
    store: ImprovementStore,
    trace_path: Path,
    project_root: Path,
) -> IngestionSummary:
    resolved = resolve_evidence_path(trace_path, project_root)
    relative_path = project_relative_path(resolved, project_root)
    scanned = 0
    eligible = 0
    created = 0
    case_ids: list[str] = []
    for _, trace in read_jsonl_objects(resolved):
        scanned += 1
        status = str(trace.get("status") or "")
        if status not in {"failed", "need_clarification"}:
            continue
        eligible += 1
        case = failure_case_from_trace(trace, relative_path)
        _, was_created = store.create_case(case)
        created += int(was_created)
        case_ids.append(case.case_id)
    return IngestionSummary(
        scanned=scanned,
        eligible=eligible,
        created=created,
        existing=eligible - created,
        case_ids=case_ids,
    )


def ingest_eval_run(
    *,
    store: ImprovementStore,
    run_path: Path,
    run_id: str,
    project_root: Path,
    trace_path: Path | None = None,
) -> IngestionSummary:
    if not run_id.strip():
        raise ValueError("run_id must not be empty.")
    resolved_run = resolve_evidence_path(run_path, project_root)
    relative_run_path = project_relative_path(resolved_run, project_root)
    trace_index: dict[str, dict[str, Any]] = {}
    relative_trace_path: str | None = None
    if trace_path is not None:
        resolved_trace = resolve_evidence_path(trace_path, project_root)
        relative_trace_path = project_relative_path(resolved_trace, project_root)
        trace_index = {
            str(record.get("trace_id")): record
            for _, record in read_jsonl_objects(resolved_trace)
            if record.get("trace_id")
        }
    scanned = 0
    eligible = 0
    created = 0
    case_ids: list[str] = []
    for _, record in read_jsonl_objects(resolved_run):
        scanned += 1
        status = str(record.get("status") or "")
        review_status = str(record.get("review_status") or "")
        if status != "fail" and review_status != "needs_triage":
            continue
        eligible += 1
        trace_id = record.get("trace_id")
        trace = trace_index.get(str(trace_id)) if trace_id else None
        case = failure_case_from_eval(
            record=record,
            run_id=run_id,
            relative_run_path=relative_run_path,
            trace=trace,
            relative_trace_path=relative_trace_path,
        )
        _, was_created = store.create_case(case)
        created += int(was_created)
        case_ids.append(case.case_id)
    return IngestionSummary(
        scanned=scanned,
        eligible=eligible,
        created=created,
        existing=eligible - created,
        case_ids=case_ids,
    )


def failure_case_from_trace(trace: dict[str, Any], relative_path: str) -> FailureCase:
    trace_id = str(trace.get("trace_id") or "")
    phase = _trace_failure_phase(trace)
    canonical = f"RUNTIME_TRACE:{trace_id}:{phase.value}"
    created_at = _timestamp_or_epoch(trace.get("created_at"))
    error = _sanitize_external_text(trace.get("error"))
    status = str(trace.get("status") or "failed")
    signals = [
        Signal(
            signal_type="TRACE_ERROR" if error else "TRACE_STATUS",
            message=error or f"Trace completed with status {status}.",
            value=status,
        )
    ]
    return FailureCase(
        schema_version=1,
        case_id=deterministic_case_id(canonical),
        source_type=SourceType.RUNTIME_TRACE,
        source_identity=SourceIdentity(trace_id=trace_id),
        context_identity=_context_identity(trace),
        question=_sanitize_external_text(trace.get("question")) or "(question unavailable)",
        observed_status=status,
        failure_phase=phase,
        signals=signals,
        evidence_refs=[EvidenceRef("TRACE", trace_id, relative_path)],
        triage_status=TriageStatus.UNTRIAGED,
        root_cause=None,
        created_at=created_at,
        updated_at=created_at,
        trace_schema_version=_trace_schema_version(trace),
        runtime_identity_missing=_runtime_identity_missing(trace),
        context_identity_missing=_context_identity_missing(trace),
    )


def failure_case_from_eval(
    *,
    record: dict[str, Any],
    run_id: str,
    relative_run_path: str,
    trace: dict[str, Any] | None,
    relative_trace_path: str | None,
) -> FailureCase:
    eval_id = str(record.get("eval_id") or "")
    canonical = f"EVAL_RECORD:{run_id}:{eval_id}"
    trace_id = str(record.get("trace_id")) if record.get("trace_id") else None
    signals = _eval_signals(record)
    evidence_refs = [EvidenceRef("EVAL_RUN", run_id, relative_run_path)]
    if trace_id and relative_trace_path:
        evidence_refs.append(EvidenceRef("TRACE", trace_id, relative_trace_path))
    created_at = _timestamp_or_epoch(record.get("started_at"))
    return FailureCase(
        schema_version=1,
        case_id=deterministic_case_id(canonical),
        source_type=SourceType.EVAL_RECORD,
        source_identity=SourceIdentity(
            trace_id=trace_id,
            eval_run_id=run_id,
            eval_id=eval_id,
        ),
        context_identity=_context_identity(trace or {}),
        question=_sanitize_external_text(record.get("question")) or "(question unavailable)",
        observed_status=str(record.get("status") or "unknown"),
        failure_phase=FailurePhase.EVAL_ASSERTION,
        signals=signals,
        evidence_refs=evidence_refs,
        triage_status=TriageStatus.UNTRIAGED,
        root_cause=None,
        created_at=created_at,
        updated_at=created_at,
        trace_schema_version=_trace_schema_version(trace) if trace else None,
        runtime_identity_missing=_runtime_identity_missing(trace or {}),
        context_identity_missing=_context_identity_missing(trace or {}),
    )


def _trace_failure_phase(trace: dict[str, Any]) -> FailurePhase:
    if trace.get("status") == "need_clarification":
        return FailurePhase.CLARITY
    if _has_failed_result(trace.get("dry_run_results")):
        return FailurePhase.WREN_DRY_RUN
    if _has_failed_result(trace.get("dry_plan_results")):
        return FailurePhase.WREN_DRY_PLAN
    error = str(trace.get("error") or "").lower()
    if "read-only" in error or "guardrail" in error or "only select" in error:
        return FailurePhase.SQL_GUARDRAIL
    if not trace.get("context_used"):
        return FailurePhase.CONTEXT
    if trace.get("final_sql"):
        return FailurePhase.EXECUTION
    if trace.get("sql_attempts"):
        return FailurePhase.SQL_GENERATION
    return FailurePhase.UNKNOWN


def _has_failed_result(value: Any) -> bool:
    return isinstance(value, list) and any(
        isinstance(item, dict) and item.get("ok") is False for item in value
    )


def _eval_signals(record: dict[str, Any]) -> list[Signal]:
    signals: list[Signal] = []
    reasons = record.get("failure_reasons")
    if isinstance(reasons, list):
        for reason in reasons:
            message = _sanitize_external_text(reason)
            signal_type = "EVAL_ASSERTION_FAILED"
            value: str | None = None
            if message.startswith("answer missing expected fragment"):
                signal_type = "ANSWER_MISSING_EXPECTED_FRAGMENT"
                value = _expected_fragment_value(message)
            elif message.startswith("answer contains forbidden fragment"):
                signal_type = "ANSWER_CONTAINS_FORBIDDEN_FRAGMENT"
            elif message.startswith("row count"):
                signal_type = "ROW_COUNT_MISMATCH"
            signals.append(Signal(signal_type, message, value))
    if record.get("review_status") == "needs_triage":
        signals.append(
            Signal(
                "EVAL_NEEDS_TRIAGE",
                "Eval record requires human triage; this does not prove a product defect.",
                "needs_triage",
            )
        )
    if not signals:
        signals.append(Signal("EVAL_FAILED", "Eval record did not pass.", "fail"))
    return signals


def _expected_fragment_value(message: str) -> str | None:
    _, _, raw_value = message.partition(":")
    try:
        parsed = ast.literal_eval(raw_value.strip())
    except (SyntaxError, ValueError):
        return raw_value.strip() or None
    if isinstance(parsed, list) and len(parsed) == 1:
        return str(parsed[0])
    return str(parsed)


def _context_identity(trace: dict[str, Any]) -> ContextIdentity:
    value = trace.get("context_identity")
    data = value if isinstance(value, dict) else {}
    return ContextIdentity(
        context_id=_optional_string(data.get("context_id")),
        candidate_id=_optional_string(data.get("candidate_id")),
        context_version=_optional_int(data.get("context_version")),
        publication_id=_optional_string(data.get("publication_id")),
        wren_project_fingerprint=_optional_string(data.get("wren_project_fingerprint")),
    )


def _runtime_identity_missing(trace: dict[str, Any]) -> bool:
    value = trace.get("runtime_identity")
    return not isinstance(value, dict) or not value.get("runtime_name")


def _context_identity_missing(trace: dict[str, Any]) -> bool:
    value = trace.get("context_identity")
    return not isinstance(value, dict) or not (
        value.get("context_id") or value.get("wren_project_fingerprint")
    )


def _trace_schema_version(trace: dict[str, Any] | None) -> int:
    if not trace:
        return 1
    value = trace.get("schema_version", 1)
    return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else 1


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None and str(value).strip() else None


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _timestamp_or_epoch(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return "1970-01-01T00:00:00+00:00"


_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|authorization|access[_-]?token|"
    r"refresh[_-]?token)\s*[:=]\s*[^\s,;]+"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"(?i)://[^\s/:]+:[^\s/@]+@")


def _sanitize_external_text(value: Any, limit: int = 2_000) -> str:
    text = str(value or "").replace("\x00", "").strip()
    text = _SECRET_VALUE_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _URL_CREDENTIAL_PATTERN.sub("://[REDACTED]@", text)
    return text if len(text) <= limit else text[: limit - 3] + "..."
