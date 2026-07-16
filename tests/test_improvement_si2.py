from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

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
from data_agent_improvement.si2 import (
    CandidateExecution,
    execute_semantic_job,
    prepare_semantic_job,
    verify_job_integrity,
)
from data_agent_improvement.store import ImprovementStore
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


class ImprovementSi2Test(unittest.TestCase):
    def test_prepare_job_packages_minimized_evidence_and_frozen_suite(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            store, target_id, base_snapshot = _frozen_target(root)
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "1" * 32,
                base_snapshot_path=base_snapshot,
                data_identity={"schema_fingerprint": "sha256:" + "2" * 64},
            )
            self.assertEqual(job.status, JobStatus.PREPARED)
            self.assertFalse(job.database_access)
            self.assertFalse(job.network_access)
            self.assertRegex(
                job.data_identity.get("schema_fingerprint") or "",
                r"^sha256:[0-9a-f]{64}$",
            )
            self.assertIsNone(verify_job_integrity(store=store, job=job))
            evidence_dir = store.job_dir(job.job_id) / "evidence"
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

    def test_execution_requires_external_isolation_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            store, target_id, base_snapshot = _frozen_target(Path(temporary_dir))
            job = prepare_semantic_job(
                store=store,
                eval_target_id=target_id,
                base_candidate_id="candidate_" + "3" * 32,
                base_snapshot_path=base_snapshot,
            )
            executor = FakeExecutor()
            with self.assertRaisesRegex(ValueError, "external filesystem/network isolation"):
                execute_semantic_job(
                    store=store,
                    job_id=job.job_id,
                    executor=executor,
                    external_isolation_confirmed=False,
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
                external_isolation_confirmed=True,
            )
            self.assertEqual(result.status, CandidateResultStatus.PASS)
            self.assertEqual(store.get_job(job.job_id).status, JobStatus.REVIEW_REQUIRED)
            self.assertTrue(executor.called)
            self.assertIn("Do not approve, publish, merge, deploy", executor.instruction)

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
                external_isolation_confirmed=True,
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
                external_isolation_confirmed=True,
            )
            self.assertEqual(result.status, CandidateResultStatus.EVAL_TARGET_INVALID)

    def test_codex_environment_excludes_provider_and_database_secrets(self):
        with patch.dict(
            "os.environ",
            {
                "PATH": "tools",
                "USERPROFILE": "user",
                "DEEPSEEK_API_KEY": "secret",
                "CONTEXT_BUILDER_STARROCKS_PASSWORD": "db-secret",
            },
            clear=True,
        ):
            environment = _codex_environment()
        self.assertEqual(environment["PATH"], "tools")
        self.assertNotIn("DEEPSEEK_API_KEY", environment)
        self.assertNotIn("CONTEXT_BUILDER_STARROCKS_PASSWORD", environment)

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


class FakeExecutor:
    def __init__(self) -> None:
        self.called = False
        self.instruction = ""

    def execute(self, *, job, instruction, target_eval_path):
        self.called = True
        self.instruction = instruction
        return CandidateExecution(
            ok=True,
            outcome="completed",
            revision_id="revision_test",
            candidate_id="candidate_test",
            candidate_project_dir=str(target_eval_path.parent / "candidate"),
            evaluation_summary={"ok": True},
        )


def _frozen_target(root: Path) -> tuple[ImprovementStore, str, Path]:
    store = ImprovementStore(root / "registry")
    base_snapshot = root / "base_wren"
    (base_snapshot / "models").mkdir(parents=True)
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
