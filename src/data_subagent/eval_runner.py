from __future__ import annotations

import json
import time
from decimal import Decimal, InvalidOperation
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent import DataSubagent
from .sql_guardrail import SQLGuardrailError, validate_readonly_sql


@dataclass
class EvalCase:
    eval_id: str
    question: str
    dataset: str = "unknown"
    db_id: str = "unknown"
    evidence: str = ""
    gold_sql: str = ""
    expected_status: str = "success"
    expected_sql_contains: list[str] = field(default_factory=list)
    expected_sql_not_contains: list[str] = field(default_factory=list)
    expected_row_count: int | None = None
    expected_first_row_contains: dict[str, Any] = field(default_factory=dict)
    expected_any_row_contains: list[dict[str, Any]] = field(default_factory=list)
    expected_any_values: list[Any] = field(default_factory=list)
    expected_answer_contains: list[str] = field(default_factory=list)
    expected_answer_not_contains: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalCase":
        required = ["eval_id", "question"]
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ValueError(f"Eval case missing required field(s): {', '.join(missing)}")
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass
class EvalRunRecord:
    eval_id: str
    dataset: str
    db_id: str
    question: str
    status: str
    trace_id: str | None
    final_sql: str | None
    gold_sql: str
    gold_sql_check: dict[str, Any]
    answer: str
    row_count: int
    review_status: str
    started_at: str
    finished_at: str
    duration_ms: int
    metrics: dict[str, bool | int | None]
    failure_reasons: list[str]
    warnings: list[str]
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalRunSummary:
    suite_name: str
    run_id: str
    started_at: str
    finished_at: str
    duration_ms: int
    total: int
    passed: int
    failed: int
    run_path: Path
    report_path: Path
    records: list[EvalRunRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "run_path": str(self.run_path),
            "report_path": str(self.report_path),
            "records": [record.to_dict() for record in self.records],
        }


