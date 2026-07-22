from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_agent_improvement.ingestion import ingest_eval_run, ingest_traces
from data_agent_improvement.models import FailurePhase, SourceType
from data_agent_improvement.store import ImprovementStore


FAILED_TRACE_ID = "trace_" + "e" * 32
CLARITY_TRACE_ID = "trace_" + "f" * 32
SUCCESS_TRACE_ID = "trace_" + "1" * 32


class ImprovementIngestionTest(unittest.TestCase):
    def test_trace_ingestion_is_legacy_compatible_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            trace_path = root / "data" / "traces" / "trace.jsonl"
            _write_jsonl(
                trace_path,
                [
                    {
                        "trace_id": FAILED_TRACE_ID,
                        "question": "Broken query",
                        "created_at": "2026-07-16T00:00:00+00:00",
                        "status": "failed",
                        "dry_run_results": [{"ok": False, "message": "column missing"}],
                        "error": "column missing",
                    },
                    {
                        "trace_id": CLARITY_TRACE_ID,
                        "question": "?",
                        "created_at": "2026-07-16T00:01:00+00:00",
                        "status": "need_clarification",
                    },
                    {
                        "trace_id": SUCCESS_TRACE_ID,
                        "question": "Working query",
                        "created_at": "2026-07-16T00:02:00+00:00",
                        "status": "success",
                    },
                ],
            )
            store = ImprovementStore(root / "data" / "improvement_registry")
            first = ingest_traces(store=store, trace_path=trace_path, project_root=root)
            second = ingest_traces(store=store, trace_path=trace_path, project_root=root)
            self.assertEqual((first.scanned, first.eligible, first.created), (3, 2, 2))
            self.assertEqual(second.created, 0)
            self.assertEqual(second.existing, 2)
            cases = store.list_cases()
            self.assertEqual(
                {case.failure_phase for case in cases},
                {FailurePhase.WREN_DRY_RUN, FailurePhase.CLARITY},
            )
            self.assertTrue(all(case.trace_schema_version == 1 for case in cases))
            self.assertTrue(all(case.runtime_identity_missing for case in cases))

    def test_eval_failure_and_triage_are_ingested_without_claiming_root_cause(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            run_path = root / "data" / "evals" / "runs" / "run.jsonl"
            _write_jsonl(
                run_path,
                [
                    {
                        "eval_id": "currency",
                        "question": "What is revenue?",
                        "status": "fail",
                        "review_status": "needs_triage",
                        "failure_reasons": ["answer missing expected fragment(s): ['CNY']"],
                        "started_at": "2026-07-16T00:00:00+00:00",
                    },
                    {
                        "eval_id": "pass",
                        "question": "Count orders",
                        "status": "pass",
                        "review_status": "auto_pass",
                        "failure_reasons": [],
                        "started_at": "2026-07-16T00:01:00+00:00",
                    },
                ],
            )
            store = ImprovementStore(root / "data" / "improvement_registry")
            summary = ingest_eval_run(
                store=store,
                run_path=run_path,
                run_id="run-1",
                project_root=root,
            )
            self.assertEqual((summary.scanned, summary.eligible, summary.created), (2, 1, 1))
            case = store.list_cases()[0]
            self.assertEqual(case.source_type, SourceType.EVAL_RECORD)
            self.assertIsNone(case.root_cause)
            self.assertEqual(case.signals[0].signal_type, "ANSWER_MISSING_EXPECTED_FRAGMENT")
            self.assertEqual(case.signals[0].value, "CNY")

    def test_invalid_json_reports_file_and_line(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            trace_path = root / "data" / "traces" / "bad.jsonl"
            trace_path.parent.mkdir(parents=True)
            trace_path.write_text("{}\n{bad}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"bad.jsonl:2"):
                ingest_traces(
                    store=ImprovementStore(root / "registry"),
                    trace_path=trace_path,
                    project_root=root,
                )

    def test_evidence_outside_project_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as other_dir:
            outside = Path(other_dir) / "trace.jsonl"
            outside.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inside project root"):
                ingest_traces(
                    store=ImprovementStore(Path(root_dir) / "registry"),
                    trace_path=outside,
                    project_root=Path(root_dir),
                )

    def test_trace_error_credentials_are_redacted_before_storage(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            trace_path = root / "data" / "traces" / "trace.jsonl"
            _write_jsonl(
                trace_path,
                [
                    {
                        "trace_id": FAILED_TRACE_ID,
                        "question": "Connection check",
                        "status": "failed",
                        "error": "connection failed password=hunter2",
                    }
                ],
            )
            store = ImprovementStore(root / "registry")
            ingest_traces(store=store, trace_path=trace_path, project_root=root)
            case_text = store.list_cases()[0].signals[0].message
            self.assertIn("password=[REDACTED]", case_text)
            self.assertNotIn("hunter2", case_text)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
