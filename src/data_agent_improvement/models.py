from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FeedbackType(str, Enum):
    RATING = "RATING"
    CORRECTION = "CORRECTION"
    BUSINESS_TRUTH = "BUSINESS_TRUTH"
    EXPECTED_ANSWER = "EXPECTED_ANSWER"
    EXPECTED_SQL = "EXPECTED_SQL"
    OTHER = "OTHER"


class Sentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class ActorType(str, Enum):
    FEEDBACK_PROVIDER = "FEEDBACK_PROVIDER"
    BUSINESS_CONTRIBUTOR = "BUSINESS_CONTRIBUTOR"
    AUTHORIZED_BUSINESS_CONFIRMER = "AUTHORIZED_BUSINESS_CONFIRMER"
    CONTEXT_APPROVER = "CONTEXT_APPROVER"


class AuthorityStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    PROJECT_CONFIRMED = "PROJECT_CONFIRMED"
    REVOKED = "REVOKED"


class SourceType(str, Enum):
    RUNTIME_TRACE = "RUNTIME_TRACE"
    EVAL_RECORD = "EVAL_RECORD"
    USER_FEEDBACK = "USER_FEEDBACK"


class FailurePhase(str, Enum):
    CLARITY = "CLARITY"
    CONTEXT = "CONTEXT"
    SQL_GENERATION = "SQL_GENERATION"
    SQL_GUARDRAIL = "SQL_GUARDRAIL"
    WREN_DRY_PLAN = "WREN_DRY_PLAN"
    WREN_DRY_RUN = "WREN_DRY_RUN"
    EXECUTION = "EXECUTION"
    SUMMARIZATION = "SUMMARIZATION"
    EVAL_ASSERTION = "EVAL_ASSERTION"
    USER_FEEDBACK = "USER_FEEDBACK"
    UNKNOWN = "UNKNOWN"


class TriageStatus(str, Enum):
    UNTRIAGED = "UNTRIAGED"
    TRIAGE_REQUIRED = "TRIAGE_REQUIRED"
    WAITING_FOR_BUSINESS_TRUTH = "WAITING_FOR_BUSINESS_TRUTH"
    READY_FOR_TASK = "READY_FOR_TASK"
    DISMISSED = "DISMISSED"


class AuthorityDecisionType(str, Enum):
    CONFIRM = "CONFIRM"
    REVOKE = "REVOKE"


class GroupingMode(str, Enum):
    SINGLETON = "SINGLETON"
    CLUSTER = "CLUSTER"


class RootCauseCandidate(str, Enum):
    BUSINESS_SEMANTIC_GAP = "BUSINESS_SEMANTIC_GAP"
    CONTEXT_GAP = "CONTEXT_GAP"
    SQL_GENERATION_DEFECT = "SQL_GENERATION_DEFECT"
    SQL_GUARDRAIL_DEFECT = "SQL_GUARDRAIL_DEFECT"
    WREN_RUNTIME_FAILURE = "WREN_RUNTIME_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    SUMMARIZATION_GAP = "SUMMARIZATION_GAP"
    EVAL_TARGET_QUALITY = "EVAL_TARGET_QUALITY"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    UNKNOWN = "UNKNOWN"


class FindingStatus(str, Enum):
    WAITING_FOR_BUSINESS_TRUTH = "WAITING_FOR_BUSINESS_TRUTH"
    EVAL_TARGET_REQUIRED = "EVAL_TARGET_REQUIRED"
    DISMISSED = "DISMISSED"


class EvalTargetStatus(str, Enum):
    DRAFT = "DRAFT"
    NEEDS_BUSINESS_REVIEW = "NEEDS_BUSINESS_REVIEW"
    APPROVED = "APPROVED"
    FROZEN = "FROZEN"
    SUPERSEDED = "SUPERSEDED"
    INVALID = "INVALID"


class JobTargetType(str, Enum):
    WREN_CONTEXT = "WREN_CONTEXT"


class JobStatus(str, Enum):
    PREPARED = "PREPARED"
    RUNNING = "RUNNING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NEEDS_BUSINESS_REVIEW = "NEEDS_BUSINESS_REVIEW"
    EVAL_TARGET_INVALID = "EVAL_TARGET_INVALID"


class CandidateResultStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NEEDS_BUSINESS_REVIEW = "NEEDS_BUSINESS_REVIEW"
    EVAL_TARGET_INVALID = "EVAL_TARGET_INVALID"


@dataclass(frozen=True)
class ObservedCorrection:
    trace_id: str
    answer_sha256: str
    sql_sha256: str

    def __post_init__(self) -> None:
        validate_identifier("trace_id", self.trace_id, "trace", 32)
        validate_sha256("answer_sha256", self.answer_sha256)
        validate_sha256("sql_sha256", self.sql_sha256)


@dataclass(frozen=True)
class ExpectedCorrection:
    answer: str | None = None
    sql: str | None = None
    business_statements: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_optional_text("expected answer", self.answer)
        _validate_optional_text("expected SQL", self.sql)
        _validate_text_list("business statements", self.business_statements)
        if not self.answer and not self.sql and not self.business_statements:
            raise ValueError(
                "Expected correction must contain an answer, SQL, or business statement."
            )


@dataclass(frozen=True)
class CorrectionPair:
    observed: ObservedCorrection
    expected: ExpectedCorrection


@dataclass(frozen=True)
class Provenance:
    provenance_type: str
    source_id: str
    statement: str

    def __post_init__(self) -> None:
        _require_text("provenance_type", self.provenance_type)
        _require_text("provenance source_id", self.source_id)
        _require_text("provenance statement", self.statement)


@dataclass(frozen=True)
class Actor:
    actor_id: str
    actor_type: ActorType = ActorType.FEEDBACK_PROVIDER
    authority_status: AuthorityStatus = AuthorityStatus.UNVERIFIED
    authorized_context_ids: list[str] = field(default_factory=list)
    authorized_scopes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_text("actor_id", self.actor_id)
        _validate_text_list("authorized_context_ids", self.authorized_context_ids)
        _validate_text_list("authorized_scopes", self.authorized_scopes)


@dataclass(frozen=True)
class FeedbackRecord:
    schema_version: int
    feedback_id: str
    trace_id: str
    feedback_type: FeedbackType
    sentiment: Sentiment
    comment: str
    correction_pair: CorrectionPair | None
    provenance: Provenance
    actor: Actor
    created_at: str
    supersedes_feedback_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("FeedbackRecord schema_version must be 1.")
        validate_identifier("feedback_id", self.feedback_id, "feedback", 32)
        validate_identifier("trace_id", self.trace_id, "trace", 32)
        if self.supersedes_feedback_id is not None:
            validate_identifier(
                "supersedes_feedback_id", self.supersedes_feedback_id, "feedback", 32
            )
        _validate_timestamp(self.created_at)
        _validate_optional_text("comment", self.comment)
        if self.feedback_type == FeedbackType.CORRECTION and self.correction_pair is None:
            raise ValueError("CORRECTION feedback requires a correction pair.")
        if self.feedback_type == FeedbackType.BUSINESS_TRUTH:
            statements = (
                self.correction_pair.expected.business_statements
                if self.correction_pair is not None
                else []
            )
            if not statements:
                raise ValueError("BUSINESS_TRUTH feedback requires a business statement.")
        if self.feedback_type == FeedbackType.EXPECTED_ANSWER:
            if self.correction_pair is None or not self.correction_pair.expected.answer:
                raise ValueError("EXPECTED_ANSWER feedback requires an expected answer.")
        if self.feedback_type == FeedbackType.EXPECTED_SQL:
            if self.correction_pair is None or not self.correction_pair.expected.sql:
                raise ValueError("EXPECTED_SQL feedback requires expected SQL.")
        if (
            self.correction_pair is not None
            and self.correction_pair.observed.trace_id != self.trace_id
        ):
            raise ValueError("Correction pair trace_id must match FeedbackRecord trace_id.")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeedbackRecord":
        pair_data = data.get("correction_pair")
        pair = None
        if pair_data is not None and not isinstance(pair_data, dict):
            raise ValueError("correction_pair must be a JSON object or null.")
        if isinstance(pair_data, dict):
            observed = pair_data.get("observed")
            expected = pair_data.get("expected")
            if not isinstance(observed, dict) or not isinstance(expected, dict):
                raise ValueError("correction_pair requires observed and expected objects.")
            pair = CorrectionPair(
                observed=ObservedCorrection(**observed),
                expected=ExpectedCorrection(
                    answer=expected.get("answer"),
                    sql=expected.get("sql"),
                    business_statements=list(expected.get("business_statements") or []),
                ),
            )
        provenance_data = _require_dict(data, "provenance")
        actor_data = _require_dict(data, "actor")
        return cls(
            schema_version=int(data["schema_version"]),
            feedback_id=str(data["feedback_id"]),
            trace_id=str(data["trace_id"]),
            feedback_type=FeedbackType(data["feedback_type"]),
            sentiment=Sentiment(data["sentiment"]),
            comment=str(data.get("comment") or ""),
            correction_pair=pair,
            provenance=Provenance(**provenance_data),
            actor=Actor(
                actor_id=str(actor_data["actor_id"]),
                actor_type=ActorType(actor_data.get("actor_type", "FEEDBACK_PROVIDER")),
                authority_status=AuthorityStatus(
                    actor_data.get("authority_status", "UNVERIFIED")
                ),
                authorized_context_ids=list(actor_data.get("authorized_context_ids") or []),
                authorized_scopes=list(actor_data.get("authorized_scopes") or []),
            ),
            created_at=str(data["created_at"]),
            supersedes_feedback_id=data.get("supersedes_feedback_id"),
        )


