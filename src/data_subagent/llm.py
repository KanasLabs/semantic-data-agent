from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import NLSQLExample, WrenContext


class LLMAdapter(ABC):
    @abstractmethod
    def generate_sql(
        self,
        question: str,
        context: WrenContext,
        examples: list[NLSQLExample],
        constraints: dict[str, Any] | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def repair_sql(
        self,
        question: str,
        sql: str,
        error_feedback: str,
        context: WrenContext,
        examples: list[NLSQLExample],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def summarize_result(
        self,
        question: str,
        sql: str,
        rows: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any], float]:
        raise NotImplementedError

    def summarize_result_with_context(
        self,
        question: str,
        sql: str,
        rows: list[dict[str, Any]],
        context: WrenContext,
    ) -> tuple[str, dict[str, Any], float]:
        return self.summarize_result(question, sql, rows)


class StaticLLMAdapter(LLMAdapter):
    def __init__(self, sql: str) -> None:
        self.sql = sql

    def generate_sql(
        self,
        question: str,
        context: WrenContext,
        examples: list[NLSQLExample],
        constraints: dict[str, Any] | None = None,
    ) -> str:
        return self.sql

    def repair_sql(
        self,
        question: str,
        sql: str,
        error_feedback: str,
        context: WrenContext,
        examples: list[NLSQLExample],
    ) -> str:
        return self.sql

    def summarize_result(
        self,
        question: str,
        sql: str,
        rows: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any], float]:
        return f"Query returned {len(rows)} row(s).", {}, 0.7
