from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from .models import FailureCase


def render_triage_report(cases: list[FailureCase]) -> str:
    source_counts = Counter(case.source_type.value for case in cases)
    phase_counts = Counter(case.failure_phase.value for case in cases)
    incomplete_identity = sum(
        1
        for case in cases
        if case.runtime_identity_missing or case.context_identity_missing
    )
    lines = [
        "# SI0 Failure Inbox Report",
        "",
        f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "> Root cause has not been classified. SI0 records observations only.",
        "",
        "## Summary",
        "",
        f"- Total cases: `{len(cases)}`",
        f"- Cases with incomplete runtime/Context identity: `{incomplete_identity}`",
        f"- By source: `{_format_counts(source_counts)}`",
        f"- By phase: `{_format_counts(phase_counts)}`",
        "",
        "## Cases",
        "",
    ]
    if not cases:
        lines.append("No matching cases.")
        return "\n".join(lines) + "\n"
    for case in cases:
        source_ids = [
            value
            for value in (
                case.source_identity.trace_id,
                case.source_identity.eval_run_id,
                case.source_identity.eval_id,
                case.source_identity.feedback_id,
            )
            if value
        ]
        context = case.context_identity.context_id or "unknown"
        signals = "; ".join(_bounded(signal.message) for signal in case.signals)
        evidence = ", ".join(_escape_md(ref.path) for ref in case.evidence_refs)
        lines.extend(
            [
                f"### `{case.case_id}`",
                "",
                f"- Question: {_escape_md(_bounded(case.question))}",
                f"- Source: `{case.source_type.value}` ({', '.join(source_ids)})",
                f"- Phase / status: `{case.failure_phase.value}` / `{case.observed_status}`",
                f"- Context: `{_escape_md(context)}`",
                f"- Signals: {_escape_md(signals)}",
                f"- Evidence: {evidence}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _format_counts(counts: Counter[str]) -> str:
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts)) or "none"


def _bounded(value: str, limit: int = 500) -> str:
    normalized = " ".join(value.replace("\x00", "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _escape_md(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for token in ("`", "|", "*", "_", "[", "]", "<", ">"):
        escaped = escaped.replace(token, f"\\{token}")
    return escaped