def load_eval_cases(path: Path, limit: int | None = None) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                loaded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(loaded, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            cases.append(EvalCase.from_dict(loaded))
            if limit and len(cases) >= limit:
                break
    return cases


def run_eval_suite(
    agent: DataSubagent,
    cases_path: Path,
    trace_path: Path,
    output_dir: Path,
    report_dir: Path,
    suite_name: str | None = None,
    limit: int | None = None,
) -> EvalRunSummary:
    cases = load_eval_cases(cases_path, limit=limit)
    resolved_suite_name = suite_name or cases_path.stem
    run_id = _new_run_id(resolved_suite_name)
    started_at = _utc_now_iso()
    started_perf = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    run_path = output_dir / f"{run_id}.jsonl"
    report_path = report_dir / f"{run_id}.md"

    records: list[EvalRunRecord] = []
    with run_path.open("w", encoding="utf-8") as run_file:
        for case in cases:
            record = _run_one_case(agent, case, trace_path)
            records.append(record)
            run_file.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            run_file.flush()

    passed = sum(1 for record in records if record.status == "pass")
    finished_at = _utc_now_iso()
    duration_ms = _elapsed_ms(started_perf)
    summary = EvalRunSummary(
        suite_name=resolved_suite_name,
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        total=len(records),
        passed=passed,
        failed=len(records) - passed,
        run_path=run_path,
        report_path=report_path,
        records=records,
    )
    report_path.write_text(_render_report(summary), encoding="utf-8")
    return summary


def _run_one_case(agent: DataSubagent, case: EvalCase, trace_path: Path) -> EvalRunRecord:
    started_at = _utc_now_iso()
    started_perf = time.perf_counter()
    answer = agent.ask_data_question(
        question=_question_with_evidence(case),
        constraints=case.constraints or None,
    )
    finished_at = _utc_now_iso()
    duration_ms = _elapsed_ms(started_perf)
    trace = _load_trace_by_id(trace_path, answer.trace_id)
    metrics, failure_reasons = _evaluate_answer(case, answer.to_dict(), trace)
    status = "pass" if not failure_reasons else "fail"
    gold_sql_check = _check_gold_sql(agent, case.gold_sql, answer.rows)
    review_status = _review_status(case, status, gold_sql_check)
    return EvalRunRecord(
        eval_id=case.eval_id,
        dataset=case.dataset,
        db_id=case.db_id,
        question=case.question,
        status=status,
        trace_id=answer.trace_id,
        final_sql=answer.sql,
        gold_sql=case.gold_sql,
        gold_sql_check=gold_sql_check,
        answer=answer.answer,
        row_count=len(answer.rows),
        review_status=review_status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        metrics=metrics,
        failure_reasons=failure_reasons,
        warnings=answer.warnings,
        error=answer.error,
    )


def _question_with_evidence(case: EvalCase) -> str:
    if not case.evidence:
        return case.question
    return f"{case.question}\n\nEvidence:\n{case.evidence}"


def _review_status(case: EvalCase, status: str, gold_sql_check: dict[str, Any]) -> str:
    if gold_sql_check and gold_sql_check.get("needs_triage"):
        return "needs_triage"
    if status == "pass":
        return "auto_pass"
    if case.gold_sql:
        return "needs_triage"
    return "auto_fail"


def _check_gold_sql(
    agent: DataSubagent,
    gold_sql: str,
    answer_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not gold_sql.strip():
        return {}
    check: dict[str, Any] = {
        "present": True,
        "guardrail_ok": False,
        "dry_run_ok": False,
        "execute_ok": False,
        "gold_row_count": None,
        "execution_match": None,
        "needs_triage": False,
        "error": None,
    }
    try:
        validated = validate_readonly_sql(gold_sql)
        check["guardrail_ok"] = True
    except SQLGuardrailError as exc:
        check["error"] = str(exc)
        check["needs_triage"] = True
        return check

    dry_run = agent.wren.dry_run(validated)
    check["dry_run_ok"] = dry_run.ok
    if not dry_run.ok:
        check["error"] = dry_run.message
        check["needs_triage"] = True
        return check

    executed = agent.wren.execute(validated, limit=agent.query_limit)
    check["execute_ok"] = executed.ok
    if not executed.ok:
        check["error"] = executed.error or "Gold SQL execution failed."
        check["needs_triage"] = True
        return check

    check["gold_row_count"] = len(executed.rows)
    execution_match = _rows_equivalent(answer_rows, executed.rows)
    check["execution_match"] = execution_match
    check["needs_triage"] = not execution_match
    return check


def _evaluate_answer(
    case: EvalCase,
    answer: dict[str, Any],
    trace: dict[str, Any] | None,
) -> tuple[dict[str, bool | int | None], list[str]]:
    rows = answer.get("rows") if isinstance(answer.get("rows"), list) else []
    sql = str(answer.get("sql") or "")
    normalized_sql = sql.lower()
    answer_text = str(answer.get("answer") or "")
    normalized_answer = answer_text.lower()
    failure_reasons: list[str] = []

    status_match = answer.get("status") == case.expected_status
    if not status_match:
        failure_reasons.append(
            f"status expected {case.expected_status!r}, got {answer.get('status')!r}"
        )

    sql_contains_match = all(item.lower() in normalized_sql for item in case.expected_sql_contains)
    if not sql_contains_match:
        missing = [item for item in case.expected_sql_contains if item.lower() not in normalized_sql]
        failure_reasons.append(f"SQL missing expected fragment(s): {missing}")

    sql_not_contains_match = all(
        item.lower() not in normalized_sql for item in case.expected_sql_not_contains
    )
    if not sql_not_contains_match:
        present = [item for item in case.expected_sql_not_contains if item.lower() in normalized_sql]
        failure_reasons.append(f"SQL contains forbidden fragment(s): {present}")

    row_count_match = True
    if case.expected_row_count is not None:
        row_count_match = len(rows) == case.expected_row_count
        if not row_count_match:
            failure_reasons.append(
                f"row_count expected {case.expected_row_count}, got {len(rows)}"
            )

    first_row_match = True
    if case.expected_first_row_contains:
        first_row_match = bool(rows) and _row_contains(rows[0], case.expected_first_row_contains)
        if not first_row_match:
            failure_reasons.append(
                f"first row did not contain {case.expected_first_row_contains}"
            )

    any_row_match = True
    for expected in case.expected_any_row_contains:
        if not any(_row_contains(row, expected) for row in rows if isinstance(row, dict)):
            any_row_match = False
            failure_reasons.append(f"no row contained {expected}")

    any_value_match = True
    flattened_values = [_normalize_value(value) for row in rows if isinstance(row, dict) for value in row.values()]
    for expected_value in case.expected_any_values:
        if _normalize_value(expected_value) not in flattened_values:
            any_value_match = False
            failure_reasons.append(f"value not found in result rows: {expected_value!r}")

    answer_contains_match = all(
        item.lower() in normalized_answer for item in case.expected_answer_contains
    )
    if not answer_contains_match:
        missing = [
            item
            for item in case.expected_answer_contains
            if item.lower() not in normalized_answer
        ]
        failure_reasons.append(f"answer missing expected fragment(s): {missing}")

    answer_not_contains_match = all(
        item.lower() not in normalized_answer
        for item in case.expected_answer_not_contains
    )
    if not answer_not_contains_match:
        present = [
            item
            for item in case.expected_answer_not_contains
            if item.lower() in normalized_answer
        ]
        failure_reasons.append(f"answer contains forbidden fragment(s): {present}")

    repair_count = None
    dry_run_ok = None
    if trace:
        attempts = trace.get("sql_attempts") if isinstance(trace.get("sql_attempts"), list) else []
        repair_count = sum(1 for item in attempts if isinstance(item, dict) and item.get("step") == "repair_sql")
        dry_runs = trace.get("dry_run_results") if isinstance(trace.get("dry_run_results"), list) else []
        dry_run_ok = any(bool(item.get("ok")) for item in dry_runs if isinstance(item, dict))

    metrics: dict[str, bool | int | None] = {
        "status_match": status_match,
        "sql_contains_match": sql_contains_match,
        "sql_not_contains_match": sql_not_contains_match,
        "row_count_match": row_count_match,
        "first_row_match": first_row_match,
        "any_row_match": any_row_match,
        "any_value_match": any_value_match,
        "answer_contains_match": answer_contains_match,
        "answer_not_contains_match": answer_not_contains_match,
        "dry_run_ok": dry_run_ok,
        "repair_count": repair_count,
    }
    return metrics, failure_reasons


def _rows_equivalent(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    return _normalize_rows(left) == _normalize_rows(right)


def _normalize_rows(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            tuple(
                sorted(
                    (_normalize_value(value) for value in row.values()),
                    key=_stable_sort_key,
                )
            )
        )
    return sorted(normalized, key=_stable_sort_key)


def _row_contains(row: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if key not in row or _normalize_value(row[key]) != _normalize_value(value):
            return False
    return True


def _normalize_value(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, float):
        return float(f"{value:.8g}")
    if isinstance(value, str):
        stripped = value.strip()
        try:
            numeric = Decimal(stripped)
        except InvalidOperation:
            return stripped
        if not numeric.is_finite():
            return stripped
        if numeric == numeric.to_integral_value():
            return int(numeric)
        return float(f"{float(numeric):.8g}")
    return value


def _stable_sort_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _load_trace_by_id(trace_path: Path, trace_id: str | None) -> dict[str, Any] | None:
    if not trace_id or not trace_path.exists():
        return None
    with trace_path.open("r", encoding="utf-8") as file:
        for raw_line in reversed(file.read().splitlines()):
            if trace_id not in raw_line:
                continue
            try:
                loaded = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict) and loaded.get("trace_id") == trace_id:
                return loaded
    return None


def _render_report(summary: EvalRunSummary) -> str:
    lines = [
        f"# Eval Report: {summary.suite_name}",
        "",
        f"- Run ID: `{summary.run_id}`",
        f"- Total: {summary.total}",
        f"- Passed: {summary.passed}",
        f"- Failed: {summary.failed}",
        f"- Started At: `{summary.started_at}`",
        f"- Finished At: `{summary.finished_at}`",
        f"- Duration: {summary.duration_ms} ms",
        f"- Run JSONL: `{summary.run_path}`",
        "",
        "## Cases",
        "",
        "| Eval ID | Status | Duration | Trace ID | SQL | Failure Reasons |",
        "|---|---|---:|---|---|---|",
    ]
    for record in summary.records:
        reasons = "<br>".join(_escape_md(item) for item in record.failure_reasons) or "-"
        sql = _escape_md((record.final_sql or "").replace("\n", " "))
        status = (
            f"{record.status} / {record.review_status}"
            if record.review_status != "auto_pass"
            else record.status
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_md(record.eval_id),
                    status,
                    f"{record.duration_ms} ms",
                    f"`{record.trace_id}`" if record.trace_id else "-",
                    f"`{sql}`" if sql else "-",
                    reasons,
                ]
            )
            + " |"
        )
    lines.extend(["", "## Review Details", ""])
    review_records = [
        record
        for record in summary.records
        if record.status != "pass" or record.review_status == "needs_triage"
    ]
    if not review_records:
        lines.append("No failures or triage items.")
    for record in review_records:
        lines.extend(
            [
                f"### {record.eval_id}",
                "",
                f"- Question: {record.question}",
                f"- Trace: `{record.trace_id}`",
                f"- Error: {record.error or '-'}",
                f"- Review Status: `{record.review_status}`",
                f"- Gold SQL: `{_escape_md(record.gold_sql.replace(chr(10), ' '))}`"
                if record.gold_sql
                else "- Gold SQL: -",
                f"- Gold SQL Check: `{_escape_md(json.dumps(record.gold_sql_check, ensure_ascii=False))}`"
                if record.gold_sql_check
                else "- Gold SQL Check: -",
                "- Reasons:",
            ]
        )
        lines.extend(f"  - {reason}" for reason in record.failure_reasons)
        lines.append("")
    return "\n".join(lines) + "\n"


def _escape_md(text: str) -> str:
    return text.replace("|", "\\|")


def _new_run_id(suite_name: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_suite = "".join(char if char.isalnum() or char in "-_" else "-" for char in suite_name)
    return f"{timestamp}-{safe_suite}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(started_perf: float) -> int:
    return int((time.perf_counter() - started_perf) * 1000)
