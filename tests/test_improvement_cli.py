from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from data_agent_improvement.cli import main
from data_agent_improvement.models import (
    Actor,
    ActorType,
    CorrectionPair,
    ExpectedCorrection,
    FeedbackRecord,
    FeedbackType,
    ObservedCorrection,
    Provenance,
    Sentiment,
    sha256_text,
)
from data_agent_improvement.store import ImprovementStore


class ImprovementCliTest(unittest.TestCase):
    def test_routing_proposal_confirmation_requires_explicit_acknowledgement(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            args = [
                "data-agent-improvement",
                "confirm-routing-proposal",
                "--project-root",
                str(root),
                "--registry-root",
                "registry",
                "--routing-proposal",
                "routeproposal_" + "2" * 32,
                "--confirmed-by",
                "engineering-reviewer",
                "--rationale",
                "Reviewed evidence supports the proposed route.",
            ]
            with patch("sys.argv", args):
                with self.assertRaisesRegex(
                    ValueError,
                    "project-routing-confirmed",
                ):
                    main()

    def test_routing_decision_requires_explicit_acknowledgement(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            args = [
                "data-agent-improvement",
                "create-routing-decision",
                "--project-root",
                str(root),
                "--registry-root",
                "registry",
                "--eval-target",
                "evaltarget_" + "3" * 32,
                "--target-type",
                "SOURCE_CODE",
                "--evidence-json",
                json.dumps(
                    {
                        "evidence_type": "SOURCE_REPRODUCTION",
                        "evidence_id": "source-test",
                        "summary": "A source unit test reproduces the failure.",
                    }
                ),
                "--decided-by",
                "engineering-reviewer",
                "--rationale",
                "Context is correct and source code still fails.",
            ]
            with patch("sys.argv", args):
                with self.assertRaisesRegex(
                    ValueError,
                    "project-routing-confirmed",
                ):
                    main()

    def test_source_development_execution_requires_explicit_acknowledgement(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            args = [
                "data-agent-improvement",
                "execute-source-job-dev",
                "--project-root",
                str(root),
                "--registry-root",
                "registry",
                "--job",
                "job_" + "2" * 32,
                "--execute",
            ]
            with patch("sys.argv", args):
                with self.assertRaisesRegex(
                    ValueError,
                    "acknowledge-host-session-development-only",
                ):
                    main()

    def test_development_execution_requires_explicit_acknowledgement(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            args = [
                "data-agent-improvement",
                "execute-semantic-job-dev",
                "--project-root",
                str(root),
                "--registry-root",
                "registry",
                "--job",
                "job_" + "1" * 32,
                "--context-registry-root",
                str(root / "context-registry"),
                "--wren-home",
                str(root / "wren-home"),
                "--wren-bin",
                str(root / "wren"),
                "--execute",
            ]
            with patch("sys.argv", args):
                with self.assertRaisesRegex(
                    ValueError,
                    "acknowledge-host-session-development-only",
                ):
                    main()

    def test_authority_command_requires_acknowledgement_and_records_decision(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            store = ImprovementStore(root / "registry")
            feedback = _feedback()
            store.create_feedback(feedback)
            base_args = [
                "data-agent-improvement",
                "record-authority",
                "--project-root",
                str(root),
                "--registry-root",
                "registry",
                "--feedback-id",
                feedback.feedback_id,
                "--decision",
                "CONFIRM",
                "--context-id",
                "data_agent_mvp",
                "--scope",
                "realized_revenue",
                "--decided-by",
                "project-owner",
                "--reason",
                "Confirmed narrow business ownership.",
            ]
            with patch("sys.argv", base_args):
                with self.assertRaisesRegex(ValueError, "project-authority-confirmed"):
                    main()
            output = io.StringIO()
            with patch("sys.argv", [*base_args, "--project-authority-confirmed"]):
                with redirect_stdout(output):
                    main()
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["decision"], "CONFIRM")
            self.assertEqual(payload["feedback_id"], feedback.feedback_id)
            self.assertEqual(len(store.list_authority_decisions(feedback.feedback_id)), 1)


def _feedback() -> FeedbackRecord:
    trace_id = "trace_" + "c" * 32
    return FeedbackRecord(
        schema_version=1,
        feedback_id="feedback_" + "d" * 32,
        trace_id=trace_id,
        feedback_type=FeedbackType.BUSINESS_TRUTH,
        sentiment=Sentiment.NEGATIVE,
        comment="Completed orders only.",
        correction_pair=CorrectionPair(
            observed=ObservedCorrection(
                trace_id,
                sha256_text("wrong"),
                sha256_text("select 1"),
            ),
            expected=ExpectedCorrection(
                business_statements=["Only completed orders are realized revenue."]
            ),
        ),
        provenance=Provenance(
            "user_declared_business_truth",
            "session",
            "Completed only.",
        ),
        actor=Actor(
            "business-user",
            actor_type=ActorType.BUSINESS_CONTRIBUTOR,
        ),
        created_at="2026-07-16T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
