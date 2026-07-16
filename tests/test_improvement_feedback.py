from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_agent_improvement.feedback import record_feedback, verify_observed_hashes
from data_agent_improvement.models import (
    Actor,
    ActorType,
    AuthorityStatus,
    FeedbackType,
    Provenance,
    Sentiment,
)
from data_agent_improvement.store import ImprovementStore


TRACE_ID = "trace_" + "d" * 32


class ImprovementFeedbackTest(unittest.TestCase):
    def test_business_correction_freezes_observed_hashes_without_copying_rows(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            trace_path = root / "data" / "traces" / "trace.jsonl"
            trace = _write_trace(trace_path)
            store = ImprovementStore(root / "data" / "improvement_registry")
            result = record_feedback(
                store=store,
                project_root=root,
                trace_path=trace_path,
                trace_id=TRACE_ID,
                feedback_type=FeedbackType.BUSINESS_TRUTH,
                sentiment=Sentiment.NEGATIVE,
                comment="Shipped orders are not realized revenue.",
                expected_answer="721.80 CNY",
                business_statements=["Only completed orders count as realized revenue."],
                provenance=Provenance(
                    "user_declared_business_truth",
                    "session-1",
                    "Completed only.",
                ),
                actor=_actor(),
            )
            verify_observed_hashes(result.feedback, trace)
            stored_text = result.feedback_path.read_text(encoding="utf-8")
            case_text = result.case_path.read_text(encoding="utf-8")
            self.assertNotIn("result_preview", stored_text)
            self.assertNotIn("result_preview", case_text)
            self.assertNotIn("721.8, 999", case_text)
            self.assertEqual(
                result.feedback.actor.authority_status,
                AuthorityStatus.UNVERIFIED,
            )

    def test_generic_negative_feedback_remains_without_correction_pair(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            trace_path = root / "data" / "traces" / "trace.jsonl"
            _write_trace(trace_path)
            result = record_feedback(
                store=ImprovementStore(root / "data" / "improvement_registry"),
                project_root=root,
                trace_path=trace_path,
                trace_id=TRACE_ID,
                feedback_type=FeedbackType.RATING,
                sentiment=Sentiment.NEGATIVE,
                comment="This looks wrong.",
                provenance=Provenance("user_feedback", "session-2", "Looks wrong."),
                actor=_actor(),
            )
            self.assertIsNone(result.feedback.correction_pair)

    def test_positive_rating_does_not_create_failure_case(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            trace_path = root / "data" / "traces" / "trace.jsonl"
            _write_trace(trace_path)
            result = record_feedback(
                store=ImprovementStore(root / "data" / "improvement_registry"),
                project_root=root,
                trace_path=trace_path,
                trace_id=TRACE_ID,
                feedback_type=FeedbackType.RATING,
                sentiment=Sentiment.POSITIVE,
                comment="Looks correct.",
                provenance=Provenance("user_feedback", "session-positive", "Looks correct."),
                actor=_actor(),
            )
            self.assertIsNone(result.case)
            self.assertFalse(result.case_created)

    def test_expected_sql_is_stored_but_never_executed(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            trace_path = root / "data" / "traces" / "trace.jsonl"
            _write_trace(trace_path)
            marker = root / "must_not_exist"
            expected_sql = f"SELECT 1; WRITE {marker}"
            result = record_feedback(
                store=ImprovementStore(root / "data" / "improvement_registry"),
                project_root=root,
                trace_path=trace_path,
                trace_id=TRACE_ID,
                feedback_type=FeedbackType.EXPECTED_SQL,
                sentiment=Sentiment.NEUTRAL,
                comment="Expected SQL reference.",
                expected_sql=expected_sql,
                provenance=Provenance("user_feedback", "session-3", "Reference SQL."),
                actor=_actor(),
            )
            self.assertEqual(result.feedback.correction_pair.expected.sql, expected_sql)
            self.assertFalse(marker.exists())

    def test_debug_import_can_record_generic_feedback_when_trace_file_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            result = record_feedback(
                store=ImprovementStore(root / "data" / "improvement_registry"),
                project_root=root,
                trace_path=root / "data" / "traces" / "missing.jsonl",
                trace_id=TRACE_ID,
                feedback_type=FeedbackType.RATING,
                sentiment=Sentiment.NEGATIVE,
                comment="Imported historical rating.",
                provenance=Provenance("import", "archive-1", "Historical rating."),
                actor=_actor(),
                allow_missing_trace=True,
            )
            self.assertIsNone(result.feedback.correction_pair)
            self.assertEqual(len(result.case.evidence_refs), 1)


def _write_trace(path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    trace = {
        "schema_version": 2,
        "trace_id": TRACE_ID,
        "question": "What is realized revenue?",
        "created_at": "2026-07-16T00:00:00+00:00",
        "status": "success",
        "final_sql": "SELECT SUM(total_amount) FROM orders",
        "answer": "999 USD",
        "result_preview": [{"value": "721.8, 999"}],
        "runtime_identity": {"runtime_name": "data_subagent"},
        "context_identity": {
            "context_id": "data_agent_mvp",
            "candidate_id": None,
            "context_version": None,
            "publication_id": None,
            "wren_project_fingerprint": None,
        },
    }
    path.write_text(json.dumps(trace) + "\n", encoding="utf-8")
    return trace


def _actor() -> Actor:
    return Actor(
        actor_id="business-user",
        actor_type=ActorType.BUSINESS_CONTRIBUTOR,
        authority_status=AuthorityStatus.UNVERIFIED,
    )


if __name__ == "__main__":
    unittest.main()
