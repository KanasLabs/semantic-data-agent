from __future__ import annotations

from typing import Any

from .adapters.wren_base import WrenAdapter
from .llm import LLMAdapter
from .models import DataAnswer, SQLAttempt, TraceRecord, WrenContext
from .sql_guardrail import SQLGuardrailError, validate_readonly_sql
from .trace_store import JsonlTraceStore


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
    ) -> DataAnswer:
        trace = TraceRecord.start(question=question, user_id=user_id)
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
                )

            context = self.wren.get_context(question)
            examples = self.wren.recall_examples(question, limit=3)
            context.examples = examples
            trace.context_used.append(_context_summary(context))
            trace.examples_used.extend(item.to_dict() for item in examples)

            injected_sql = _debug_initial_sql(constraints)
            if injected_sql:
                trace.warnings.append("debug_initial_sql was injected; first SQL attempt did not come from the LLM.")
                sql = injected_sql
                sql = self._record_and_validate_sql(trace, "inject_initial_sql", sql)
            else:
                sql = self.llm.generate_sql(question, context, examples, constraints)
                sql = self._record_and_validate_sql(trace, "generate_sql", sql)

            final_error: str | None = None
            for attempt_index in range(self.max_repair_attempts + 1):
                dry_plan = self.wren.dry_plan(sql)
                trace.dry_plan_results.append(dry_plan.to_dict())
                if not dry_plan.ok:
                    final_error = dry_plan.message
                else:
                    dry_run = self.wren.dry_run(sql)
                    trace.dry_run_results.append(dry_run.to_dict())
                    if dry_run.ok:
                        execute = self.wren.execute(sql, limit=self.query_limit)
                        if not execute.ok:
                            final_error = execute.error or "Wren execute failed."
                            break
                        answer, chart_spec, confidence = self.llm.summarize_result(
                            question, sql, execute.rows
                        )
                        return self._finish(
                            trace,
                            status="success",
                            answer=answer,
                            sql=sql,
                            rows=execute.rows,
                            chart_spec=chart_spec,
                            confidence=confidence,
                            error=None,
                        )
                    final_error = dry_run.message

                if attempt_index >= self.max_repair_attempts:
                    break
                repaired = self.llm.repair_sql(question, sql, final_error or "", context, examples)
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
    ) -> DataAnswer:
        trace.status = status  # type: ignore[assignment]
        trace.answer = answer
        trace.final_sql = sql
        trace.row_count = len(rows)
        trace.result_preview = rows[:20]
        trace.chart_spec = chart_spec
        trace.error = error
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
) -> DataAnswer:
    return DataSubagent(wren=wren, llm=llm, trace_store=trace_store).ask_data_question(
        question=question,
        user_id=user_id,
        conversation_context=conversation_context,
        constraints=constraints,
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
