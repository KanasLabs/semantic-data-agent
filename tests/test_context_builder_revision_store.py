from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_subagent_context_builder.revision_store import (
    CandidateStatus,
    HumanTaskStatus,
    HumanTaskType,
    InvalidTransitionError,
    ProvenanceType,
    ReviewPacket,
    RevisionStatus,
    RevisionStore,
    SemanticDiff,
    StaleBaseVersionError,
)


class RevisionStoreTest(unittest.TestCase):
    def test_revision_creates_new_candidate_and_preserves_business_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RevisionStore(root / "registry")
            base = store.create_candidate(
                context_id="data_agent_mvp",
                project_path=root / "base_project",
            )

            request, candidate = store.create_revision(
                base_candidate_id=base.candidate_id,
                user_instruction="total_amount is CNY; completed orders are realized revenue",
                requested_scope=["orders.total_amount", "realized_revenue"],
                candidate_project_path=root / "candidate_v2",
            )

            self.assertNotEqual(candidate.candidate_id, base.candidate_id)
            self.assertEqual(candidate.base_candidate_id, base.candidate_id)
            self.assertEqual(candidate.version, 2)
            self.assertEqual(store.get_candidate(base.candidate_id).status, CandidateStatus.DRAFT)
            self.assertEqual(
                request.provenance.provenance_type,
                ProvenanceType.USER_DECLARED_BUSINESS_TRUTH,
            )
            change_request_path = (
                root / "registry" / "revisions" / request.revision_id / "change_request.json"
            )
            persisted = json.loads(change_request_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["candidate_id"], candidate.candidate_id)
            self.assertEqual(
                persisted["provenance"]["provenance_type"],
                "user_declared_business_truth",
            )

    def test_candidate_publish_requires_validation_review_and_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RevisionStore(Path(tmp) / "registry")
            candidate = store.create_candidate(
                context_id="sales",
                project_path=Path(tmp) / "sales_project",
            )

            with self.assertRaisesRegex(InvalidTransitionError, "DRAFT -> PUBLISHED"):
                store.transition_candidate(candidate.candidate_id, CandidateStatus.PUBLISHED)

            store.transition_candidate(candidate.candidate_id, CandidateStatus.AUTO_VALIDATING)
            store.transition_candidate(candidate.candidate_id, CandidateStatus.REVIEW_REQUIRED)
            store.transition_candidate(candidate.candidate_id, CandidateStatus.APPROVED)
            published = store.transition_candidate(candidate.candidate_id, CandidateStatus.PUBLISHED)

            self.assertEqual(published.status, CandidateStatus.PUBLISHED)
            with self.assertRaises(InvalidTransitionError):
                store.transition_candidate(candidate.candidate_id, CandidateStatus.STALE)

    def test_clarification_task_is_persisted_and_resumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RevisionStore(root / "registry")
            base = store.create_candidate(context_id="sales", project_path=root / "base")
            request, _ = store.create_revision(
                base_candidate_id=base.candidate_id,
                user_instruction="make revenue correct",
                candidate_project_path=root / "candidate",
            )
            store.transition_revision(request.revision_id, RevisionStatus.CLARIFICATION_REQUIRED)
            task = store.create_human_task(
                revision_id=request.revision_id,
                task_type=HumanTaskType.CLARIFICATION,
                questions=[
                    (
                        "Which order statuses count as realized revenue?",
                        "The database cannot establish accounting policy.",
                    )
                ],
            )

            reopened_store = RevisionStore(root / "registry")
            reopened_task = reopened_store.get_human_task(request.revision_id, task.task_id)
            with self.assertRaisesRegex(InvalidTransitionError, "unanswered clarification"):
                reopened_store.transition_revision(
                    request.revision_id,
                    RevisionStatus.REVISING,
                    expected_status=RevisionStatus.CLARIFICATION_REQUIRED,
                )
            answer = reopened_store.answer_human_question(
                revision_id=request.revision_id,
                task_id=task.task_id,
                question_id=reopened_task.questions[0].question_id,
                answer="Only completed orders count as realized revenue.",
            )

            self.assertEqual(
                answer.provenance.provenance_type,
                ProvenanceType.USER_DECLARED_BUSINESS_TRUTH,
            )
            self.assertEqual(
                reopened_store.get_human_task(request.revision_id, task.task_id).status,
                HumanTaskStatus.ANSWERED,
            )
            resumed = reopened_store.transition_revision(
                request.revision_id,
                RevisionStatus.REVISING,
                expected_status=RevisionStatus.CLARIFICATION_REQUIRED,
            )
            self.assertEqual(resumed.status, RevisionStatus.REVISING)

    def test_expected_base_version_detects_stale_revision_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RevisionStore(root / "registry")
            base = store.create_candidate(context_id="sales", project_path=root / "base")

            with self.assertRaisesRegex(StaleBaseVersionError, "expected version 2"):
                store.create_revision(
                    base_candidate_id=base.candidate_id,
                    expected_base_version=2,
                    user_instruction="total_amount is CNY",
                    candidate_project_path=root / "candidate",
                )

            self.assertFalse((root / "registry" / "revisions").exists())

    def test_clarification_and_approval_tasks_are_separate_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RevisionStore(root / "registry")
            base = store.create_candidate(context_id="sales", project_path=root / "base")
            request, _ = store.create_revision(
                base_candidate_id=base.candidate_id,
                user_instruction="total_amount is CNY",
                candidate_project_path=root / "candidate",
            )

            with self.assertRaisesRegex(InvalidTransitionError, "Approval tasks"):
                store.create_human_task(
                    revision_id=request.revision_id,
                    task_type=HumanTaskType.APPROVAL,
                    questions=[("Approve this candidate?", "Explicit human approval is required.")],
                )

            store.transition_revision(request.revision_id, RevisionStatus.REVISING)
            store.transition_revision(request.revision_id, RevisionStatus.AUTO_VALIDATING)
            store.transition_revision(request.revision_id, RevisionStatus.REVIEW_REQUIRED)
            approval = store.create_human_task(
                revision_id=request.revision_id,
                task_type=HumanTaskType.APPROVAL,
                questions=[("Approve this candidate?", "Explicit human approval is required.")],
            )
            self.assertEqual(approval.task_type, HumanTaskType.APPROVAL)
            with self.assertRaisesRegex(InvalidTransitionError, "completed approval task"):
                store.transition_revision(request.revision_id, RevisionStatus.APPROVED)

            store.answer_human_question(
                revision_id=request.revision_id,
                task_id=approval.task_id,
                question_id=approval.questions[0].question_id,
                answer="Approved for publication review.",
            )
            approved = store.transition_revision(request.revision_id, RevisionStatus.APPROVED)
            self.assertEqual(approved.status, RevisionStatus.APPROVED)

    def test_semantic_diff_and_review_packet_are_revision_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RevisionStore(root / "registry")
            base = store.create_candidate(context_id="sales", project_path=root / "base")
            request, candidate = store.create_revision(
                base_candidate_id=base.candidate_id,
                user_instruction="total_amount is CNY",
                candidate_project_path=root / "candidate",
            )
            store.transition_revision(request.revision_id, RevisionStatus.REVISING)
            store.transition_revision(request.revision_id, RevisionStatus.AUTO_VALIDATING)
            store.transition_revision(request.revision_id, RevisionStatus.REVIEW_REQUIRED)

            diff_path = store.write_semantic_diff(
                SemanticDiff(
                    revision_id=request.revision_id,
                    base_candidate_id=base.candidate_id,
                    candidate_id=candidate.candidate_id,
                    fields=[
                        {
                            "model": "orders",
                            "field": "total_amount",
                            "change": "description_changed",
                        }
                    ],
                )
            )
            packet_path = store.write_review_packet(
                ReviewPacket(
                    revision_id=request.revision_id,
                    candidate_id=candidate.candidate_id,
                    status=RevisionStatus.REVIEW_REQUIRED,
                    summary="Added the user-declared CNY unit.",
                )
            )

            self.assertTrue(diff_path.exists())
            self.assertTrue(packet_path.exists())
            self.assertEqual(
                json.loads(diff_path.read_text(encoding="utf-8"))["fields"][0]["field"],
                "total_amount",
            )

    def test_expected_status_detects_stale_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RevisionStore(Path(tmp) / "registry")
            candidate = store.create_candidate(
                context_id="sales",
                project_path=Path(tmp) / "sales_project",
            )
            store.transition_candidate(candidate.candidate_id, CandidateStatus.AUTO_VALIDATING)

            with self.assertRaisesRegex(StaleBaseVersionError, "expected DRAFT"):
                store.transition_candidate(
                    candidate.candidate_id,
                    CandidateStatus.REVIEW_REQUIRED,
                    expected_status=CandidateStatus.DRAFT,
                )

    def test_invalid_identifiers_cannot_escape_registry_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RevisionStore(Path(tmp) / "registry")
            with self.assertRaises(ValueError):
                store.get_candidate("../outside")


if __name__ == "__main__":
    unittest.main()