@dataclass(frozen=True)
class SourceIdentity:
    trace_id: str | None = None
    eval_run_id: str | None = None
    eval_id: str | None = None
    feedback_id: str | None = None

    def __post_init__(self) -> None:
        if self.trace_id is not None:
            validate_identifier("trace_id", self.trace_id, "trace", 32)
        if self.feedback_id is not None:
            validate_identifier("feedback_id", self.feedback_id, "feedback", 32)
        _validate_optional_text("eval_run_id", self.eval_run_id)
        _validate_optional_text("eval_id", self.eval_id)


@dataclass(frozen=True)
class ContextIdentity:
    context_id: str | None = None
    candidate_id: str | None = None
    context_version: int | None = None
    publication_id: str | None = None
    wren_project_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.context_version is not None and self.context_version < 1:
            raise ValueError("context_version must be at least 1.")
        if self.wren_project_fingerprint is not None:
            validate_sha256("wren_project_fingerprint", self.wren_project_fingerprint)
        for label, value in (
            ("context_id", self.context_id),
            ("candidate_id", self.candidate_id),
            ("publication_id", self.publication_id),
        ):
            _validate_optional_text(label, value)


@dataclass(frozen=True)
class Signal:
    signal_type: str
    message: str
    value: str | int | float | bool | None = None

    def __post_init__(self) -> None:
        _require_text("signal_type", self.signal_type)
        _require_text("signal message", self.message)


@dataclass(frozen=True)
class EvidenceRef:
    evidence_type: str
    evidence_id: str
    path: str

    def __post_init__(self) -> None:
        _require_text("evidence_type", self.evidence_type)
        _require_text("evidence_id", self.evidence_id)
        _require_text("evidence path", self.path)


