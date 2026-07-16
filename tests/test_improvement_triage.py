from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from data_agent_improvement.models import (
    Actor,
    ActorType,
    AuthorityDecisionType,
    ContextIdentity,
    CorrectionPair,
    EvalTargetStatus,
    EvidenceRef,
    ExpectedCorrection,
    FeedbackRecord,
    FeedbackType,
    FailureCase,
    FailurePhase,
    FindingStatus,
    GroupingMode,
    ObservedCorrection,
    Provenance,
    ResultContract,
    RootCauseCandidate,
    SemanticConstraints,
    Sentiment,
    Signal,
    SourceIdentity,
    SourceType,
    TriageStatus,
    deterministic_case_id,
    sha256_text,
)
from data_agent_improvement.store import ImmutableRecordError, ImprovementStore
from data_agent_improvement.triage import (
    approve_eval_target,
    create_eval_target,
    create_grouped_finding,
    dismiss_finding,
    freeze_eval_target,
    record_authority_decision,
    submit_eval_target_for_review,
    suggest_groups,
)


TRACE_ID = "trace_" + "5" * 32
FEEDBACK_ID = "feedback_" + "6" * 32
CREATED_AT = "2026-07-16T00:00:00+00:00"


class ImprovementTriageTest(unittest.TestCase):
    def test_semantic_singleton_requires_confirmed_scoped_authority(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, case = _semantic_store(Path(temporary_dir))
            with self.assertRaisesRegex(ValueError, "project-confirmed authority"):
                _create_semantic_finding(store, case.case_id)
            _confirm_authority(store)
            finding = _create_semantic_finding(store, case.case_id)
            self.assertEqual(finding.status, FindingStatus.EVAL_TARGET_REQUIRED)
            self.assertEqual(finding.business_scopes, ["realized_revenue"])
            self.assertEqual(len(finding.authority_decision_ids), 1)

    def test_eval_target_lifecycle_freezes_hash_and_preserves_content(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, case = _semantic_store(Path(temporary_dir))
            _confirm_authority(store)
            finding = _create_semantic_finding(store, case.case_id)
            target = _create_target(store, finding.finding_id)
            self.assertEqual(target.status, EvalTargetStatus.DRAFT)
            target = submit_eval_target_for_review(
                store=store,
                eval_target_id=target.eval_target_id,
            )
            target = approve_eval_target(
                store=store,
                eval_target_id=target.eval_target_id,
                reviewer_id="mvp-business-reviewer",
            )
            self.assertEqual(target.reviewed_by, "mvp-business-reviewer")
            target = freeze_eval_target(store=store, eval_target_id=target.eval_target_id)
            self.assertEqual(target.status, EvalTargetStatus.FROZEN)
            self.assertRegex(target.frozen_sha256 or "", r"^sha256:[0-9a-f]{64}$")
            with self.assertRaisesRegex(ImmutableRecordError, "cannot change"):
                store.replace_eval_target(
                    replace(target, question="Changed after freeze"),
                    expected_status=EvalTargetStatus.FROZEN,
                )

    def test_revoked_business_authority_blocks_freeze(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, case = _semantic_store(Path(temporary_dir))
            confirmation = _confirm_authority(store)
            finding = _create_semantic_finding(store, case.case_id)
            target = _create_target(store, finding.finding_id)
            target = submit_eval_target_for_review(
                store=store,
                eval_target_id=target.eval_target_id,
            )
            target = approve_eval_target(
                store=store,
                eval_target_id=target.eval_target_id,
                reviewer_id="reviewer",
            )
            record_authority_decision(
                store=store,
                feedback_id=FEEDBACK_ID,
                decision=AuthorityDecisionType.REVOKE,
                context_ids=[],
                scopes=[],
                decided_by="project-owner",
                reason="Actor changed role.",
                supersedes_authority_id=confirmation.authority_id,
            )
            with self.assertRaisesRegex(ValueError, "revoked or is missing"):
                freeze_eval_target(store=store, eval_target_id=target.eval_target_id)

    def test_unverified_semantic_cluster_waits_for_business_truth(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store = ImprovementStore(Path(temporary_dir) / "registry")
            first = _runtime_case("7", FailurePhase.EVAL_ASSERTION)
            second = _runtime_case("8", FailurePhase.EVAL_ASSERTION)
            store.create_case(first)
            store.create_case(second)
            finding = create_grouped_finding(
                store=store,
                context_id="data_agent_mvp",
                grouping_mode=GroupingMode.CLUSTER,
                case_ids=[first.case_id, second.case_id],
                root_cause_candidate=RootCauseCandidate.BUSINESS_SEMANTIC_GAP,
            )
            self.assertEqual(finding.status, FindingStatus.WAITING_FOR_BUSINESS_TRUTH)
            with self.assertRaisesRegex(ValueError, "not EVAL_TARGET_REQUIRED"):
                _create_target(store, finding.finding_id)

    def test_group_suggestions_are_deterministic_and_separate_triage_quality(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store = ImprovementStore(Path(temporary_dir) / "registry")
            first = _runtime_case("9", FailurePhase.WREN_DRY_RUN)
            second = _runtime_case("a", FailurePhase.WREN_DRY_RUN)
            triage = replace(
                _runtime_case("b", FailurePhase.EVAL_ASSERTION),
                signals=[Signal("EVAL_NEEDS_TRIAGE", "Benchmark needs triage")],
            )
            for case in (first, second, triage):
                store.create_case(case)
            suggestions = suggest_groups(store=store)
            self.assertEqual(len(suggestions), 1)
            self.assertEqual(suggestions[0]["case_ids"], sorted([first.case_id, second.case_id]))
            self.assertEqual(
                suggestions[0]["root_cause_candidate"],
                RootCauseCandidate.WREN_RUNTIME_FAILURE.value,
            )

    def test_replacement_creates_new_version_and_supersedes_old_target(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, case = _semantic_store(Path(temporary_dir))
            _confirm_authority(store)
            finding = _create_semantic_finding(store, case.case_id)
            first = _create_target(store, finding.finding_id)
            second = create_eval_target(
                store=store,
                finding_id=finding.finding_id,
                question="What is revised realized revenue?",
                result_contract=ResultContract(expected_value=721.8, numeric_tolerance=0.001),
                semantic_constraints=SemanticConstraints(required_units=["CNY"]),
                supersedes_eval_target_id=first.eval_target_id,
            )
            self.assertEqual(second.version, 2)
            self.assertEqual(
                store.get_eval_target(first.eval_target_id).status,
                EvalTargetStatus.SUPERSEDED,
            )

    def test_finding_dismissal_records_separate_review_action(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store = ImprovementStore(Path(temporary_dir) / "registry")
            first = _runtime_case("e", FailurePhase.WREN_DRY_RUN)
            store.create_case(first)
            finding = create_grouped_finding(
                store=store,
                context_id="data_agent_mvp",
                grouping_mode=GroupingMode.SINGLETON,
                case_ids=[first.case_id],
                root_cause_candidate=RootCauseCandidate.WREN_RUNTIME_FAILURE,
            )
            self.assertEqual(suggest_groups(store=store), [])
            with self.assertRaisesRegex(ValueError, "active findings"):
                create_grouped_finding(
                    store=store,
                    context_id="data_agent_mvp",
                    grouping_mode=GroupingMode.SINGLETON,
                    case_ids=[first.case_id],
                    root_cause_candidate=RootCauseCandidate.WREN_RUNTIME_FAILURE,
                )
            dismissed = dismiss_finding(
                store=store,
                finding_id=finding.finding_id,
                reviewer_id="engineer",
                reason="Duplicate infrastructure incident.",
            )
            self.assertEqual(dismissed.status, FindingStatus.DISMISSED)
            self.assertEqual(dismissed.dismissed_by, "engineer")
            self.assertEqual(len(suggest_groups(store=store)), 1)


def _semantic_store(root: Path) -> tuple[ImprovementStore, FailureCase]:
    store = ImprovementStore(root / "registry")
    feedback = FeedbackRecord(
        schema_version=1,
        feedback_id=FEEDBACK_ID,
        trace_id=TRACE_ID,
        feedback_type=FeedbackType.BUSINESS_TRUTH,
        sentiment=Sentiment.NEGATIVE,
        comment="Only completed orders are realized revenue.",
        correction_pair=CorrectionPair(
            observed=ObservedCorrection(
                TRACE_ID,
                sha256_text("999 USD"),
                sha256_text("SELECT SUM(total_amount) FROM orders"),
            ),
            expected=ExpectedCorrection(
                answer="721.80 CNY",
                business_statements=["Only completed orders count as realized revenue."],
            ),
        ),
        provenance=Provenance(
            "user_declared_business_truth",
            "session-1",
            "Completed orders only.",
        ),
        actor=Actor(
            actor_id="business-user",
            actor_type=ActorType.BUSINESS_CONTRIBUTOR,
            authorized_context_ids=["data_agent_mvp"],
            authorized_scopes=["realized_revenue"],
        ),
        created_at=CREATED_AT,
    )
    store.create_feedback(feedback)
    case = FailureCase(
        schema_version=1,
        case_id=deterministic_case_id(f"USER_FEEDBACK:{FEEDBACK_ID}"),
        source_type=SourceType.USER_FEEDBACK,
        source_identity=SourceIdentity(trace_id=TRACE_ID, feedback_id=FEEDBACK_ID),
        context_identity=ContextIdentity(context_id="data_agent_mvp"),
        question="What is realized revenue?",
        observed_status="success",
        failure_phase=FailurePhase.USER_FEEDBACK,
        signals=[Signal("FEEDBACK_BUSINESS_TRUTH", "Completed orders only")],
        evidence_refs=[EvidenceRef("FEEDBACK", FEEDBACK_ID, "feedback/test.json")],
        triage_status=TriageStatus.UNTRIAGED,
        root_cause=None,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )
    store.create_case(case)
    return store, case


def _confirm_authority(store: ImprovementStore):
    return record_authority_decision(
        store=store,
        feedback_id=FEEDBACK_ID,
        decision=AuthorityDecisionType.CONFIRM,
        context_ids=["data_agent_mvp"],
        scopes=["realized_revenue"],
        decided_by="project-owner",
        reason="User owns the realized revenue policy.",
    )


def _create_semantic_finding(store: ImprovementStore, case_id: str):
    return create_grouped_finding(
        store=store,
        context_id="data_agent_mvp",
        grouping_mode=GroupingMode.SINGLETON,
        case_ids=[case_id],
        root_cause_candidate=RootCauseCandidate.BUSINESS_SEMANTIC_GAP,
        business_truth_feedback_ids=[FEEDBACK_ID],
        business_scopes=["realized_revenue"],
    )


def _create_target(store: ImprovementStore, finding_id: str):
    return create_eval_target(
        store=store,
        finding_id=finding_id,
        question="What is realized revenue?",
        result_contract=ResultContract(expected_value=721.8, numeric_tolerance=0.001),
        semantic_constraints=SemanticConstraints(
            required_filters=["orders.status = completed"],
            required_units=["CNY"],
        ),
    )


def _runtime_case(hex_character: str, phase: FailurePhase) -> FailureCase:
    trace_id = "trace_" + hex_character * 32
    identity = f"RUNTIME_TRACE:{trace_id}:{phase.value}"
    return FailureCase(
        schema_version=1,
        case_id=deterministic_case_id(identity),
        source_type=SourceType.RUNTIME_TRACE,
        source_identity=SourceIdentity(trace_id=trace_id),
        context_identity=ContextIdentity(context_id="data_agent_mvp"),
        question="Repeated failure",
        observed_status="failed",
        failure_phase=phase,
        signals=[Signal("TRACE_ERROR", "Repeated failure")],
        evidence_refs=[EvidenceRef("TRACE", trace_id, "data/traces/test.jsonl")],
        triage_status=TriageStatus.UNTRIAGED,
        root_cause=None,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


if __name__ == "__main__":
    unittest.main()
