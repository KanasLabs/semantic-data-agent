from __future__ import annotations

from data_subagent.adapters.wren_base import WrenAdapter
from data_subagent.models import DryRunResult, ExecuteResult, NLSQLExample, WrenContext


class FakeWrenAdapter(WrenAdapter):
    def __init__(self) -> None:
        self.rows = [{"order_count": 99}]

    def get_context(self, question: str) -> WrenContext:
        return WrenContext(
            text="Model orders(order_id, customer_id, order_date, status, amount).",
            raw={"models": [{"name": "orders"}]},
        )

    def recall_examples(self, question: str, limit: int = 3) -> list[NLSQLExample]:
        return [NLSQLExample(question="How many orders are there?", sql="select count(*) as order_count from orders")]

    def dry_plan(self, sql: str) -> DryRunResult:
        return DryRunResult(ok=True, message="OK", expanded_sql=sql)

    def dry_run(self, sql: str) -> DryRunResult:
        if "bad_column" in sql:
            return DryRunResult(ok=False, message="Binder Error: column bad_column not found")
        return DryRunResult(ok=True, message="OK")

    def execute(self, sql: str, limit: int = 100) -> ExecuteResult:
        return ExecuteResult(ok=True, rows=self.rows[:limit])
