from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CandidateEvaluationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class CandidateEvaluationReason(str, Enum):
    ACCEPTANCE_PASSED = "ACCEPTANCE_PASSED"
    ASSERTION_FAILED = "ASSERTION_FAILED"
    INFRASTRUCTURE_UNAVAILABLE = "INFRASTRUCTURE_UNAVAILABLE"
    EVAL_TARGET_INVALID = "EVAL_TARGET_INVALID"


@dataclass(frozen=True)
class CandidateEvaluation:
    schema_version: int
    status: CandidateEvaluationStatus
    reason: CandidateEvaluationReason
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("CandidateEvaluation schema_version must be 1.")
        if not self.message.strip():
            raise ValueError("CandidateEvaluation message must not be empty.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "reason": self.reason.value,
            "message": self.message,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateEvaluation":
        return cls(
            schema_version=int(data["schema_version"]),
            status=CandidateEvaluationStatus(data["status"]),
            reason=CandidateEvaluationReason(data["reason"]),
            message=str(data["message"]),
            details=dict(data.get("details") or {}),
        )


def classify_candidate_evaluation(eval_result: dict[str, Any]) -> CandidateEvaluation:
    details = {
        "smoke_ok": _nested_bool(eval_result, "smoke", "ok"),
        "regression_ok": _nested_bool(eval_result, "regression", "ok"),
    }
    if bool(eval_result.get("ok")):
        return CandidateEvaluation(
            schema_version=1,
            status=CandidateEvaluationStatus.PASS,
            reason=CandidateEvaluationReason.ACCEPTANCE_PASSED,
            message="Candidate passed all required evaluation suites.",
            details=details,
        )

    invalid_signals = _invalid_target_signals(eval_result)
    if invalid_signals:
        return CandidateEvaluation(
            schema_version=1,
            status=CandidateEvaluationStatus.BLOCKED,
            reason=CandidateEvaluationReason.EVAL_TARGET_INVALID,
            message="Candidate evaluation is blocked by an invalid or unavailable EvalTarget.",
            details={**details, "signals": invalid_signals},
        )

    infrastructure_signals = _infrastructure_signals(eval_result)
    if infrastructure_signals:
        return CandidateEvaluation(
            schema_version=1,
            status=CandidateEvaluationStatus.BLOCKED,
            reason=CandidateEvaluationReason.INFRASTRUCTURE_UNAVAILABLE,
            message="Candidate evaluation is blocked by unavailable evaluation infrastructure.",
            details={**details, "signals": infrastructure_signals},
        )

    return CandidateEvaluation(
        schema_version=1,
        status=CandidateEvaluationStatus.FAIL,
        reason=CandidateEvaluationReason.ASSERTION_FAILED,
        message="Candidate completed evaluation but failed one or more frozen assertions.",
        details=details,
    )


def _invalid_target_signals(value: Any) -> list[str]:
    signals: list[str] = []
    for item in _walk_dicts(value):
        error = item.get("error")
        if not isinstance(error, str):
            continue
        normalized = error.casefold()
        if (
            "regression suite not found" in normalized
            or "required evaluation suite not configured" in normalized
            or "evaltarget" in normalized
            and ("invalid" in normalized or "not found" in normalized)
        ):
            signals.append(error[:500])
    return _deduplicate(signals)


def _infrastructure_signals(value: Any) -> list[str]:
    signals: list[str] = []
    patterns = (
        "can't connect to server",
        "cannot connect to server",
        "connection refused",
        "connection reset",
        "network is unreachable",
        "no route to host",
        "temporarily unavailable",
        "eval timed out",
        "winerror 10061",
    )
    for item in _walk_dicts(value):
        if item.get("returncode") == 124:
            signals.append("Evaluation process timed out (returncode 124).")
        summary = item.get("summary")
        if item.get("ok") is False and item.get("returncode") not in {None, 0} and summary is None:
            signals.append(
                f"Evaluation process failed before producing a summary (returncode {item.get('returncode')})."
            )
        for key in ("error", "stderr"):
            text = item.get(key)
            if not isinstance(text, str):
                continue
            normalized = text.casefold()
            if any(pattern in normalized for pattern in patterns):
                signals.append(text[:500])
    return _deduplicate(signals)


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_dicts(nested)


def _nested_bool(value: dict[str, Any], key: str, nested_key: str) -> bool | None:
    nested = value.get(key)
    if not isinstance(nested, dict) or nested_key not in nested:
        return None
    return bool(nested.get(nested_key))


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
