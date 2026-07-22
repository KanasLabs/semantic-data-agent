from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from data_agent_improvement.models import (
    Actor,
    ActorType,
    AuthorityDecisionType,
    CandidateResultStatus,
    ContextIdentity,
    CorrectionPair,
    EvalTargetStatus,
    EvidenceRef,
    ExpectedCorrection,
    FeedbackRecord,
    FeedbackType,
    FailureCase,
    FailurePhase,
    GroupingMode,
    JobStatus,
    JobTargetType,
    ObservedCorrection,
    Provenance,
    ResultContract,
    RootCauseCandidate,
    RoutingEvidence,
    RoutingEvidenceType,
    RoutingProposalStatus,
    SemanticConstraints,
    Sentiment,
    Signal,
    SourceIdentity,
    SourceType,
    TriageStatus,
    deterministic_case_id,
    sha256_text,
)
from data_agent_improvement.si3 import (
    SourceCandidateExecution,
    execute_source_job_development,
    prepare_source_job,
    verify_source_job_integrity,
)
from data_agent_improvement.routing import (
    confirm_routing_proposal,
    create_routing_decision,
    create_routing_proposal,
)
from data_agent_improvement.store import ImprovementStore, RecordNotFoundError
from data_agent_improvement.source_plan import SourceEvaluationCommand
from data_agent_improvement.triage import (
    approve_eval_target,
    create_eval_target,
    create_grouped_finding,
    freeze_eval_target,
    record_authority_decision,
    submit_eval_target_for_review,
)


TRACE_ID = "trace_" + "3" * 32
FEEDBACK_ID = "feedback_" + "4" * 32
CREATED_AT = "2026-07-21T00:00:00+00:00"


