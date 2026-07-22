from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

Status = Literal["success", "need_clarification", "failed"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_trace_id() -> str:
    return f"trace_{uuid4().hex}"


@dataclass
class NLSQLExample:
    question: str
    sql: str
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WrenContext:
    text: str
    raw: dict[str, Any] = field(default_factory=dict)
    examples: list[NLSQLExample] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "raw": self.raw,
            "examples": [item.to_dict() for item in self.examples],
        }


@dataclass
class SQLAttempt:
    step: str
    sql: str
    error_feedback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DryRunResult:
    ok: bool
    message: str = ""
    expanded_sql: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecuteResult:
    ok: bool
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DataAnswer:
    status: Status
    answer: str
    sql: str | None
    rows: list[dict[str, Any]]
    chart_spec: dict[str, Any]
    context_used: list[dict[str, Any]]
    trace_id: str
    confidence: float
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceRecord:
    trace_id: str
    question: str
    created_at: str
    user_id: str | None
    status: Status
    context_used: list[dict[str, Any]] = field(default_factory=list)
    examples_used: list[dict[str, Any]] = field(default_factory=list)
    sql_attempts: list[dict[str, Any]] = field(default_factory=list)
    dry_plan_results: list[dict[str, Any]] = field(default_factory=list)
    dry_run_results: list[dict[str, Any]] = field(default_factory=list)
    final_sql: str | None = None
    row_count: int = 0
    result_preview: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    chart_spec: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    schema_version: int = 2
    runtime_identity: dict[str, Any] = field(default_factory=dict)
    context_identity: dict[str, Any] = field(default_factory=dict)
    data_identity: dict[str, Any] = field(default_factory=dict)
    llm_identity: dict[str, Any] = field(default_factory=dict)
    eval_identity: dict[str, Any] = field(default_factory=dict)
    timings_ms: dict[str, int | None] = field(default_factory=dict)

    @classmethod
    def start(cls, question: str, user_id: str | None = None) -> "TraceRecord":
        return cls(
            trace_id=new_trace_id(),
            question=question,
            created_at=utc_now_iso(),
            user_id=user_id,
            status="failed",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
