from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .models import (
    AuthorityDecision,
    BoundedCodexTask,
    EvalTarget,
    EvalTargetStatus,
    FeedbackRecord,
    FailureCase,
    FindingStatus,
    GroupedFinding,
    ImprovementJobResult,
    IsolationReceipt,
    JobStatus,
    TriageStatus,
    validate_identifier,
)


class ImprovementStoreError(RuntimeError):
    pass


class RecordNotFoundError(ImprovementStoreError):
    pass


class ImmutableRecordError(ImprovementStoreError):
    pass


class ImprovementStore:
    def __init__(self, registry_root: Path) -> None:
        self.registry_root = registry_root.resolve()

    def create_feedback(self, feedback: FeedbackRecord) -> Path:
        path = self._feedback_path(feedback.feedback_id)
        if path.exists():
            raise ImmutableRecordError(f"Feedback already exists: {feedback.feedback_id}")
        self._write_json(path, feedback.to_dict())
        return path

    def get_feedback(self, feedback_id: str) -> FeedbackRecord:
        return FeedbackRecord.from_dict(self._read_json(self._feedback_path(feedback_id)))

    def list_feedback(self, trace_id: str | None = None) -> list[FeedbackRecord]:
        if trace_id is not None:
            validate_identifier("trace_id", trace_id, "trace", 32)
        root = self.registry_root / "feedback"
        if not root.exists():
            return []
        records = [
            FeedbackRecord.from_dict(self._read_json(path))
            for path in sorted(root.glob("feedback_*.json"))
        ]
        if trace_id is not None:
            records = [record for record in records if record.trace_id == trace_id]
        return records

    def create_case(self, case: FailureCase) -> tuple[Path, bool]:
        path = self._case_path(case.case_id)
        if path.exists():
            existing = FailureCase.from_dict(self._read_json(path))
            if existing.to_dict() != case.to_dict():
                raise ImmutableRecordError(
                    f"Case identity collision with different content: {case.case_id}"
                )
            return path, False
        self._write_json(path, case.to_dict())
        return path, True

    def get_case(self, case_id: str) -> FailureCase:
        return FailureCase.from_dict(self._read_json(self._case_path(case_id)))

    def list_cases(self, triage_status: str | None = None) -> list[FailureCase]:
        status = TriageStatus(triage_status) if triage_status is not None else None
        root = self.registry_root / "cases"
        if not root.exists():
            return []
        records = [
            FailureCase.from_dict(self._read_json(path))
            for path in sorted(root.glob("case_*/case.json"))
        ]
        if status is not None:
            records = [record for record in records if record.triage_status == status]
        return records

    def create_authority_decision(self, decision: AuthorityDecision) -> Path:
        path = self._authority_path(decision.authority_id)
        if path.exists():
            raise ImmutableRecordError(
                f"Authority decision already exists: {decision.authority_id}"
            )
        self._write_json(path, decision.to_dict())
        return path

    def get_authority_decision(self, authority_id: str) -> AuthorityDecision:
        return AuthorityDecision.from_dict(self._read_json(self._authority_path(authority_id)))

    def list_authority_decisions(
        self,
        feedback_id: str | None = None,
    ) -> list[AuthorityDecision]:
        if feedback_id is not None:
            validate_identifier("feedback_id", feedback_id, "feedback", 32)
        root = self.registry_root / "authority"
        if not root.exists():
            return []
        records = [
            AuthorityDecision.from_dict(self._read_json(path))
            for path in sorted(root.glob("authority_*.json"))
        ]
        if feedback_id is not None:
            records = [record for record in records if record.feedback_id == feedback_id]
        return records

    def create_finding(self, finding: GroupedFinding) -> Path:
        path = self._finding_path(finding.finding_id)
        if path.exists():
            raise ImmutableRecordError(f"Finding already exists: {finding.finding_id}")
        self._write_json(path, finding.to_dict())
        return path

    def get_finding(self, finding_id: str) -> GroupedFinding:
        return GroupedFinding.from_dict(self._read_json(self._finding_path(finding_id)))

    def list_findings(self, status: str | None = None) -> list[GroupedFinding]:
        parsed_status = FindingStatus(status) if status is not None else None
        root = self.registry_root / "findings"
        if not root.exists():
            return []
        records = [
            GroupedFinding.from_dict(self._read_json(path))
            for path in sorted(root.glob("finding_*.json"))
        ]
        if parsed_status is not None:
            records = [record for record in records if record.status == parsed_status]
        return records

    def replace_finding(
        self,
        finding: GroupedFinding,
        *,
        expected_status: FindingStatus,
    ) -> Path:
        path = self._finding_path(finding.finding_id)
        existing = self.get_finding(finding.finding_id)
        if existing.status != expected_status:
            raise ImmutableRecordError(
                f"Finding {finding.finding_id} is {existing.status.value}, "
                f"expected {expected_status.value}."
            )
        if _finding_content(existing) != _finding_content(finding):
            raise ImmutableRecordError("GroupedFinding evidence cannot change in place.")
        self._write_json(path, finding.to_dict())
        return path

    def create_eval_target(self, target: EvalTarget) -> Path:
        path = self._eval_target_path(target.eval_target_id)
        if path.exists():
            raise ImmutableRecordError(
                f"EvalTarget already exists: {target.eval_target_id}"
            )
        self._write_json(path, target.to_dict())
        return path

    def get_eval_target(self, eval_target_id: str) -> EvalTarget:
        return EvalTarget.from_dict(self._read_json(self._eval_target_path(eval_target_id)))

    def list_eval_targets(
        self,
        *,
        finding_id: str | None = None,
        status: str | None = None,
    ) -> list[EvalTarget]:
        if finding_id is not None:
            validate_identifier("finding_id", finding_id, "finding", 32)
        parsed_status = EvalTargetStatus(status) if status is not None else None
        root = self.registry_root / "eval_targets"
        if not root.exists():
            return []
        records = [
            EvalTarget.from_dict(self._read_json(path))
            for path in sorted(root.glob("evaltarget_*.json"))
        ]
        if finding_id is not None:
            records = [record for record in records if record.finding_id == finding_id]
        if parsed_status is not None:
            records = [record for record in records if record.status == parsed_status]
        return records

    def replace_eval_target(
        self,
        target: EvalTarget,
        *,
        expected_status: EvalTargetStatus,
    ) -> Path:
        path = self._eval_target_path(target.eval_target_id)
        existing = self.get_eval_target(target.eval_target_id)
        if existing.status != expected_status:
            raise ImmutableRecordError(
                f"EvalTarget {target.eval_target_id} is {existing.status.value}, "
                f"expected {expected_status.value}."
            )
        if _eval_target_content(existing) != _eval_target_content(target):
            raise ImmutableRecordError("EvalTarget acceptance content cannot change in place.")
        self._write_json(path, target.to_dict())
        return path

    def create_job(self, job: BoundedCodexTask) -> Path:
        path = self._job_path(job.job_id)
        if path.exists():
            raise ImmutableRecordError(f"Job already exists: {job.job_id}")
        self._write_json(path, job.to_dict())
        return path

    def get_job(self, job_id: str) -> BoundedCodexTask:
        return BoundedCodexTask.from_dict(self._read_json(self._job_path(job_id)))

    def replace_job(
        self,
        job: BoundedCodexTask,
        *,
        expected_status: JobStatus,
    ) -> Path:
        path = self._job_path(job.job_id)
        existing = self.get_job(job.job_id)
        if existing.status != expected_status:
            raise ImmutableRecordError(
                f"Job {job.job_id} is {existing.status.value}, "
                f"expected {expected_status.value}."
            )
        if _job_content(existing) != _job_content(job):
            raise ImmutableRecordError("BoundedCodexTask content cannot change in place.")
        self._write_json(path, job.to_dict())
        return path

    def create_job_result(self, result: ImprovementJobResult) -> Path:
        path = self.job_dir(result.job_id) / "result.json"
        if path.exists():
            raise ImmutableRecordError(f"Job result already exists: {result.job_id}")
        self._write_json(path, result.to_dict())
        return path

    def get_job_result(self, job_id: str) -> ImprovementJobResult:
        return ImprovementJobResult.from_dict(
            self._read_json(self.job_dir(job_id) / "result.json")
        )

    def create_isolation_receipt(self, receipt: IsolationReceipt) -> Path:
        path = self.job_dir(receipt.job_id) / "control" / "isolation_receipt.json"
        if path.exists():
            raise ImmutableRecordError(
                f"Isolation receipt already exists: {receipt.job_id}"
            )
        self._write_json(path, receipt.to_dict())
        return path

    def get_isolation_receipt(self, job_id: str) -> IsolationReceipt:
        return IsolationReceipt.from_dict(
            self._read_json(self.job_dir(job_id) / "control" / "isolation_receipt.json")
        )

    def write_job_artifact(
        self,
        job_id: str,
        relative_path: Path,
        value: dict[str, Any] | list[Any],
    ) -> Path:
        root = self.job_dir(job_id)
        path = _safe_child_path(root, relative_path)
        if path.exists():
            raise ImmutableRecordError(f"Job artifact already exists: {path}")
        _reject_secret_fields(value)
        payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        self._atomic_write(path, payload)
        return path

    def write_job_text_artifact(
        self,
        job_id: str,
        relative_path: Path,
        text: str,
    ) -> Path:
        root = self.job_dir(job_id)
        path = _safe_child_path(root, relative_path)
        if path.exists():
            raise ImmutableRecordError(f"Job artifact already exists: {path}")
        self._atomic_write(path, text.rstrip() + "\n")
        return path

    def job_dir(self, job_id: str) -> Path:
        validate_identifier("job_id", job_id, "job", 32)
        return self.registry_root / "jobs" / job_id

    def write_report(self, report_id: str, markdown: str) -> Path:
        if not re.fullmatch(r"report_[0-9a-f]{32}", report_id):
            raise ValueError(f"Invalid report_id: {report_id!r}")
        path = self.registry_root / "reports" / f"{report_id}.md"
        if path.exists():
            raise ImmutableRecordError(f"Report already exists: {report_id}")
        self._atomic_write(path, markdown.rstrip() + "\n")
        return path

    def relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.registry_root).as_posix()

    def _feedback_path(self, feedback_id: str) -> Path:
        validate_identifier("feedback_id", feedback_id, "feedback", 32)
        return self.registry_root / "feedback" / f"{feedback_id}.json"

    def _case_path(self, case_id: str) -> Path:
        validate_identifier("case_id", case_id, "case", 24)
        return self.registry_root / "cases" / case_id / "case.json"

    def _authority_path(self, authority_id: str) -> Path:
        validate_identifier("authority_id", authority_id, "authority", 32)
        return self.registry_root / "authority" / f"{authority_id}.json"

    def _finding_path(self, finding_id: str) -> Path:
        validate_identifier("finding_id", finding_id, "finding", 32)
        return self.registry_root / "findings" / f"{finding_id}.json"

    def _eval_target_path(self, eval_target_id: str) -> Path:
        validate_identifier("eval_target_id", eval_target_id, "evaltarget", 32)
        return self.registry_root / "eval_targets" / f"{eval_target_id}.json"

    def _job_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise RecordNotFoundError(f"Improvement record not found: {path}")
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ImprovementStoreError(f"Invalid registry JSON at {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ImprovementStoreError(f"Registry record must be a JSON object: {path}")
        return loaded

    def _write_json(self, path: Path, value: dict[str, Any]) -> None:
        _reject_secret_fields(value)
        payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        self._atomic_write(path, payload)

    def _atomic_write(self, path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


def new_report_id() -> str:
    return f"report_{uuid.uuid4().hex}"


_SECRET_FIELD_NAMES = {
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "authorization_header",
    "access_token",
    "refresh_token",
    "secret",
}


def _reject_secret_fields(value: Any, path: str = "record") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _SECRET_FIELD_NAMES:
                raise ValueError(f"Secret field is not allowed in Improvement Store: {path}.{key}")
            _reject_secret_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_fields(item, f"{path}[{index}]")


def _eval_target_content(target: EvalTarget) -> tuple[Any, ...]:
    return (
        target.schema_version,
        target.eval_target_id,
        target.version,
        target.finding_id,
        target.question,
        target.result_contract,
        target.semantic_constraints,
        tuple(target.sql_hints),
        tuple(target.evidence_refs),
        target.created_at,
        target.supersedes_eval_target_id,
    )


def _finding_content(finding: GroupedFinding) -> tuple[Any, ...]:
    return (
        finding.schema_version,
        finding.finding_id,
        finding.context_id,
        finding.grouping_mode,
        tuple(finding.case_ids),
        tuple(finding.representative_trace_ids),
        finding.root_cause_candidate,
        tuple(finding.confirmed_business_truth_feedback_ids),
        tuple(finding.authority_decision_ids),
        tuple(finding.business_scopes),
        finding.created_at,
    )


def _job_content(job: BoundedCodexTask) -> tuple[Any, ...]:
    return (
        job.schema_version,
        job.job_id,
        job.finding_id,
        job.eval_target_id,
        job.eval_target_sha256,
        job.target_type,
        job.risk_level,
        job.base_candidate_id,
        tuple(job.read_only_roots),
        job.evidence_manifest_sha256,
        tuple(sorted(job.data_identity.items())),
        job.writable_root,
        tuple(job.allowed_paths),
        tuple(job.forbidden_paths),
        tuple(job.required_suites),
        job.target_eval_repetitions,
        job.timeout_seconds,
        job.max_repair_rounds,
        job.database_access,
        job.network_access,
        job.created_at,
    )


def _safe_child_path(root: Path, relative_path: Path) -> Path:
    if relative_path.is_absolute():
        raise ValueError("Job artifact path must be relative.")
    resolved = (root / relative_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Job artifact path escapes the job directory.") from exc
    return resolved
