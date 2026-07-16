from __future__ import annotations

import time
from typing import Any

from .adapters.wren_base import WrenAdapter
from .llm import LLMAdapter
from .models import DataAnswer, SQLAttempt, TraceRecord, WrenContext
from .sql_guardrail import SQLGuardrailError, validate_readonly_sql
from .trace_store import JsonlTraceStore
from .trace_identity import (
    canonical_json_sha256,
    context_identity,
    empty_eval_identity,
    empty_timings,
    initial_data_identity,
    llm_identity,
    runtime_identity,
)


class DataSubagent:
    def __init__(
        self,
        wren: WrenAdapter,
        llm: LLMAdapter,
        trace_store: JsonlTraceStore,
        max_repair_attempts: int = 2,
        query_limit: int = 100,
    ) -> None:
        self.wren = wren
        self.llm = llm
        self.trace_store = trace_store
        self.max_repair_attempts = max_repair_attempts
        self.query_limit = query_limit

    def ask_data_question(
        self,
        question: str,
        user_id: str | None = None,
        conversation_context: list[dict[str, Any]] | None = None,
        constraints: dict[str, Any] | None = None,
        eval_identity: dict[str, Any] | None = None,
    ) -> DataAnswer:
        started_perf = time.perf_counter()
        trace = TraceRecord.start(question=question, user_id=user_id)
        trace.runtime_identity = runtime_identity()
        trace.context_identity = context_identity(self.wren)
        trace.data_identity = initial_data_identity(trace.created_at)
        trace.llm_identity = llm_identity(self.llm)
        trace.eval_identity = dict(eval_identity or empty_eval_identity())
        trace.timings_ms = empty_timings()
        try:
            if not _is_clear_enough(question):
                return self._finish(
                    trace,
                    status="need_clarification",
                    answer="Please provide a more specific data question.",
                    sql=None,
                    rows=[],
                    chart_spec={},
                    confidence=0.0,
                    error=None,
                    started_perf=started_perf,
                )

            phase_started = time.perf_counter()
            context = self.wren.get_context(question)
            examples = self.wren.recall_examples(question, limit=3)
            _add_timing(trace, "context", phase_started)
            context.examples = examples
            trace.context_used.append(_context_summary(context))
            trace.examples_used.extend(item.to_dict() for item in examples)
            trace.data_identity["schema_fingerprint"] = canonical_json_sha256(
                {
                    "models": context.raw.get("models", []),
                    "relationships": context.raw.get("relationships", []),
                }
            )

            injected_sql = _debug_initial_sql(constraints)
            if injected_sql:
                trace.warnings.append("debug_initial_sql was injected; first SQL attempt did not come from the LLM.")
                sql = injected_sql
                sql = self._record_and_validate_sql(trace, "inject_initial_sql", sql)
            else:
                phase_started = time.perf_counter()
                sql = self.llm.generate_sql(question, context, examples, constraints)
                _add_timing(trace, "generate_sql", phase_started)
                sql = self._record_and_validate_sql(trace, "generate_sql", sql)

            final_error: str | None = None
            for attempt_index in range(self.max_repair_attempts + 1):
                phase_started = time.perf_counter()
                dry_plan = self.wren.dry_plan(sql)
                _add_timing(trace, "dry_plan", phase_started)
                trace.dry_plan_results.append(dry_plan.to_dict())
                if not dry_plan.ok:
                    final_error = dry_plan.message
                else:
                    phase_started = time.perf_counter()
                    dry_run = self.wren.dry_run(sql)
                    _add_timing(trace, "dry_run", phase_started)
                    trace.dry_run_results.append(dry_run.to_dict())
                    if dry_run.ok:
                        phase_started = time.perf_counter()
                        execute = self.wren.execute(sql, limit=self.query_limit)
                        _add_timing(trace, "execute", phase_started)
                        if not execute.ok:
                            final_error = execute.error or "Wren execute failed."
                            break
                        phase_started = time.perf_counter()
                        answer, chart_spec, confidence = self.llm.summarize_result(
                            question, sql, execute.rows
                        )
                        _add_timing(trace, "summarize", phase_started)
                        return self._finish(
                            trace,
                            status="success",
                            answer=answer,
                            sql=sql,
                            rows=execute.rows,
                            chart_spec=chart_spec,
                            confidence=confidence,
                            error=None,
                            started_perf=started_perf,
                        )
                    final_error = dry_run.message

                if attempt_index >= self.max_repair_attempts:
                    break
                phase_started = time.perf_counter()
                repaired = self.llm.repair_sql(question, sql, final_error or "", context, examples)
                _add_timing(trace, "generate_sql", phase_started)
                sql = self._record_and_validate_sql(trace, "repair_sql", repaired, final_error)

            return self._finish(
                trace,
                status="failed",
                answer="I could not produce a valid SQL query for this question.",
                sql=sql,
                rows=[],
                chart_spec={},
                confidence=0.0,
                error=final_error,
                started_perf=started_perf,
            )
        except Exception as exc:
            return self._finish(
                trace,
                status="failed",
                answer="The Data Subagent failed before completing the query.",
                sql=trace.final_sql,
                rows=[],
                chart_spec={},
                confidence=0.0,
                error=str(exc),
                started_perf=started_perf,
            )

    def _record_and_validate_sql(
        self,
        trace: TraceRecord,
        step: str,
        sql: str,
        error_feedback: str | None = None,
    ) -> str:
        validated = validate_readonly_sql(sql)
        trace.sql_attempts.append(SQLAttempt(step=step, sql=validated, error_feedback=error_feedback).to_dict())
        trace.final_sql = validated
        return validated

    def _finish(
        self,
        trace: TraceRecord,
        status: str,
        answer: str,
        sql: str | None,
        rows: list[dict[str, Any]],
        chart_spec: dict[str, Any],
        confidence: float,
        error: str | None,
        started_perf: float,
    ) -> DataAnswer:
        trace.status = status  # type: ignore[assignment]
        trace.answer = answer
        trace.final_sql = sql
        trace.row_count = len(rows)
        trace.result_preview = rows[:20]
        trace.chart_spec = chart_spec
        trace.error = error
        trace.data_identity["result_sha256"] = canonical_json_sha256(rows)
        trace.timings_ms["total"] = _elapsed_ms(started_perf)
        self.trace_store.append(trace)
        return DataAnswer(
            status=status,  # type: ignore[arg-type]
            answer=answer,
            sql=sql,
            rows=rows,
            chart_spec=chart_spec,
            context_used=trace.context_used,
            trace_id=trace.trace_id,
            confidence=confidence,
            warnings=trace.warnings,
            error=error,
        )


