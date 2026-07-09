from __future__ import annotations

from abc import ABC, abstractmethod

from data_subagent.models import DryRunResult, ExecuteResult, NLSQLExample, WrenContext


class WrenAdapter(ABC):
    @abstractmethod
    def get_context(self, question: str) -> WrenContext:
        raise NotImplementedError

    @abstractmethod
    def recall_examples(self, question: str, limit: int = 3) -> list[NLSQLExample]:
        raise NotImplementedError

    @abstractmethod
    def dry_plan(self, sql: str) -> DryRunResult:
        raise NotImplementedError

    @abstractmethod
    def dry_run(self, sql: str) -> DryRunResult:
        raise NotImplementedError

    @abstractmethod
    def execute(self, sql: str, limit: int = 100) -> ExecuteResult:
        raise NotImplementedError