class ImprovementSi3Test(unittest.TestCase):
    def test_insufficient_source_proposal_is_persisted_for_more_diagnosis(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id = _frozen_target(Path(temporary_dir))

            proposal = create_routing_proposal(
                store=store,
                eval_target_id=target_id,
                proposed_target_type=JobTargetType.SOURCE_CODE,
                evidence=[
                    RoutingEvidence(
                        RoutingEvidenceType.SOURCE_REPRODUCTION,
                        "source-unit-test",
                        "A source-level test reproduces the observed failure.",
                    )
                ],
                proposed_by="codex-cli",
                rationale="The symptom appears after query generation.",
            )

            self.assertEqual(
                proposal.status,
                RoutingProposalStatus.DIAGNOSIS_REQUIRED,
            )
            self.assertTrue(proposal.validation_errors)
            self.assertEqual(
                store.get_routing_proposal(proposal.routing_proposal_id),
                proposal,
            )
            with self.assertRaisesRegex(ValueError, "READY_FOR_REVIEW"):
                confirm_routing_proposal(
                    store=store,
                    routing_proposal_id=proposal.routing_proposal_id,
                    confirmed_by="engineering-reviewer",
                    rationale="Confirm the proposed source route.",
                )

    def test_confirmed_proposal_binds_source_decision_and_job(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            proposal = _source_routing_proposal(store, target_id)

            decision = confirm_routing_proposal(
                store=store,
                routing_proposal_id=proposal.routing_proposal_id,
                confirmed_by="engineering-reviewer",
                rationale="Reviewed evidence supports SI3.",
            )
            job = prepare_source_job(
                store=store,
                eval_target_id=target_id,
                routing_decision_id=decision.routing_decision_id,
                repository_root=repository,
                allowed_paths=["src/**"],
                evaluation_commands=_evaluation_commands(),
            )

            self.assertEqual(proposal.status, RoutingProposalStatus.READY_FOR_REVIEW)
            self.assertEqual(
                decision.routing_proposal_id,
                proposal.routing_proposal_id,
            )
            self.assertTrue(
                (decision.routing_proposal_sha256 or "").startswith("sha256:")
            )
            self.assertIsNone(verify_source_job_integrity(store=store, job=job))

    def test_unconfirmed_proposal_cannot_prepare_source_job(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            proposal = _source_routing_proposal(store, target_id)

            with self.assertRaisesRegex(ValueError, "routing_decision_id"):
                prepare_source_job(
                    store=store,
                    eval_target_id=target_id,
                    routing_decision_id=proposal.routing_proposal_id,
                    repository_root=repository,
                    allowed_paths=["src/**"],
                    evaluation_commands=_evaluation_commands(),
                )

    def test_modified_confirmed_proposal_rejects_source_job(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            proposal = _source_routing_proposal(store, target_id)
            decision = confirm_routing_proposal(
                store=store,
                routing_proposal_id=proposal.routing_proposal_id,
                confirmed_by="engineering-reviewer",
                rationale="Reviewed evidence supports SI3.",
            )
            proposal_path = (
                store.registry_root
                / "routing_proposals"
                / f"{proposal.routing_proposal_id}.json"
            )
            payload = json.loads(proposal_path.read_text(encoding="utf-8"))
            payload["rationale"] = "tampered rationale"
            proposal_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "content/hash changed"):
                prepare_source_job(
                    store=store,
                    eval_target_id=target_id,
                    routing_decision_id=decision.routing_decision_id,
                    repository_root=repository,
                    allowed_paths=["src/**"],
                    evaluation_commands=_evaluation_commands(),
                )

    def test_prepare_source_job_freezes_git_identity_and_paths(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            routing = _source_routing_decision(store, target_id)

            job = prepare_source_job(
                store=store,
                eval_target_id=target_id,
                routing_decision_id=routing.routing_decision_id,
                repository_root=repository,
                allowed_paths=["src/**", "tests/**"],
                evaluation_commands=_evaluation_commands(),
            )

            self.assertEqual(job.target_type, JobTargetType.SOURCE_CODE)
            self.assertEqual(job.base_candidate_id, _git_text(repository, "rev-parse", "HEAD"))
            self.assertEqual(job.data_identity["snapshot_id"], job.base_candidate_id)
            self.assertTrue(job.data_identity["schema_fingerprint"].startswith("sha256:"))
            self.assertTrue(
                job.data_identity["evaluation_plan_sha256"].startswith("sha256:")
            )
            self.assertEqual(job.routing_decision_id, routing.routing_decision_id)
            self.assertTrue(
                job.data_identity["routing_decision_sha256"].startswith("sha256:")
            )
            self.assertIn("deepseek_apikey.txt", job.forbidden_paths)
            self.assertIsNone(verify_source_job_integrity(store=store, job=job))
            plan_path = (
                store.job_dir(job.job_id) / "control" / "source_evaluation_plan.json"
            )
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["commands"][0]["name"], "unit")
            packaged_routing = json.loads(
                (
                    store.job_dir(job.job_id)
                    / "evidence"
                    / "routing_decision.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                packaged_routing["routing_decision_id"],
                routing.routing_decision_id,
            )
            target_eval = (
                store.job_dir(job.job_id) / "evidence" / "target_eval.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn('"eval_id": "si3_', target_eval)
            self.assertIn('"dataset": "si3_frozen_target"', target_eval)

    def test_semantic_finding_requires_context_correctness_before_si3(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            store, target_id = _frozen_target(root)

            with self.assertRaisesRegex(ValueError, "Context rules or generated SQL"):
                create_routing_decision(
                    store=store,
                    eval_target_id=target_id,
                    target_type=JobTargetType.SOURCE_CODE,
                    evidence=[
                        RoutingEvidence(
                            RoutingEvidenceType.SOURCE_REPRODUCTION,
                            "source-unit-test",
                            "A source-level test reproduces the observed failure.",
                        )
                    ],
                    decided_by="engineering-reviewer",
                    rationale="Attempt to route a semantic finding directly to source.",
                )

    def test_reviewed_source_contract_can_justify_semantic_si3_route(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            store, target_id = _frozen_target(root)

            decision = create_routing_decision(
                store=store,
                eval_target_id=target_id,
                target_type=JobTargetType.SOURCE_CODE,
                evidence=[
                    RoutingEvidence(
                        RoutingEvidenceType.SOURCE_CONTRACT_OWNERSHIP_VERIFIED,
                        "source-contract-review",
                        "The reviewed source API explicitly owns this behavior.",
                    ),
                    RoutingEvidence(
                        RoutingEvidenceType.SOURCE_REPRODUCTION,
                        "source-unit-test",
                        "A source-level test reproduces the observed failure.",
                    ),
                ],
                decided_by="engineering-reviewer",
                rationale="The behavior is source-owned and the defect is reproducible.",
            )

            self.assertEqual(decision.target_type, JobTargetType.SOURCE_CODE)
            self.assertEqual(
                store.get_routing_decision(decision.routing_decision_id),
                decision,
            )

    def test_source_job_rejects_context_routing_decision(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            routing = create_routing_decision(
                store=store,
                eval_target_id=target_id,
                target_type=JobTargetType.WREN_CONTEXT,
                evidence=[
                    RoutingEvidence(
                        RoutingEvidenceType.CONTEXT_RULE_VERIFIED,
                        "context-review",
                        "The reviewer selected the Context candidate path.",
                    )
                ],
                decided_by="engineering-reviewer",
                rationale="This decision explicitly routes to SI2.",
            )

            with self.assertRaisesRegex(ValueError, "SOURCE_CODE RoutingDecision"):
                prepare_source_job(
                    store=store,
                    eval_target_id=target_id,
                    routing_decision_id=routing.routing_decision_id,
                    repository_root=repository,
                    allowed_paths=["src/**"],
                    evaluation_commands=_evaluation_commands(),
                )

    def test_modified_evaluation_plan_invalidates_source_job(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            job = prepare_source_job(
                store=store,
                eval_target_id=target_id,
                routing_decision_id=_source_routing_decision(
                    store,
                    target_id,
                ).routing_decision_id,
                repository_root=repository,
                allowed_paths=["src/**"],
                evaluation_commands=_evaluation_commands(),
            )
            plan_path = (
                store.job_dir(job.job_id) / "control" / "source_evaluation_plan.json"
            )
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["commands"][0]["args"] = [sys.executable, "-c", "raise SystemExit(0)"]
            plan_path.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            error = verify_source_job_integrity(store=store, job=job)

            self.assertIn("hash changed after Job preparation", error or "")

    def test_modified_routing_decision_invalidates_source_job(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            routing = _source_routing_decision(store, target_id)
            job = prepare_source_job(
                store=store,
                eval_target_id=target_id,
                routing_decision_id=routing.routing_decision_id,
                repository_root=repository,
                allowed_paths=["src/**"],
                evaluation_commands=_evaluation_commands(),
            )
            routing_path = (
                store.registry_root
                / "routing_decisions"
                / f"{routing.routing_decision_id}.json"
            )
            payload = json.loads(routing_path.read_text(encoding="utf-8"))
            payload["rationale"] = "Changed after source Job preparation."
            routing_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            error = verify_source_job_integrity(store=store, job=job)

            self.assertIn("content/hash changed", error or "")

    def test_passing_candidate_creates_development_pr_packet(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            job = prepare_source_job(
                store=store,
                eval_target_id=target_id,
                routing_decision_id=_source_routing_decision(
                    store,
                    target_id,
                ).routing_decision_id,
                repository_root=repository,
                allowed_paths=["src/**"],
                evaluation_commands=_evaluation_commands(),
            )
            evaluator = FakeEvaluator(_passing_eval())

            report = execute_source_job_development(
                store=store,
                job_id=job.job_id,
                executor=EditingExecutor("src/app.py", "def value():\n    return 2\n"),
                evaluator=evaluator,
            )

            self.assertEqual(report["candidate_status"], CandidateResultStatus.PASS.value)
            self.assertTrue(report["development_only"])
            self.assertFalse(report["formal_result_recorded"])
            self.assertFalse(report["release_eligible"])
            self.assertEqual(report["changed_paths"], ["src/app.py"])
            self.assertTrue(report["branch_name"].startswith("si3/job_"))
            self.assertEqual(
                report["candidate_evaluation"]["reason"],
                "ACCEPTANCE_PASSED",
            )
            self.assertTrue(Path(report["pr_candidate"]["patch_path"]).is_file())
            patch = Path(report["pr_candidate"]["patch_path"]).read_text(encoding="utf-8")
            self.assertIn("+    return 2", patch)
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.PREPARED)
            self.assertTrue(evaluator.called)
            with self.assertRaises(RecordNotFoundError):
                store.get_job_result(job.job_id)

    def test_forbidden_change_fails_before_outer_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            job = prepare_source_job(
                store=store,
                eval_target_id=target_id,
                routing_decision_id=_source_routing_decision(
                    store,
                    target_id,
                ).routing_decision_id,
                repository_root=repository,
                allowed_paths=["src/**"],
                evaluation_commands=_evaluation_commands(),
            )
            evaluator = FakeEvaluator(_passing_eval())

            report = execute_source_job_development(
                store=store,
                job_id=job.job_id,
                executor=EditingExecutor("README.md", "unsafe edit\n"),
                evaluator=evaluator,
            )

            self.assertEqual(report["candidate_status"], CandidateResultStatus.FAIL.value)
            self.assertIn("outside the allowlist", report["error"])
            self.assertEqual(report["candidate_evaluation"]["reason"], "ASSERTION_FAILED")
            self.assertFalse(evaluator.called)
            self.assertIsNone(report["pr_candidate"])
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.PREPARED)

    def test_infrastructure_block_keeps_patch_but_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repository = _git_repository(root)
            store, target_id = _frozen_target(root)
            job = prepare_source_job(
                store=store,
                eval_target_id=target_id,
                routing_decision_id=_source_routing_decision(
                    store,
                    target_id,
                ).routing_decision_id,
                repository_root=repository,
                allowed_paths=["src/**"],
                evaluation_commands=_evaluation_commands(),
            )

            report = execute_source_job_development(
                store=store,
                job_id=job.job_id,
                executor=EditingExecutor("src/app.py", "def value():\n    return 3\n"),
                evaluator=FakeEvaluator(_blocked_eval()),
            )

            self.assertEqual(
                report["candidate_status"],
                CandidateResultStatus.INCONCLUSIVE.value,
            )
            self.assertEqual(
                report["candidate_evaluation"]["reason"],
                "INFRASTRUCTURE_UNAVAILABLE",
            )
            self.assertIsNotNone(report["pr_candidate"])
            self.assertFalse(report["pr_candidate"]["release_eligible"])
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.PREPARED)


class EditingExecutor:
    def __init__(self, relative_path: str, content: str) -> None:
        self.relative_path = relative_path
        self.content = content

    def execute(self, *, job, instruction, worktree_path, evidence_dir):
        path = worktree_path / self.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.content, encoding="utf-8")
        if "Do not commit" not in instruction:
            raise AssertionError("SI3 instruction omitted the Git-history boundary.")
        return SourceCandidateExecution(ok=True, outcome="completed", summary="edited")


class FakeEvaluator:
    def __init__(self, result):
        self.result = result
        self.called = False

    def evaluate(self, *, job, worktree_path, target_eval_path):
        self.called = True
        if not target_eval_path.is_file():
            raise AssertionError("Frozen target was not packaged.")
        return self.result


def _passing_eval():
    return {
        "ok": True,
        "smoke": {"ok": True},
        "regression": {"ok": True, "suites": []},
    }


def _blocked_eval():
    return {
        "ok": False,
        "smoke": {
            "ok": False,
            "execution": {
                "ok": False,
                "returncode": 1,
                "stderr": "Can't connect to server on '127.0.0.1' (10061)",
            },
        },
        "regression": {"ok": False, "suites": []},
    }


def _evaluation_commands():
    return [
        SourceEvaluationCommand(
            name="unit",
            args=[sys.executable, "-c", "print('ok')"],
        )
    ]


def _source_routing_decision(store: ImprovementStore, target_id: str):
    return create_routing_decision(
        store=store,
        eval_target_id=target_id,
        target_type=JobTargetType.SOURCE_CODE,
        evidence=[
            RoutingEvidence(
                RoutingEvidenceType.CONTEXT_RULE_VERIFIED,
                "context-check",
                "The completed-order rule is already present in Context.",
            ),
            RoutingEvidence(
                RoutingEvidenceType.SOURCE_REPRODUCTION,
                "source-unit-test",
                "A source-only unit test reproduces the post-Context defect.",
            ),
        ],
        decided_by="engineering-reviewer",
        rationale="Context is correct and the failure is reproduced in source code.",
    )


def _source_routing_proposal(store: ImprovementStore, target_id: str):
    return create_routing_proposal(
        store=store,
        eval_target_id=target_id,
        proposed_target_type=JobTargetType.SOURCE_CODE,
        evidence=[
            RoutingEvidence(
                RoutingEvidenceType.CONTEXT_RULE_VERIFIED,
                "context-check",
                "The completed-order rule is already present in Context.",
            ),
            RoutingEvidence(
                RoutingEvidenceType.SOURCE_REPRODUCTION,
                "source-unit-test",
                "A source-only unit test reproduces the post-Context defect.",
            ),
        ],
        proposed_by="codex-cli",
        rationale="Context is correct and source code still reproduces the failure.",
    )


def _git_repository(root: Path) -> Path:
    repository = root / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "si3-test@example.invalid")
    _git(repository, "config", "user.name", "SI3 Test")
    (repository / "src").mkdir()
    (repository / "src" / "app.py").write_text(
        "def value():\n    return 1\n",
        encoding="utf-8",
    )
    (repository / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    return repository.resolve()


def _git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _git_text(repository: Path, *args: str) -> str:
    return _git(repository, *args).stdout.strip()


def _frozen_target(root: Path) -> tuple[ImprovementStore, str]:
    store = ImprovementStore(root / "registry")
    feedback = FeedbackRecord(
        schema_version=1,
        feedback_id=FEEDBACK_ID,
        trace_id=TRACE_ID,
        feedback_type=FeedbackType.BUSINESS_TRUTH,
        sentiment=Sentiment.NEGATIVE,
        comment="Completed orders only.",
        correction_pair=CorrectionPair(
            observed=ObservedCorrection(
                TRACE_ID,
                sha256_text("999 USD"),
                sha256_text("select sum(total_amount) from orders"),
            ),
            expected=ExpectedCorrection(
                answer="721.80 CNY",
                business_statements=["Only completed orders are realized revenue."],
            ),
        ),
        provenance=Provenance(
            "user_declared_business_truth",
            "session",
            "Completed only.",
        ),
        actor=Actor("business-user", actor_type=ActorType.BUSINESS_CONTRIBUTOR),
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
        signals=[Signal("FEEDBACK_BUSINESS_TRUTH", "Completed only")],
        evidence_refs=[EvidenceRef("FEEDBACK", FEEDBACK_ID, "feedback/test.json")],
        triage_status=TriageStatus.UNTRIAGED,
        root_cause=None,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )
    store.create_case(case)
    record_authority_decision(
        store=store,
        feedback_id=FEEDBACK_ID,
        decision=AuthorityDecisionType.CONFIRM,
        context_ids=["data_agent_mvp"],
        scopes=["realized_revenue"],
        decided_by="project-owner",
        reason="Confirmed narrow ownership.",
    )
    finding = create_grouped_finding(
        store=store,
        context_id="data_agent_mvp",
        grouping_mode=GroupingMode.SINGLETON,
        case_ids=[case.case_id],
        root_cause_candidate=RootCauseCandidate.SUMMARIZATION_GAP,
        business_truth_feedback_ids=[FEEDBACK_ID],
        business_scopes=["realized_revenue"],
    )
    target = create_eval_target(
        store=store,
        finding_id=finding.finding_id,
        question="What is realized revenue?",
        result_contract=ResultContract(expected_value=721.8, numeric_tolerance=0.001),
        semantic_constraints=SemanticConstraints(
            required_filters=["orders.status = completed"],
            required_units=["CNY"],
        ),
    )
    target = submit_eval_target_for_review(store=store, eval_target_id=target.eval_target_id)
    target = approve_eval_target(
        store=store,
        eval_target_id=target.eval_target_id,
        reviewer_id="reviewer",
    )
    target = freeze_eval_target(store=store, eval_target_id=target.eval_target_id)
    if target.status != EvalTargetStatus.FROZEN:
        raise AssertionError("Fixture target did not freeze.")
    return store, target.eval_target_id


if __name__ == "__main__":
    unittest.main()
