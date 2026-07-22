from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from data_agent_improvement.evaluation import (
    CandidateEvaluation,
    CandidateEvaluationReason,
    CandidateEvaluationStatus,
)
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
    SemanticConstraints,
    Sentiment,
    Signal,
    SourceIdentity,
    SourceType,
    TriageStatus,
    deterministic_case_id,
    sha256_text,
)
from data_agent_improvement.isolation import (
    REQUIRED_ISOLATION_PROBES,
    create_isolation_receipt,
)
from data_agent_improvement.codex_executor import _codex_runner_for_mode
from data_agent_improvement.si2 import (
    CandidateExecution,
    execute_semantic_job,
    execute_semantic_job_development,
    prepare_semantic_job as _prepare_semantic_job_impl,
    verify_job_integrity,
)
from data_agent_improvement.routing import (
    confirm_routing_proposal,
    create_routing_decision,
    create_routing_proposal,
)
from data_agent_improvement.store import ImprovementStore, RecordNotFoundError
from data_agent_improvement.triage import (
    approve_eval_target,
    create_eval_target,
    create_grouped_finding,
    freeze_eval_target,
    record_authority_decision,
    submit_eval_target_for_review,
)
from data_subagent_context_builder.codex_runtime import CodexCliRunner, _codex_environment


TRACE_ID = "trace_" + "e" * 32
FEEDBACK_ID = "feedback_" + "f" * 32
CREATED_AT = "2026-07-16T00:00:00+00:00"
ISOLATION_ENVIRONMENT_ID = "si2-test-environment"
ISOLATION_HMAC_KEY = "test-isolation-key-material-32-bytes-minimum"