@dataclass(frozen=True)
class FailureCase:
    schema_version: int
    case_id: str
    source_type: SourceType
    source_identity: SourceIdentity
    context_identity: ContextIdentity
    question: str
    observed_status: str
    failure_phase: FailurePhase
    signals: list[Signal]
    evidence_refs: list[EvidenceRef]
    triage_status: TriageStatus
    root_cause: str | None
    created_at: str
    updated_at: str
    trace_schema_version: int | None = None
    runtime_identity_missing: bool = False
    context_identity_missing: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("FailureCase schema_version must be 1.")
        validate_identifier("case_id", self.case_id, "case", 24)
        _require_text("question", self.question)
        _require_text("observed_status", self.observed_status)
        _validate_timestamp(self.created_at)
        _validate_timestamp(self.updated_at)
        if not self.signals:
            raise ValueError("FailureCase requires at least one signal.")
        if not self.evidence_refs:
            raise ValueError("FailureCase requires at least one evidence reference.")
        if self.triage_status == TriageStatus.UNTRIAGED and self.root_cause is not None:
            raise ValueError("SI0 UNTRIAGED cases must not contain root_cause.")
        if self.source_type == SourceType.RUNTIME_TRACE and not self.source_identity.trace_id:
            raise ValueError("RUNTIME_TRACE cases require trace_id.")
        if self.source_type == SourceType.EVAL_RECORD:
            if not self.source_identity.eval_run_id or not self.source_identity.eval_id:
                raise ValueError("EVAL_RECORD cases require eval_run_id and eval_id.")
        if self.source_type == SourceType.USER_FEEDBACK and not self.source_identity.feedback_id:
            raise ValueError("USER_FEEDBACK cases require feedback_id.")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureCase":
        return cls(
            schema_version=int(data["schema_version"]),
            case_id=str(data["case_id"]),
            source_type=SourceType(data["source_type"]),
            source_identity=SourceIdentity(**_require_dict(data, "source_identity")),
            context_identity=ContextIdentity(**_require_dict(data, "context_identity")),
            question=str(data["question"]),
            observed_status=str(data["observed_status"]),
            failure_phase=FailurePhase(data["failure_phase"]),
            signals=[Signal(**item) for item in data.get("signals", [])],
            evidence_refs=[EvidenceRef(**item) for item in data.get("evidence_refs", [])],
            triage_status=TriageStatus(data["triage_status"]),
            root_cause=data.get("root_cause"),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            trace_schema_version=(
                int(data["trace_schema_version"])
                if data.get("trace_schema_version") is not None
                else None
            ),
            runtime_identity_missing=bool(data.get("runtime_identity_missing", False)),
            context_identity_missing=bool(data.get("context_identity_missing", False)),
        )


@dataclass(frozen=True)
class AuthorityDecision:
    schema_version: int
    authority_id: str
    feedback_id: str
    actor_id: str
    decision: AuthorityDecisionType
    context_ids: list[str]
    scopes: list[str]
    decided_by: str
    reason: str
    created_at: str
    supersedes_authority_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("AuthorityDecision schema_version must be 1.")
        validate_identifier("authority_id", self.authority_id, "authority", 32)
        validate_identifier("feedback_id", self.feedback_id, "feedback", 32)
        if self.supersedes_authority_id is not None:
            validate_identifier(
                "supersedes_authority_id",
                self.supersedes_authority_id,
                "authority",
                32,
            )
        _require_text("actor_id", self.actor_id)
        _require_text("decided_by", self.decided_by)
        _require_text("authority reason", self.reason)
        _validate_text_list("authority context_ids", self.context_ids)
        _validate_text_list("authority scopes", self.scopes)
        _validate_timestamp(self.created_at)
        if self.decision == AuthorityDecisionType.CONFIRM:
            if not self.context_ids or not self.scopes:
                raise ValueError("CONFIRM authority decisions require Context IDs and scopes.")
        if self.decision == AuthorityDecisionType.REVOKE:
            if self.supersedes_authority_id is None:
                raise ValueError("REVOKE authority decisions must supersede a confirmation.")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthorityDecision":
        return cls(
            schema_version=int(data["schema_version"]),
            authority_id=str(data["authority_id"]),
            feedback_id=str(data["feedback_id"]),
            actor_id=str(data["actor_id"]),
            decision=AuthorityDecisionType(data["decision"]),
            context_ids=list(data.get("context_ids") or []),
            scopes=list(data.get("scopes") or []),
            decided_by=str(data["decided_by"]),
            reason=str(data["reason"]),
            created_at=str(data["created_at"]),
            supersedes_authority_id=data.get("supersedes_authority_id"),
        )


