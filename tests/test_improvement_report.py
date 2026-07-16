from __future__ import annotations

import unittest

from data_agent_improvement.ingestion import failure_case_from_trace
from data_agent_improvement.report import render_triage_report


class ImprovementReportTest(unittest.TestCase):
    def test_report_summarizes_cases_without_copying_result_rows(self):
        trace_id = "trace_" + "2" * 32
        case = failure_case_from_trace(
            {
                "trace_id": trace_id,
                "question": "Why did this fail?",
                "created_at": "2026-07-16T00:00:00+00:00",
                "status": "failed",
                "error": "dry run failed",
                "dry_run_results": [{"ok": False}],
                "result_preview": [{"secret_business_row": "must-not-appear"}],
            },
            "data/traces/test.jsonl",
        )
        report = render_triage_report([case])
        self.assertIn("Root cause has not been classified", report)
        self.assertIn("RUNTIME_TRACE=1", report)
        self.assertIn("WREN_DRY_RUN=1", report)
        self.assertNotIn("secret_business_row", report)
        self.assertNotIn("must-not-appear", report)


if __name__ == "__main__":
    unittest.main()