class ImprovementSi2Test(unittest.TestCase):
    def test_prepare_job_packages_minimized_evidence_and_frozen_suite(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            store, target_id, base_snapshot = _frozen_target(root)
            proposal = create_routing_proposal(
                store=store,
                eval_target_id=target_id,
                proposed_target_type=JobTargetType.WREN_CONTEXT,
                evidence=[
                    RoutingEvidence(
                        RoutingEvidenceType.CONTEXT_RULE_VERIFIED,
                        "context-candidate-route",
                        "The proposed route assigns this finding to the Context layer.",
                    )
                ],
                proposed_by="codex-cli",
                rationale="The semantic gap should first be repaired in Context.",
            )
            routing = confirm_routing_proposal(
                store=store,
                routing_proposal_id=proposal.routing_proposal_id,
                confirmed_by="test-reviewer",
                rationale="Reviewed evidence supports SI2.",
            )
            job = _prepare_semantic_job_impl(
                store=store,
                eval_target_id=target_id,
                routing_decision_id=routing.routing_decision_id,
                base_candidate_id="candidate_" + "1" * 32,
                base_snapshot_path=base_snapshot,
            )
            self.assertEqual(job.status, JobStatus.PREPARED)
            self.assertFalse(job.database_access)
            self.assertFalse(job.network_access)
            self.assertRegex(
                job.data_identity.get("schema_fingerprint") or "",
                r"^sha256:[0-9a-f]{64}$",
            )
            self.assertIsNone(verify_job_integrity(store=store, job=job))
            self.assertIsNotNone(job.routing_decision_id)
            evidence_dir = store.job_dir(job.job_id) / "evidence"
            self.assertTrue((evidence_dir / "routing_decision.json").is_file())
            combined = "\n".join(
                path.read_text(encoding="utf-8")
                for path in evidence_dir.iterdir()
                if path.is_file() and path.name != "manifest.json"
            )
            self.assertNotIn("result_preview", combined)
            target_eval = json.loads(
                (evidence_dir / "target_eval.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual(target_eval["expected_any_values"], [721.8])
            self.assertEqual(target_eval["expected_numeric_tolerance"], 0.001)
            self.assertIn("CNY", target_eval["expected_answer_contains"])

    def test_execution_rejects_receipt_from_another_environment(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "3" * 32,
                base_snapshot_path=base_snapshot,
            )
            executor = FakeExecutor()
            with self.assertRaisesRegex(ValueError, "active execution environment"):
                execute_semantic_job(
                    store=store,
                    job_id=job.job_id,
                    executor=executor,
                    isolation_receipt=_isolation_receipt(job),
                    isolation_hmac_key=ISOLATION_HMAC_KEY,
                    isolation_environment_id="different-environment",
                )
            self.assertFalse(executor.called)
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.PREPARED)

    def test_passing_candidate_stops_at_review_required(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "4" * 32,
                base_snapshot_path=base_snapshot,
            )
            executor = FakeExecutor()
            result = execute_semantic_job(
                store=store,
                job_id=job.job_id,
                executor=executor,
                **_isolation_arguments(job),
            )
            self.assertEqual(result.status, CandidateResultStatus.PASS)
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.REVIEW_REQUIRED)
            self.assertTrue(executor.called)
            self.assertIn("Do not approve, publish, merge, deploy", executor.instruction)
            self.assertEqual(
                store.get_isolation_receipt(job.job_id).job_id,
                job.job_id,
            )
            self.assertEqual(
                result.evaluation_summary["candidate_evaluation"]["status"],
                CandidateEvaluationStatus.PASS.value,
            )

    def test_failed_evaluation_maps_to_failed_job(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "a" * 32,
                base_snapshot_path=base_snapshot,
            )
            result = execute_semantic_job(
                store=store,
                job_id=job.job_id,
                executor=FakeExecutor(evaluation=_failed_evaluation()),
                **_isolation_arguments(job),
            )

            self.assertEqual(result.status, CandidateResultStatus.FAIL)
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.FAILED)

    def test_infrastructure_block_maps_to_inconclusive_job(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "b" * 32,
                base_snapshot_path=base_snapshot,
            )
            result = execute_semantic_job(
                store=store,
                job_id=job.job_id,
                executor=FakeExecutor(evaluation=_infrastructure_evaluation()),
                **_isolation_arguments(job),
            )

            self.assertEqual(result.status, CandidateResultStatus.INCONCLUSIVE)
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.INCONCLUSIVE)

    def test_invalid_target_block_maps_to_eval_target_invalid_job(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "c" * 32,
                base_snapshot_path=base_snapshot,
            )
            result = execute_semantic_job(
                store=store,
                job_id=job.job_id,
                executor=FakeExecutor(evaluation=_invalid_target_evaluation()),
                **_isolation_arguments(job),
            )

            self.assertEqual(result.status, CandidateResultStatus.EVAL_TARGET_INVALID)
            self.assertEqual(
                store.get_job(job.job_id).status,
                JobStatus.EVAL_TARGET_INVALID,
            )

    def test_development_execution_keeps_formal_job_prepared(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "d" * 32,
                base_snapshot_path=base_snapshot,
            )
            executor = FakeExecutor()
            report = execute_semantic_job_development(
                store=store,
                job_id=job.job_id,
                executor=executor,
            )
            self.assertTrue(report["development_only"])
            self.assertFalse(report["formal_result_recorded"])
            self.assertFalse(report["isolation_receipt_used"])
            self.assertFalse(report["release_eligible"])
            self.assertEqual(report["candidate_status"], CandidateResultStatus.PASS.value)
            self.assertEqual(
                report["candidate_evaluation"]["status"],
                CandidateEvaluationStatus.PASS.value,
            )
            self.assertEqual(report["job_status_after"], JobStatus.PREPARED.value)
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.PREPARED)
            self.assertIn("DEVELOPMENT_ONLY", executor.instruction)
            with self.assertRaises(RecordNotFoundError):
                store.get_job_result(job.job_id)

    def test_evidence_tampering_is_inconclusive_and_skips_executor(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "5" * 32,
                base_snapshot_path=base_snapshot,
            )
            evidence = store.job_dir(job.job_id) / "evidence" / "cases.json"
            evidence.write_text("[]\n", encoding="utf-8")
            executor = FakeExecutor()
            result = execute_semantic_job(
                store=store,
                job_id=job.job_id,
                executor=executor,
                **_isolation_arguments(job),
            )
            self.assertEqual(result.status, CandidateResultStatus.INCONCLUSIVE)
            self.assertFalse(executor.called)
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.INCONCLUSIVE)

    def test_frozen_target_drift_is_eval_target_invalid(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "6" * 32,
                base_snapshot_path=base_snapshot,
            )
            target_path = store.registry_root / "eval_targets" / f"{target_id}.json"
            payload = json.loads(target_path.read_text(encoding="utf-8"))
            payload["question"] = "Tampered question"
            target_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            result = execute_semantic_job(
                store=store,
                job_id=job.job_id,
                executor=FakeExecutor(),
                **_isolation_arguments(job),
            )
            self.assertEqual(result.status, CandidateResultStatus.EVAL_TARGET_INVALID)

    def test_execution_rejects_tampered_isolation_receipt(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "7" * 32,
                base_snapshot_path=base_snapshot,
            )
            receipt = replace(_isolation_receipt(job), backend="tampered-backend")
            executor = FakeExecutor()
            with self.assertRaisesRegex(ValueError, "signature is invalid"):
                execute_semantic_job(
                    store=store,
                    job_id=job.job_id,
                    executor=executor,
                    isolation_receipt=receipt,
                    isolation_hmac_key=ISOLATION_HMAC_KEY,
                    isolation_environment_id=ISOLATION_ENVIRONMENT_ID,
                )
            self.assertFalse(executor.called)
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.PREPARED)

    def test_execution_rejects_expired_isolation_receipt(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "8" * 32,
                base_snapshot_path=base_snapshot,
            )
            receipt = create_isolation_receipt(
                job=job,
                environment_id=ISOLATION_ENVIRONMENT_ID,
                issuer="test-external-runner",
                backend="test-process-sandbox",
                hmac_key=ISOLATION_HMAC_KEY,
                probes=_passing_isolation_probes(),
                issued_at=datetime.now(timezone.utc) - timedelta(minutes=20),
                ttl=timedelta(minutes=10),
            )
            with self.assertRaisesRegex(ValueError, "has expired"):
                execute_semantic_job(
                    store=store,
                    job_id=job.job_id,
                    executor=FakeExecutor(),
                    isolation_receipt=receipt,
                    isolation_hmac_key=ISOLATION_HMAC_KEY,
                    isolation_environment_id=ISOLATION_ENVIRONMENT_ID,
                )

    def test_execution_rejects_failed_isolation_probe(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "9" * 32,
                base_snapshot_path=base_snapshot,
            )
            probes = _passing_isolation_probes()
            probes["outside_workspace_read_denied"] = False
            receipt = create_isolation_receipt(
                job=job,
                environment_id=ISOLATION_ENVIRONMENT_ID,
                issuer="test-external-runner",
                backend="test-process-sandbox",
                hmac_key=ISOLATION_HMAC_KEY,
                probes=probes,
            )
            executor = FakeExecutor()
            with self.assertRaisesRegex(ValueError, "outside_workspace_read_denied"):
                execute_semantic_job(
                    store=store,
                    job_id=job.job_id,
                    executor=executor,
                    isolation_receipt=receipt,
                    isolation_hmac_key=ISOLATION_HMAC_KEY,
                    isolation_environment_id=ISOLATION_ENVIRONMENT_ID,
                )
            self.assertFalse(executor.called)

    def test_codex_environment_excludes_provider_and_database_secrets(self):
        with patch.dict(
            "os.environ",
            {
                "PATH": "tools",
                "USERPROFILE": "user",
                "DEEPSEEK_API_KEY": "secret",
                "CONTEXT_BUILDER_STARROCKS_PASSWORD": "db-secret",
                "DATA_AGENT_ISOLATION_HMAC_KEY": "isolation-secret",
                "DATA_AGENT_ISOLATION_ENVIRONMENT_ID": "isolation-environment",
            },
            clear=True,
        ):
            environment = _codex_environment()
        self.assertEqual(environment["PATH"], "tools")
        self.assertNotIn("DEEPSEEK_API_KEY", environment)
        self.assertNotIn("CONTEXT_BUILDER_STARROCKS_PASSWORD", environment)
        self.assertNotIn("DATA_AGENT_ISOLATION_HMAC_KEY", environment)
        self.assertNotIn("DATA_AGENT_ISOLATION_ENVIRONMENT_ID", environment)

    def test_hardened_runner_uses_verified_noninteractive_flags(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            schema = root / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            runner = CodexCliRunner(
                codex_bin=str(root / "missing-codex"),
                project_root=root,
                ephemeral=True,
                ignore_user_config=True,
                approval_policy="never",
                output_schema_path=schema,
                sanitized_environment=True,
            )
            result = runner.run("bounded task")
            self.assertEqual(result.returncode, 127)
            self.assertIn("--ask-for-approval", result.args)
            self.assertIn("--ephemeral", result.args)
            self.assertIn("--ignore-user-config", result.args)
            self.assertIn("--output-schema", result.args)
            self.assertNotIn("--search", result.args)

    def test_host_session_runner_loads_user_config_with_sanitized_environment(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            schema = root / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            runner = _codex_runner_for_mode(
                codex_bin="codex",
                candidate_project_dir=root,
                codex_model=None,
                timeout_seconds=60,
                output_schema_path=schema,
                host_session_development=True,
            )
            self.assertFalse(runner.ignore_user_config)
            self.assertTrue(runner.sanitized_environment)
            self.assertTrue(runner.ephemeral)
            self.assertEqual(runner.approval_policy, "never")


def prepare_semantic_job(*, store, eval_target_id, **kwargs):
    routing = create_routing_decision(
        store=store,
        eval_target_id=eval_target_id,
        target_type=JobTargetType.WREN_CONTEXT,
        evidence=[
            RoutingEvidence(
                RoutingEvidenceType.CONTEXT_RULE_VERIFIED,
                "context-candidate-route",
                "The reviewed route assigns this finding to the Context layer.",
            )
        ],
        decided_by="test-reviewer",
        rationale="The fixture exercises the SI2 candidate path.",
    )
    return _prepare_semantic_job_impl(
        store=store,
        eval_target_id=eval_target_id,
        routing_decision_id=routing.routing_decision_id,
        **kwargs,
    )


class FakeExecutor:
    def __init__(self, evaluation: CandidateEvaluation | None = None) -> None:
        self.called = False
        self.instruction = ""
        self.evaluation = evaluation or _passing_evaluation()

    def execute(self, *, job, instruction, target_eval_path):
        self.called = True
        self.instruction = instruction
        return CandidateExecution(
            ok=self.evaluation.status == CandidateEvaluationStatus.PASS,
            outcome="completed",
            revision_id="revision_test",
            candidate_id="candidate_test",
            candidate_project_dir=str(target_eval_path.parent / "candidate"),
            evaluation_summary={"ok": True},
            evaluation=self.evaluation,
        )


def _passing_evaluation() -> CandidateEvaluation:
    return CandidateEvaluation(
        schema_version=1,
        status=CandidateEvaluationStatus.PASS,
        reason=CandidateEvaluationReason.ACCEPTANCE_PASSED,
        message="Candidate passed all required evaluation suites.",
    )


def _failed_evaluation() -> CandidateEvaluation:
    return CandidateEvaluation(
        schema_version=1,
        status=CandidateEvaluationStatus.FAIL,
        reason=CandidateEvaluationReason.ASSERTION_FAILED,
        message="Candidate failed a frozen assertion.",
    )


def _infrastructure_evaluation() -> CandidateEvaluation:
    return CandidateEvaluation(
        schema_version=1,
        status=CandidateEvaluationStatus.BLOCKED,
        reason=CandidateEvaluationReason.INFRASTRUCTURE_UNAVAILABLE,
        message="Evaluation infrastructure is unavailable.",
    )


def _invalid_target_evaluation() -> CandidateEvaluation:
    return CandidateEvaluation(
        schema_version=1,
        status=CandidateEvaluationStatus.BLOCKED,
        reason=CandidateEvaluationReason.EVAL_TARGET_INVALID,
        message="The frozen EvalTarget is invalid.",
    )


def _isolation_receipt(job):
    return create_isolation_receipt(
        job=job,
        environment_id=ISOLATION_ENVIRONMENT_ID,
        issuer="test-external-runner",
        backend="test-process-sandbox",
        hmac_key=ISOLATION_HMAC_KEY,
        probes=_passing_isolation_probes(),
    )


def _isolation_arguments(job):
    return {
        "isolation_receipt": _isolation_receipt(job),
        "isolation_hmac_key": ISOLATION_HMAC_KEY,
        "isolation_environment_id": ISOLATION_ENVIRONMENT_ID,
    }


def _passing_isolation_probes():
    return {name: True for name in REQUIRED_ISOLATION_PROBES}


def _frozen_target(root: Path) -> tuple[ImprovementStore, str, Path]:
    store = ImprovementStore(root / "registry")
    base_snapshot = root / "base_wren"
    (base_snapshot / "models").mkdir(parents=True)
    (base_snapshot / "models" / "orders.yml").write_text(
        "name: orders\n",
        encoding="utf-8",
    )
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
        actor=Actor(
            "business-user",
            actor_type=ActorType.BUSINESS_CONTRIBUTOR,
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
        root_cause_candidate=RootCauseCandidate.BUSINESS_SEMANTIC_GAP,
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
    self_check = store.get_eval_target(target.eval_target_id)
    if self_check.status != EvalTargetStatus.FROZEN:
        raise AssertionError("Fixture target did not freeze.")
    return store, target.eval_target_id, base_snapshot


if __name__ == "__main__":
    unittest.main()
