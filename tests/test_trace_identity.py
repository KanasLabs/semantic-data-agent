from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_subagent.adapters.fake_wren import FakeWrenAdapter
from data_subagent.agent import DataSubagent
from data_subagent.llm import StaticLLMAdapter
from data_subagent.trace_identity import fingerprint_wren_project
from data_subagent.trace_store import JsonlTraceStore


class TraceIdentityTest(unittest.TestCase):
    def test_fingerprint_uses_semantic_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            project = Path(temporary_dir)
            model = project / "models" / "orders" / "metadata.yml"
            model.parent.mkdir(parents=True)
            model.write_text("name: orders\n", encoding="utf-8")
            ignored = project / "onboarding" / "prompt.md"
            ignored.parent.mkdir(parents=True)
            ignored.write_text("first", encoding="utf-8")
            first = fingerprint_wren_project(project)
            ignored.write_text("second", encoding="utf-8")
            self.assertEqual(first, fingerprint_wren_project(project))
            model.write_text("name: changed_orders\n", encoding="utf-8")
            self.assertNotEqual(first, fingerprint_wren_project(project))

    def test_real_agent_trace_contains_v2_identity_hashes_and_timings(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            trace_path = Path(temporary_dir) / "trace.jsonl"
            agent = DataSubagent(
                wren=FakeWrenAdapter(),
                llm=StaticLLMAdapter("select count(*) as order_count from orders"),
                trace_store=JsonlTraceStore(trace_path),
            )
            agent.ask_data_question(
                "How many orders are there?",
                eval_identity={"run_id": "run-1", "eval_id": "count", "suite_name": "smoke"},
            )
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertEqual(trace["schema_version"], 2)
            self.assertEqual(trace["runtime_identity"]["runtime_name"], "data_subagent")
            self.assertEqual(trace["eval_identity"]["eval_id"], "count")
            self.assertRegex(trace["data_identity"]["schema_fingerprint"], r"^sha256:")
            self.assertRegex(trace["data_identity"]["result_sha256"], r"^sha256:")
            self.assertIsInstance(trace["timings_ms"]["total"], int)


if __name__ == "__main__":
    unittest.main()
