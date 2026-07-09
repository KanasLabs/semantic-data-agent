from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .llm import LLMAdapter
from .models import NLSQLExample, WrenContext


class LLMResponseParseError(RuntimeError):
    pass


class DeepSeekTransientError(RuntimeError):
    pass


class DeepSeekLLMAdapter(LLMAdapter):
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: int = 90,
        max_retries: int = 2,
        retry_initial_delay_seconds: float = 1.0,
        retry_backoff_factor: float = 2.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.retry_initial_delay_seconds = max(0.0, retry_initial_delay_seconds)
        self.retry_backoff_factor = max(1.0, retry_backoff_factor)

    def generate_sql(
        self,
        question: str,
        context: WrenContext,
        examples: list[NLSQLExample],
        constraints: dict[str, Any] | None = None,
    ) -> str:
        payload = self._json_chat(
            system=_sql_system_prompt(),
            user=_sql_user_prompt(question, context, examples, constraints),
            max_tokens=1200,
        )
        return _require_sql(payload)

    def repair_sql(
        self,
        question: str,
        sql: str,
        error_feedback: str,
        context: WrenContext,
        examples: list[NLSQLExample],
    ) -> str:
        user = (
            _sql_user_prompt(question, context, examples, None)
            + "\n\nThe previous SQL failed.\n"
            + f"Previous SQL:\n```sql\n{sql}\n```\n\n"
            + f"Error feedback:\n{error_feedback}\n\n"
            + "Return repaired SQL as JSON."
        )
        payload = self._json_chat(system=_sql_system_prompt(), user=user, max_tokens=1200)
        return _require_sql(payload)

    def summarize_result(
        self,
        question: str,
        sql: str,
        rows: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any], float]:
        row_preview = rows[:20]
        try:
            payload = self._json_chat(
                system=(
                    "You summarize SQL query results for a business user. "
                    "Return JSON with keys answer, chart_spec, confidence. "
                    "Keep chart_spec compact and use an empty object if no chart is useful."
                ),
                user=(
                    f"Question: {question}\nSQL:\n{sql}\n"
                    f"Rows JSON:\n{json.dumps(row_preview, ensure_ascii=False)}"
                ),
                max_tokens=900,
            )
        except LLMResponseParseError:
            return _fallback_summary(rows), {}, 0.5
        answer = str(payload.get("answer") or f"Query returned {len(rows)} row(s).")
        chart_spec = payload.get("chart_spec") if isinstance(payload.get("chart_spec"), dict) else {}
        confidence = _parse_confidence(payload.get("confidence"))
        return answer, chart_spec, confidence

    def _json_chat(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        for attempt_index in range(self.max_retries + 1):
            try:
                return self._json_chat_once(system=system, user=user, max_tokens=max_tokens)
            except (DeepSeekTransientError, LLMResponseParseError):
                if attempt_index >= self.max_retries:
                    raise
                self._sleep_before_retry(attempt_index)
        raise RuntimeError("DeepSeek retry loop exited unexpectedly.")

    def _json_chat_once(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504}:
                raise DeepSeekTransientError(
                    f"DeepSeek API transient error {exc.code}: {details}"
                ) from exc
            raise RuntimeError(f"DeepSeek API error {exc.code}: {details}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DeepSeekTransientError(f"DeepSeek API request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DeepSeekTransientError("DeepSeek API returned malformed JSON.") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseParseError(f"Unexpected DeepSeek response shape: {body!r}") from exc
        try:
            return _parse_json_content(content)
        except (json.JSONDecodeError, RuntimeError) as exc:
            raise LLMResponseParseError(f"Failed to parse LLM JSON response: {content!r}") from exc

    def _sleep_before_retry(self, attempt_index: int) -> None:
        if self.retry_initial_delay_seconds <= 0:
            return
        delay = self.retry_initial_delay_seconds * (self.retry_backoff_factor ** attempt_index)
        time.sleep(delay)


def _sql_system_prompt() -> str:
    return (
        "You are a text-to-SQL component inside a controlled Data Subagent. "
        "Generate Wren MDL SQL only. Use the semantic context and confirmed examples. "
        "Return JSON with one key: sql. The SQL must be read-only SELECT/WITH, "
        "must not mutate data, and should prefer model-layer tables."
    )


def _sql_user_prompt(
    question: str,
    context: WrenContext,
    examples: list[NLSQLExample],
    constraints: dict[str, Any] | None,
) -> str:
    examples_text = "\n".join(
        f"- NL: {item.question}\n  SQL: {item.sql}" for item in examples
    )
    return (
        f"Question:\n{question}\n\n"
        f"Constraints:\n{json.dumps(constraints or {}, ensure_ascii=False)}\n\n"
        f"Wren semantic context:\n{context.text}\n\n"
        f"Confirmed NL-SQL examples:\n{examples_text or '(none)'}\n\n"
        "Return only JSON like {\"sql\": \"select ...\"}."
    )


def _require_sql(payload: dict[str, Any]) -> str:
    sql = payload.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise RuntimeError(f"LLM response did not contain a non-empty sql field: {payload}")
    return sql.strip()


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        loaded = json.loads(match.group(0))
    if not isinstance(loaded, dict):
        raise RuntimeError(f"Expected JSON object from LLM, got: {loaded!r}")
    return loaded


def _parse_confidence(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        normalized = value.strip().lower()
        mapped = {
            "high": 0.9,
            "medium": 0.7,
            "low": 0.4,
        }
        if normalized in mapped:
            return mapped[normalized]
        try:
            return max(0.0, min(1.0, float(normalized)))
        except ValueError:
            return 0.75
    return 0.75


def _fallback_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Query returned 0 rows."
    if len(rows) == 1 and isinstance(rows[0], dict):
        values = list(rows[0].values())
        if len(values) == 1:
            return str(values[0])
    return f"Query returned {len(rows)} row(s)."