@dataclass(frozen=True)
class GroupedFinding:
    schema_version: int
    finding_id: str
    context_id: str
    grouping_mode: GroupingMode
    case_ids: list[str]
    representative_trace_ids: list[str]
    root_cause_candidate: RootCauseCandidate
    confirmed_business_truth_feedback_ids: list[str]
    authority_decision_ids: list[str]
    business_scopes: list[str]
    status: FindingStatus
    created_at: str
    dismissed_by: str | None = None
    dismissed_at: str | None = None
    terminal_reason: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("GroupedFinding schema_version must be 1.")
        validate_identifier("finding_id", self.finding_id, "finding", 32)
        _require_text("finding context_id", self.context_id)
        _validate_timestamp(self.created_at)
        _validate_optional_text("dismissed_by", self.dismissed_by)
        _validate_optional_text("finding terminal_reason", self.terminal_reason)
        if self.dismissed_at is not None:
            _validate_timestamp(self.dismissed_at)
        if not self.case_ids:
            raise ValueError("GroupedFinding requires at least one case.")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("GroupedFinding case_ids must be unique.")
        for case_id in self.case_ids:
            validate_identifier("case_id", case_id, "case", 24)
        for trace_id in self.representative_trace_ids:
            validate_identifier("trace_id", trace_id, "trace", 32)
        for feedback_id in self.confirmed_business_truth_feedback_ids:
            validate_identifier("feedback_id", feedback_id, "feedback", 32)
        for authority_id in self.authority_decision_ids:
            validate_identifier("authority_id", authority_id, "authority", 32)
        _validate_text_list("business_scopes", self.business_scopes)
        if self.grouping_mode == GroupingMode.SINGLETON and len(self.case_ids) != 1:
            raise ValueError("SINGLETON findings require exactly one case.")
        if self.grouping_mode == GroupingMode.CLUSTER and len(self.case_ids) < 2:
            raise ValueError("CLUSTER findings require at least two cases.")
        if self.status == FindingStatus.DISMISSED:
            if not self.dismissed_by or not self.dismissed_at or not self.terminal_reason:
                raise ValueError("DISMISSED findings require reviewer, time, and reason.")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroupedFinding":
        return cls(
            schema_version=int(data["schema_version"]),
            finding_id=str(data["finding_id"]),
            context_id=str(data["context_id"]),
            grouping_mode=GroupingMode(data["grouping_mode"]),
            case_ids=list(data.get("case_ids") or []),
            representative_trace_ids=list(data.get("representative_trace_ids") or []),
            root_cause_candidate=RootCauseCandidate(data["root_cause_candidate"]),
            confirmed_business_truth_feedback_ids=list(
                data.get("confirmed_business_truth_feedback_ids") or []
            ),
            authority_decision_ids=list(data.get("authority_decision_ids") or []),
            business_scopes=list(data.get("business_scopes") or []),
            status=FindingStatus(data["status"]),
            created_at=str(data["created_at"]),
            dismissed_by=data.get("dismissed_by"),
            dismissed_at=data.get("dismissed_at"),
            terminal_reason=data.get("terminal_reason"),
        )


@dataclass(frozen=True)
class ResultContract:
    expected_value: str | int | float | bool | None = None
    numeric_tolerance: float | None = None

    def __post_init__(self) -> None:
        if self.expected_value is not None and not isinstance(
            self.expected_value, (str, int, float, bool)
        ):
            raise ValueError("expected_value must be a JSON scalar.")
        _validate_optional_text(
            "result expected_value",
            self.expected_value if isinstance(self.expected_value, str) else None,
        )
        if self.numeric_tolerance is not None and self.numeric_tolerance < 0:
            raise ValueError("numeric_tolerance must not be negative.")
        if self.numeric_tolerance is not None:
            if isinstance(self.expected_value, bool) or not isinstance(
                self.expected_value, (int, float)
            ):
                raise ValueError("numeric_tolerance requires a numeric expected_value.")
            if not math.isfinite(float(self.numeric_tolerance)):
                raise ValueError("numeric_tolerance must be finite.")
        if isinstance(self.expected_value, float) and not math.isfinite(self.expected_value):
            raise ValueError("expected_value must be finite.")


@dataclass(frozen=True)
class SemanticConstraints:
    required_filters: list[str] = field(default_factory=list)
    required_units: list[str] = field(default_factory=list)
    forbidden_units: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_text_list("required_filters", self.required_filters)
        _validate_text_list("required_units", self.required_units)
        _validate_text_list("forbidden_units", self.forbidden_units)
        overlap = set(self.required_units) & set(self.forbidden_units)
        if overlap:
            raise ValueError(f"Units cannot be both required and forbidden: {sorted(overlap)}")

    def is_empty(self) -> bool:
        return not (self.required_filters or self.required_units or self.forbidden_units)


