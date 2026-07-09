import json
import tempfile
import unittest
from pathlib import Path

from data_subagent.adapters.fake_wren import FakeWrenAdapter
from data_subagent.agent import DataSubagent
from data_subagent.eval_runner import _rows_equivalent, load_eval_cases, run_eval_suite
from data_subagent.llm import StaticLLMAdapter
from data_subagent.models import ExecuteResult
from data_subagent.trace_store import JsonlTraceStore


class EvalRunnerTest(unittest.TestCase):
    def test_load_eval_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            suite = Path(tmp) / "suite.jsonl"
            suite.write_text(
                json.dumps(
                    {
                        "eval_id": "case_1",
                        "question": "How many orders are there?",
                        "expected_sql_contains": ["count"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            cases = load_eval_cases(suite)
            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0].eval_id, "case_1")
            self.assertEqual(cases[0].expected_sql_contains, ["count"])

    def test_run_eval_suite_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite = root / "suite.jsonl"
            suite.write_text(
                json.dumps(
                    {
                        "eval_id": "case_1",
                        "dataset": "fake",
                        "db_id": "fake",
                        "question": "How many orders are there?",
                        "expected_sql_contains": ["count", "orders"],
                        "expected_row_count": 1,
                        "expected_any_row_contains": [{"order_count": 99}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            trace_path = root / "trace.jsonl"
            agent = DataSubagent(
                wren=FakeWrenAdapter(),
                llm=StaticLLMAdapter("select count(*) as order_count from orders"),
                trace_store=JsonlTraceStore(trace_path),
            )
            summary = run_eval_suite(
                agent=agent,
                cases_path=suite,
                trace_path=trace_path,
                output_dir=root / "runs",
                report_dir=root / "reports",
                suite_name="fake_suite",
            )
            self.assertEqual(summary.total, 1)
            self.assertEqual(summary.passed, 1)
            self.assertIsInstance(summary.duration_ms, int)
            self.assertGreaterEqual(summary.duration_ms, 0)
            self.assertTrue(summary.started_at)
            self.assertTrue(summary.finished_at)
            self.assertIsInstance(summary.records[0].duration_ms, int)
            self.assertTrue(summary.run_path.exists())
            self.assertTrue(summary.report_path.exists())

    def test_gold_sql_failure_requires_triage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite = root / "suite.jsonl"
            suite.write_text(
                json.dumps(
                    {
                        "eval_id": "bird_case_1",
                        "dataset": "bird_mini_dev",
                        "db_id": "business_db",
                        "question": "How many customers are there?",
                        "gold_sql": "select count(*) from customers",
                        "expected_sql_contains": ["customers"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            trace_path = root / "trace.jsonl"
            agent = DataSubagent(
                wren=FakeWrenAdapter(),
                llm=StaticLLMAdapter("select count(*) as order_count from orders"),
                trace_store=JsonlTraceStore(trace_path),
            )
            summary = run_eval_suite(
                agent=agent,
                cases_path=suite,
                trace_path=trace_path,
                output_dir=root / "runs",
                report_dir=root / "reports",
                suite_name="bird_subset",
            )

            self.assertEqual(summary.failed, 1)
            self.assertEqual(summary.records[0].gold_sql, "select count(*) from customers")
            self.assertEqual(summary.records[0].review_status, "needs_triage")
            self.assertIn("needs_triage", summary.report_path.read_text(encoding="utf-8"))

    def test_gold_sql_execution_mismatch_requires_triage_even_when_auto_checks_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite = root / "suite.jsonl"
            suite.write_text(
                json.dumps(
                    {
                        "eval_id": "bird_case_2",
                        "dataset": "bird_mini_dev",
                        "db_id": "business_db",
                        "question": "How many orders are there?",
                        "gold_sql": "select count(*) as order_count from orders",
                        "expected_sql_contains": ["count", "orders"],
                        "expected_row_count": 1,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            trace_path = root / "trace.jsonl"
            agent = DataSubagent(
                wren=GoldMismatchWrenAdapter(),
                llm=StaticLLMAdapter("select count(*) as order_count from orders"),
                trace_store=JsonlTraceStore(trace_path),
            )
            summary = run_eval_suite(
                agent=agent,
                cases_path=suite,
                trace_path=trace_path,
                output_dir=root / "runs",
                report_dir=root / "reports",
                suite_name="bird_subset",
            )

            self.assertEqual(summary.passed, 1)
            self.assertEqual(summary.records[0].review_status, "needs_triage")
            self.assertFalse(summary.records[0].gold_sql_check["execution_match"])
            self.assertIn("Gold SQL Check", summary.report_path.read_text(encoding="utf-8"))

    def test_rows_equivalent_handles_mixed_value_types(self):
        self.assertTrue(
            _rows_equivalent(
                [{"label": "EUR/CZK", "ratio": 1.5}],
                [{"ratio": 1.5, "label": "EUR/CZK"}],
            )
        )


class GoldMismatchWrenAdapter(FakeWrenAdapter):
    def __init__(self) -> None:
        super().__init__()
        self._execute_count = 0

    def execute(self, sql: str, limit: int = 100) -> ExecuteResult:
        self._execute_count += 1
        if self._execute_count == 1:
            return ExecuteResult(ok=True, rows=[{"order_count": 99}])
        return ExecuteResult(ok=True, rows=[{"order_count": 100}])


if __name__ == "__main__":
    unittest.main()
