from __future__ import annotations

import unittest

from data_agent_improvement.models import (
    Actor,
    ActorType,
    AuthorityStatus,
    CorrectionPair,
    ExpectedCorrection,
    FeedbackRecord,
    FeedbackType,
    ObservedCorrection,
    Provenance,
    Sentiment,
    deterministic_case_id,
    sha256_text,
)


TRACE_ID = "trace_" + "a" * 32
FEEDBACK_ID = "feedback_" + "b" * 32
CREATED_AT = "2026-07-16T00:00:00+00:00"


class ImprovementModelsTest(unittest.TestCase):
    def test_feedback_round_trip_preserves_scoped_authority_claim(self):
        record = _feedback_record()
        loaded = FeedbackRecord.from_dict(record.to_dict())
        self.assertEqual(loaded, record)
        self.assertEqual(loaded.actor.actor_type, ActorType.BUSINESS_CONTRIBUTOR)
        self.assertEqual(loaded.actor.authority_status, AuthorityStatus.UNVERIFIED)

    def test_business_truth_requires_statement(self):
        with self.assertRaisesRegex(ValueError, "business statement"):
            _feedback_record(
                feedback_type=FeedbackType.BUSINESS_TRUTH,
                correction_pair=CorrectionPair(
                    observed=ObservedCorrection(
                        TRACE_ID,
                        sha256_text("answer"),
                        sha256_text("sql"),
                    ),
                    expected=ExpectedCorrection(answer="expected"),
                ),
            )

    def test_expected_sql_requires_sql(self):
        with self.assertRaisesRegex(ValueError, "expected SQL"):
            _feedback_record(
                feedback_type=FeedbackType.EXPECTED_SQL,
                correction_pair=CorrectionPair(
                    observed=ObservedCorrection(
                        TRACE_ID,
                        sha256_text("answer"),
                        sha256_text("sql"),
                    ),
                    expected=ExpectedCorrection(answer="expected"),
                ),
            )

    def test_deterministic_case_id_is_stable(self):
        identity = f"RUNTIME_TRACE:{TRACE_ID}:WREN_DRY_RUN"
        self.assertEqual(deterministic_case_id(identity), deterministic_case_id(identity))
        self.assertRegex(deterministic_case_id(identity), r"^case_[0-9a-f]{24}$")

    def test_invalid_feedback_identifier_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "feedback_id"):
            _feedback_record(feedback_id="../../feedback_bad")

    def test_credential_like_feedback_text_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "credential-like"):
            FeedbackRecord(
                **{
                    **_feedback_record().to_dict(),
                    "comment": "password=hunter2",
                    "feedback_type": FeedbackType.BUSINESS_TRUTH,
                    "sentiment": Sentiment.NEGATIVE,
                    "correction_pair": _feedback_record().correction_pair,
                    "provenance": _feedback_record().provenance,
                    "actor": _feedback_record().actor,
                }
            )


def _feedback_record(
    *,
    feedback_id: str = FEEDBACK_ID,
    feedback_type: FeedbackType = FeedbackType.BUSINESS_TRUTH,
    correction_pair: CorrectionPair | None = None,
) -> FeedbackRecord:
    pair = correction_pair or CorrectionPair(
        observed=ObservedCorrection(TRACE_ID, sha256_text("answer"), sha256_text("sql")),
        expected=ExpectedCorrection(business_statements=["Only completed orders count."]),
    )
    return FeedbackRecord(
        schema_version=1,
        feedback_id=feedback_id,
        trace_id=TRACE_ID,
        feedback_type=feedback_type,
        sentiment=Sentiment.NEGATIVE,
        comment="Incorrect business scope.",
        correction_pair=pair,
        provenance=Provenance("user_declared_business_truth", "session-1", "Completed only."),
        actor=Actor(
            actor_id="business-user",
            actor_type=ActorType.BUSINESS_CONTRIBUTOR,
            authority_status=AuthorityStatus.UNVERIFIED,
            authorized_context_ids=["data_agent_mvp"],
            authorized_scopes=["realized_revenue"],
        ),
        created_at=CREATED_AT,
    )


if __name__ == "__main__":
    unittest.main()