@dataclass(frozen=True)
class EvalTarget:
    schema_version: int
    eval_target_id: str
    version: int
    finding_id: str
    question: str
    result_contract: ResultContract
    semantic_constraints: SemanticConstraints
    sql_hints: list[str]
    evidence_refs: list[str]
    frozen_sha256: str | None
    status: EvalTargetStatus
    created_at: str
    reviewed_by: str | None = None
    approved_at: str | None = None
    frozen_at: str | None = None
    supersedes_eval_target_id: str | None = None
    terminal_reason: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("EvalTarget schema_version must be 1.")
        validate_identifier("eval_target_id", self.eval_target_id, "evaltarget", 32)
        validate_identifier("finding_id", self.finding_id, "finding", 32)
        if self.supersedes_eval_target_id is not None:
            validate_identifier(
                "supersedes_eval_target_id",
                self.supersedes_eval_target_id,
                "evaltarget",
                32,
            )
        if self.version < 1:
            raise ValueError("EvalTarget version must be at least 1.")
        _require_text("EvalTarget question", self.question)
        _validate_text_list("sql_hints", self.sql_hints)
        _validate_text_list("evidence_refs", self.evidence_refs)
        _validate_timestamp(self.created_at)
        _validate_optional_text("reviewed_by", self.reviewed_by)
        _validate_optional_text("terminal_reason", self.terminal_reason)
        if self.approved_at is not None:
            _validate_timestamp(self.approved_at)
        if self.frozen_at is not None:
            _validate_timestamp(self.frozen_at)
        if self.frozen_sha256 is not None:
            validate_sha256("frozen_sha256", self.frozen_sha256)
        if self.status == EvalTargetStatus.FROZEN:
            if not self.frozen_sha256 or not self.frozen_at or not self.approved_at:
                raise ValueError("FROZEN EvalTargets require approval and frozen metadata.")
        if self.status in {EvalTargetStatus.SUPERSEDED, EvalTargetStatus.INVALID}:
            _require_text("terminal_reason", self.terminal_reason or "")
        if self.result_contract.expected_value is None and self.semantic_constraints.is_empty():
            raise ValueError("EvalTarget requires a result value or semantic constraint.")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalTarget":
        result_data = _require_dict(data, "result_contract")
        constraints_data = _require_dict(data, "semantic_constraints")
        return cls(
            schema_version=int(data["schema_version"]),
            eval_target_id=str(data["eval_target_id"]),
            version=int(data["version"]),
            finding_id=str(data["finding_id"]),
            question=str(data["question"]),
            result_contract=ResultContract(
                expected_value=result_data.get("expected_value"),
                numeric_tolerance=(
                    float(result_data["numeric_tolerance"])
                    if result_data.get("numeric_tolerance") is not None
                    else None
                ),
            ),
            semantic_constraints=SemanticConstraints(
                required_filters=list(constraints_data.get("required_filters") or []),
                required_units=list(constraints_data.get("required_units") or []),
                forbidden_units=list(constraints_data.get("forbidden_units") or []),
            ),
            sql_hints=list(data.get("sql_hints") or []),
            evidence_refs=list(data.get("evidence_refs") or []),
            frozen_sha256=data.get("frozen_sha256"),
            status=EvalTargetStatus(data["status"]),
            created_at=str(data["created_at"]),
            reviewed_by=data.get("reviewed_by"),
            approved_at=data.get("approved_at"),
            frozen_at=data.get("frozen_at"),
            supersedes_eval_target_id=data.get("supersedes_eval_target_id"),
            terminal_reason=data.get("terminal_reason"),
        )