def ask_data_question(
    question: str,
    wren: WrenAdapter,
    llm: LLMAdapter,
    trace_store: JsonlTraceStore,
    user_id: str | None = None,
    conversation_context: list[dict[str, Any]] | None = None,
    constraints: dict[str, Any] | None = None,
    eval_identity: dict[str, Any] | None = None,
) -> DataAnswer:
    return DataSubagent(wren=wren, llm=llm, trace_store=trace_store).ask_data_question(
        question=question,
        user_id=user_id,
        conversation_context=conversation_context,
        constraints=constraints,
        eval_identity=eval_identity,
    )


def _is_clear_enough(question: str) -> bool:
    stripped = question.strip()
    return len(stripped) >= 4 and any(char.isalpha() for char in stripped)


def _debug_initial_sql(constraints: dict[str, Any] | None) -> str | None:
    if not constraints:
        return None
    value = constraints.get("debug_initial_sql")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _context_summary(context: WrenContext) -> dict[str, Any]:
    return {
        "source": "wren",
        "models": [model.get("name") for model in context.raw.get("models", []) if isinstance(model, dict)],
        "relationships": [
            item.get("name")
            for item in context.raw.get("relationships", [])
            if isinstance(item, dict)
        ],
    }


def _add_timing(trace: TraceRecord, phase: str, started_perf: float) -> None:
    elapsed = _elapsed_ms(started_perf)
    current = trace.timings_ms.get(phase)
    trace.timings_ms[phase] = elapsed if current is None else current + elapsed


def _elapsed_ms(started_perf: float) -> int:
    return max(0, int((time.perf_counter() - started_perf) * 1000))
