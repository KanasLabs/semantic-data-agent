from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from data_subagent_context_builder.review_workflow import (
    approve_candidate,
    publish_candidate,
    review_candidate,
    rollback_context,
)
from data_subagent_context_builder.revision_store import (
    CandidateStatus,
    InvalidTransitionError,
    ProvenanceType,
    ReviewPacket,
    RevisionStatus,
    RevisionStore,
    SemanticDiff,
)


class ReviewWorkflowTest(unittest.TestCase):
    def test_review_approve_and_publish_are_separate_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RevisionStore(root / "registry")
            base = store.create_candidate(context_id="sales", project_path=root / "base")
            request, candidate = store.create_revision(
                base_candidate_id=base.candidate_id,
                user_instruction="total_amount is CNY",
                candidate_project_path=root / "candidate",
            )
            _move_to_review(store, request.revision_id, candidate.candidate_id)
            store.write_semantic_diff(
                SemanticDiff(
                    revision_id=request.revision_id,
                    base_candidate_id=base.candidate_id,
                    candidate_id=candidate.candidate_id,
                )
            )
            store.write_review_packet(
                ReviewPacket(
                    revision_id=request.revision_id,
                    candidate_id=candidate.candidate_id,
                    status=RevisionStatus.REVIEW_REQUIRED,
                    summary="Added CNY currency semantics.",
                )
            )

            review = review_candidate(
                registry_root=root / "registry",
                candidate_id=candidate.candidate_id,
                store=store,
            )
            approval = approve_candidate(
                registry_root=root / "registry",
                candidate_id=candidate.candidate_id,
                approval_note="Reviewed and approved for publication.",
                store=store,
            )

            self.assertEqual(review["candidate"]["status"], "REVIEW_REQUIRED")
            self.assertIsNotNone(review["review_packet"])
            self.assertEqual(approval["candidate_status"], "APPROVED")
            self.assertEqual(
                approval["approval_provenance"],
                ProvenanceType.USER_REVIEW_DECISION.value,
            )
            self.assertIsNone(store.get_published_context("sales"))

            publication = publish_candidate(
                registry_root=root / "registry",
                candidate_id=candidate.candidate_id,
                store=store,
            )
            self.assertEqual(publication["publication"]["candidate_id"], candidate.candidate_id)
            self.assertEqual(
                store.get_candidate(candidate.candidate_id).status,
                CandidateStatus.PUBLISHED,
            )

    def test_publish_pointer_can_roll_back_to_previous_published_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RevisionStore(root / "registry")
            first = _create_approved_candidate(store, root, version=1)
            second = _create_approved_candidate(store, root, version=2)
            store.publish_candidate(first.candidate_id)
            second_publication = store.publish_candidate(second.candidate_id)

            self.assertEqual(second_publication["previous_candidate_id"], first.candidate_id)
            rolled_back = rollback_context(
                registry_root=root / "registry",
                context_id="sales",
                store=store,
            )

            self.assertEqual(rolled_back["publication"]["action"], "rollback")
            self.assertEqual(rolled_back["publication"]["candidate_id"], first.candidate_id)
            self.assertEqual(
                store.get_published_context("sales")["candidate_id"],
                first.candidate_id,
            )

    def test_development_only_candidate_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RevisionStore(root / "registry")
            base = store.create_candidate(context_id="sales", project_path=root / "base")
            request, candidate = store.create_revision(
                base_candidate_id=base.candidate_id,
                user_instruction="DEVELOPMENT_ONLY candidate",
                candidate_project_path=root / "candidate",
                release_eligible=False,
            )
            _move_to_review(store, request.revision_id, candidate.candidate_id)
            store.write_review_packet(
                ReviewPacket(
                    revision_id=request.revision_id,
                    candidate_id=candidate.candidate_id,
                    status=RevisionStatus.REVIEW_REQUIRED,
                    summary="Development-only candidate.",
                )
            )

            with self.assertRaisesRegex(InvalidTransitionError, "not release eligible"):
                approve_candidate(
                    registry_root=root / "registry",
                    candidate_id=candidate.candidate_id,
                    approval_note="Attempted approval.",
                    store=store,
                )
            with self.assertRaisesRegex(InvalidTransitionError, "not release eligible"):
                store.transition_candidate(candidate.candidate_id, CandidateStatus.APPROVED)

            self.assertEqual(
                store.get_candidate(candidate.candidate_id).status,
                CandidateStatus.REVIEW_REQUIRED,
            )
            self.assertEqual(
                store.get_revision(request.revision_id).status,
                RevisionStatus.REVIEW_REQUIRED,
            )


def _move_to_review(store: RevisionStore, revision_id: str, candidate_id: str) -> None:
    store.transition_revision(revision_id, RevisionStatus.REVISING)
    store.transition_revision(revision_id, RevisionStatus.AUTO_VALIDATING)
    store.transition_revision(revision_id, RevisionStatus.REVIEW_REQUIRED)
    store.transition_candidate(candidate_id, CandidateStatus.AUTO_VALIDATING)
    store.transition_candidate(candidate_id, CandidateStatus.REVIEW_REQUIRED)


def _create_approved_candidate(
    store: RevisionStore,
    root: Path,
    *,
    version: int,
):
    candidate = store.create_candidate(
        context_id="sales",
        project_path=root / f"candidate_{version}",
        version=version,
    )
    store.transition_candidate(candidate.candidate_id, CandidateStatus.AUTO_VALIDATING)
    store.transition_candidate(candidate.candidate_id, CandidateStatus.REVIEW_REQUIRED)
    return store.transition_candidate(candidate.candidate_id, CandidateStatus.APPROVED)


if __name__ == "__main__":
    unittest.main()