@dataclass(frozen=True)
class BoundedCodexTask:
    schema_version: int
    job_id: str
    finding_id: str
    eval_target_id: str
    eval_target_sha256: str
    target_type: JobTargetType
    risk_level: str
    base_candidate_id: str
    read_only_roots: list[str]
    evidence_manifest_sha256: str
    data_identity: dict[str, str | None]
    writable_root: str
    allowed_paths: list[str]
    forbidden_paths: list[str]
    required_suites: list[str]
    target_eval_repetitions: int
    timeout_seconds: int
    max_repair_rounds: int
    database_access: bool
    network_access: bool
    status: JobStatus
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("BoundedCodexTask schema_version must be 1.")
        validate_identifier("job_id", self.job_id, "job", 32)
        validate_identifier("finding_id", self.finding_id, "finding", 32)
        validate_identifier("eval_target_id", self.eval_target_id, "evaltarget", 32)
        validate_sha256("eval_target_sha256", self.eval_target_sha256)
        validate_sha256("evidence_manifest_sha256", self.evidence_manifest_sha256)
        _require_text("risk_level", self.risk_level)
        if self.risk_level not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError("risk_level must be LOW, MEDIUM, or HIGH.")
        _require_text("base_candidate_id", self.base_candidate_id)
        _validate_text_list("read_only_roots", self.read_only_roots)
        _require_text("writable_root", self.writable_root)
        _validate_text_list("allowed_paths", self.allowed_paths)
        _validate_text_list("forbidden_paths", self.forbidden_paths)
        _validate_text_list("required_suites", self.required_suites)
        _validate_timestamp(self.created_at)
        if self.target_eval_repetitions < 1:
            raise ValueError("target_eval_repetitions must be at least 1.")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1.")
        if self.max_repair_rounds < 0:
            raise ValueError("max_repair_rounds must not be negative.")
        if self.database_access or self.network_access:
            raise ValueError("SI2 Codex tasks must not grant database or network access.")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundedCodexTask":
        return cls(
            schema_version=int(data["schema_version"]),
            job_id=str(data["job_id"]),
            finding_id=str(data["finding_id"]),
            eval_target_id=str(data["eval_target_id"]),
            eval_target_sha256=str(data["eval_target_sha256"]),
            target_type=JobTargetType(data["target_type"]),
            risk_level=str(data["risk_level"]),
            base_candidate_id=str(data["base_candidate_id"]),
            read_only_roots=list(data.get("read_only_roots") or []),
            evidence_manifest_sha256=str(data["evidence_manifest_sha256"]),
            data_identity=dict(data.get("data_identity") or {}),
            writable_root=str(data["writable_root"]),
            allowed_paths=list(data.get("allowed_paths") or []),
            forbidden_paths=list(data.get("forbidden_paths") or []),
            required_suites=list(data.get("required_suites") or []),
            target_eval_repetitions=int(data["target_eval_repetitions"]),
            timeout_seconds=int(data["timeout_seconds"]),
            max_repair_rounds=int(data["max_repair_rounds"]),
            database_access=bool(data["database_access"]),
            network_access=bool(data["network_access"]),
            status=JobStatus(data["status"]),
            created_at=str(data["created_at"]),
        )


@dataclass(frozen=True)
class IsolationReceipt:
    schema_version: int
    receipt_id: str
    job_id: str
    job_contract_sha256: str
    eval_target_sha256: str
    evidence_manifest_sha256: str
    schema_fingerprint: str
    environment_id: str
    issuer: str
    backend: str
    tool_network_policy: str
    provider_network_policy: str
    writable_root: str
    probes: dict[str, bool]
    issued_at: str
    expires_at: str
    signature: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("IsolationReceipt schema_version must be 1.")
        validate_identifier("receipt_id", self.receipt_id, "isolation", 32)
        validate_identifier("job_id", self.job_id, "job", 32)
        validate_sha256("job_contract_sha256", self.job_contract_sha256)
        validate_sha256("eval_target_sha256", self.eval_target_sha256)
        validate_sha256("evidence_manifest_sha256", self.evidence_manifest_sha256)
        validate_sha256("schema_fingerprint", self.schema_fingerprint)
        _require_text("environment_id", self.environment_id)
        _require_text("isolation issuer", self.issuer)
        _require_text("isolation backend", self.backend)
        _require_text("writable_root", self.writable_root)
        if self.tool_network_policy != "DENY":
            raise ValueError("IsolationReceipt tool_network_policy must be DENY.")
        if self.provider_network_policy != "CONTROL_PLANE_ONLY":
            raise ValueError(
                "IsolationReceipt provider_network_policy must be CONTROL_PLANE_ONLY."
            )
        if not self.probes or any(type(value) is not bool for value in self.probes.values()):
            raise ValueError("IsolationReceipt probes must be a non-empty boolean map.")
        _validate_timestamp(self.issued_at)
        _validate_timestamp(self.expires_at)
        if not re.fullmatch(r"hmac-sha256:[0-9a-f]{64}", self.signature):
            raise ValueError("IsolationReceipt signature must be an HMAC-SHA256 value.")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IsolationReceipt":
        return cls(
            schema_version=int(data["schema_version"]),
            receipt_id=str(data["receipt_id"]),
            job_id=str(data["job_id"]),
            job_contract_sha256=str(data["job_contract_sha256"]),
            eval_target_sha256=str(data["eval_target_sha256"]),
            evidence_manifest_sha256=str(data["evidence_manifest_sha256"]),
            schema_fingerprint=str(data["schema_fingerprint"]),
            environment_id=str(data["environment_id"]),
            issuer=str(data["issuer"]),
            backend=str(data["backend"]),
            tool_network_policy=str(data["tool_network_policy"]),
            provider_network_policy=str(data["provider_network_policy"]),
            writable_root=str(data["writable_root"]),
            probes=dict(data.get("probes") or {}),
            issued_at=str(data["issued_at"]),
            expires_at=str(data["expires_at"]),
            signature=str(data["signature"]),
        )


