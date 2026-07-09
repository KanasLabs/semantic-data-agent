import tempfile
import unittest
from pathlib import Path

from data_subagent.adapters.fake_wren import FakeWrenAdapter
from data_subagent.agent import DataSubagent
from data_subagent.llm import LLMAdapter, StaticLLMAdapter
from data_subagent.trace_store import JsonlTraceStore


class AgentLoopTest(unittest.TestCase):
    def test_successful_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = DataSubagent(
                wren=FakeWrenAdapter(),
                llm=StaticLLMAdapter("select count(*) as order_count from orders"),
                trace_store=JsonlTraceStore(Path(tmp) / "trace.jsonl"),
            )
            answer = agent.ask_data_question("How many orders are there?")
            self.assertEqual(answer.status, "success")
            self.assertEqual(answer.rows, [{"order_count": 99}])
            self.assertTrue(answer.trace_id.startswith("trace_"))

    def test_need_clarification(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = DataSubagent(
                wren=FakeWrenAdapter(),
                llm=StaticLLMAdapter("select 1"),
                trace_store=JsonlTraceStore(Path(tmp) / "trace.jsonl"),
            )
            answer = agent.ask_data_question("?")
            self.assertEqual(answer.status, "need_clarification")

    def test_repairs_failed_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = DataSubagent(
                wren=FakeWrenAdapter(),
                llm=RepairingLLMAdapter(),
                trace_store=JsonlTraceStore(Path(tmp) / "trace.jsonl"),
            )
            answer = agent.ask_data_question("How many orders are there?")
            self.assertEqual(answer.status, "success")
            self.assertEqual(answer.sql, "select count(*) as order_count from orders")

    def test_repairs_injected_initial_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "trace.jsonl"
            agent = DataSubagent(
                wren=FakeWrenAdapter(),
                llm=RepairingLLMAdapter(),
                trace_store=JsonlTraceStore(trace_path),
            )
            answer = agent.ask_data_question(
                "How many orders are there?",
                constraints={"debug_initial_sql": "select bad_column from orders"},
            )
            self.assertEqual(answer.status, "success")
            self.assertEqual(answer.sql, "select count(*) as order_count from orders")
            self.assertIn("debug_initial_sql", answer.warnings[0])

            trace_text = trace_path.read_text(encoding="utf-8")
            self.assertIn('"step": "inject_initial_sql"', trace_text)
            self.assertIn('"step": "repair_sql"', trace_text)


class RepairingLLMAdapter(LLMAdapter):
    def generate_sql(self, question, context, examples, constraints=None):
        return "select bad_column from orders"

    def repair_sql(self, question, sql, error_feedback, context, examples):
        return "select count(*) as order_count from orders"

    def summarize_result(self, question, sql, rows):
        return "There are 99 orders.", {}, 0.9


if __name__ == "__main__":
    unittest.main()
