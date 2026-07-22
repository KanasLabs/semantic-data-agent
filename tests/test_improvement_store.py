from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from data_agent_improvement.models import (
    Actor,
    CorrectionPair,
    ContextIdentity,
    EvidenceRef,
    ExpectedCorrection,
    FeedbackRecord,
    FeedbackType,
    FailureCase,
    FailurePhase,
    ObservedCorrection,
    Provenance,
    Sentiment,
    Signal,
    SourceIdentity,
    SourceType,
    TriageStatus,
    deterministic_case_id,
    sha256_text,
)
from data_agent_improvement.store import ImmutableRecordError, ImprovementStore


TRACE_ID = "trace_" + "c" * 32
CREATED_AT = "2026-07-16T00:00:00+00:00"


class ImprovementStoreTest(unittest.TestCase):
    def test_feedback_is_immutable_and_filterable_by_trace(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store = ImprovementStore(Path(temporary_dir) / "registry")
            feedback = _feedback()
            path = store.create_feedback(feedback)
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
            self.assertEqual(store.get_feedback(feedback.feedback_id), feedback)
            self.assertEqual(store.list_feedback(TRACE_ID), [feedback])
            with self.assertRaises(ImmutableRecordError):
                store.create_feedback(feedback)

    def test_case_creation_is_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store = ImprovementStore(Path(temporary_dir) / "registry")
            case = _case()
            path, created = store.create_case(case)
            same_path, created_again = store.create_case(case)
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(path, same_path)
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
            self.assertEqual(store.get_case(case.case_id), case)

    def test_case_identity_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store = ImprovementStore(Path(temporary_dir) / "registry")
            case = _case()
            store.create_case(case)
            changed = replace(case, observed_status="different")
            with self.assertRaises(ImmutableRecordError):
                store.create_case(changed)

    def test_path_traversal_identifier_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store = ImprovementStore(Path(temporary_dir) / "registry")
            with self.assertRaisesRegex(ValueError, "case_id"):
                store.get_case("../../case_bad")

    def test_registry_does_not_create_future_phase_directories(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir) / "registry"
            store = ImprovementStore(root)
            store.create_case(_case())
            self.assertFalse((root / "findings").exists())
            self.assertFalse((root / "jobs").exists())


def _case() -> FailureCase:
    identity = f"RUNTIME_TRACE:{TRACE_ID}:WREN_DRY_RUN"
    return FailureCase(
        schema_version=1,
        case_id=deterministic_case_id(identity),
        source_type=SourceType.RUNTIME_TRACE,
        source_identity=SourceIdentity(trace_id=TRACE_ID),
        context_identity=ContextIdentity(),
        question="How many orders?",
        observed_status="failed",
        failure_phase=FailurePhase.WREN_DRY_RUN,
        signals=[Signal("TRACE_ERROR", "Column not found")],
        evidence_refs=[EvidenceRef("TRACE", TRACE_ID, "data/traces/test.jsonl")],
        triage_status=TriageStatus.UNTRIAGED,
        root_cause=None,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def _feedback() -> FeedbackRecord:
    return FeedbackRecord(
        schema_version=1,
        feedback_id="feedback_" + "4" * 32,
        trace_id=TRACE_ID,
        feedback_type=FeedbackType.CORRECTION,
        sentiment=Sentiment.NEGATIVE,
        comment="Wrong answer.",
        correction_pair=CorrectionPair(
            observed=ObservedCorrection(
                TRACE_ID,
                sha256_text("wrong"),
                sha256_text("select 1"),
            ),
            expected=ExpectedCorrection(answer="correct"),
        ),
        provenance=Provenance("user_feedback", "session", "Correct this answer."),
        actor=Actor("user"),
        created_at=CREATED_AT,
    )


if __name__ == "__main__":
    unittest.main()