@dataclass(frozen=True)
class ImprovementJobResult:
    schema_version: int
    job_id: str
    status: CandidateResultStatus
    revision_id: str | None
    candidate_id: str | None
    candidate_project_dir: str | None
    evaluation_summary: dict[str, Any]
    error: str | None
    completed_at: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("ImprovementJobResult schema_version must be 1.")
        validate_identifier("job_id", self.job_id, "job", 32)
        _validate_optional_text("revision_id", self.revision_id)
        _validate_optional_text("candidate_id", self.candidate_id)
        _validate_optional_text("candidate_project_dir", self.candidate_project_dir)
        _validate_optional_text("job error", self.error)
        _validate_timestamp(self.completed_at)

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImprovementJobResult":
        return cls(
            schema_version=int(data["schema_version"]),
            job_id=str(data["job_id"]),
            status=CandidateResultStatus(data["status"]),
            revision_id=data.get("revision_id"),
            candidate_id=data.get("candidate_id"),
            candidate_project_dir=data.get("candidate_project_dir"),
            evaluation_summary=dict(data.get("evaluation_summary") or {}),
            error=data.get("error"),
            completed_at=str(data["completed_at"]),
        )


def new_feedback_id() -> str:
    return f"feedback_{uuid.uuid4().hex}"


def new_record_id(prefix: str) -> str:
    if prefix not in {"authority", "finding", "evaltarget", "isolation", "job"}:
        raise ValueError(f"Unsupported record prefix: {prefix!r}")
    return f"{prefix}_{uuid.uuid4().hex}"


def deterministic_case_id(canonical_source_identity: str) -> str:
    _require_text("canonical source identity", canonical_source_identity)
    digest = hashlib.sha256(canonical_source_identity.encode("utf-8")).hexdigest()
    return f"case_{digest[:24]}"


def sha256_text(value: str | None) -> str:
    digest = hashlib.sha256((value or "").encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def validate_identifier(label: str, value: str, prefix: str, hex_length: int) -> None:
    if not re.fullmatch(rf"{re.escape(prefix)}_[0-9a-f]{{{hex_length}}}", value):
        raise ValueError(f"Invalid {label}: {value!r}")


def validate_sha256(label: str, value: str) -> None:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError(f"Invalid {label}: {value!r}")


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _require_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object.")
    return value


def _require_text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be empty.")
    if len(value) > 10_000:
        raise ValueError(f"{label} exceeds 10000 characters.")
    secret_match = _EMBEDDED_SECRET_PATTERN.search(value)
    has_unredacted_secret = bool(
        secret_match and secret_match.group("value").upper() != "[REDACTED]"
    )
    if has_unredacted_secret or _URL_CREDENTIAL_PATTERN.search(value):
        raise ValueError(f"{label} contains credential-like text and cannot be stored.")


def _validate_optional_text(label: str, value: str | None) -> None:
    if value is not None:
        _require_text(label, value)


def _validate_text_list(label: str, values: list[str]) -> None:
    for value in values:
        _require_text(label, value)


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Timestamp must include a UTC offset: {value!r}")
    if parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"Timestamp must be UTC: {value!r}")


_EMBEDDED_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|authorization|access[_-]?token|"
    r"refresh[_-]?token)\s*[:=]\s*(?P<value>\S+)"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"(?i)://[^\s/:]+:[^\s/@]+@")
