from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_subagent_context_builder.codex_runtime import CodexCommandResult
from data_subagent_context_builder.revision_engine import (
    register_existing_candidate,
    retry_revision_evals,
    resume_revision,
    revise_candidate,
)
from data_subagent_context_builder.review_workflow import answer_review_question
from data_subagent_context_builder.revision_store import (
    CandidateStatus,
    HumanTaskStatus,
    RevisionStatus,
    RevisionStore,
)
from data_subagent_context_builder.revision_starrocks import StarRocksRevisionConfig
from data_subagent_context_builder.wren_cli import CommandResult


class RevisionEngineTest(unittest.TestCase):
    def test_register_existing_candidate_creates_bootstrap_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "starrocks_project"
            _write_wren_project(project_dir)

            result = register_existing_candidate(
                registry_root=root / "registry",
                context_id="data_agent_mvp",
                project_dir=project_dir,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "DRAFT")
            self.assertEqual(result["project_dir"], str(project_dir.resolve()))
            self.assertTrue(Path(result["candidate_record"]).exists())

    def test_prompt_only_copies_base_into_registry_candidate_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_project = root / "base_project"
            _write_wren_project(base_project)
            store = RevisionStore(root / "registry")
            base = store.create_candidate(context_id="sales", project_path=base_project)

            result = revise_candidate(
                registry_root=root / "registry",
                base_candidate_id=base.candidate_id,
                expected_base_version=1,
                user_instruction="total_amount is CNY",
                requested_scope=["orders.total_amount"],
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                store=store,
            )

            candidate_project = Path(result["candidate_project_dir"])
            self.assertTrue(result["ok"])
            self.assertFalse(result["executed"])
            self.assertTrue((candidate_project / "wren_project.yml").exists())
            self.assertTrue((candidate_project / "onboarding" / "schema_manifest.json").exists())
            self.assertFalse((candidate_project / ".wren").exists())
            self.assertFalse((candidate_project / "target").exists())
            self.assertEqual(
                store.get_candidate(result["candidate_id"]).status,
                CandidateStatus.DRAFT,
            )
            self.assertEqual(
                store.get_revision(result["revision_id"]).status,
                RevisionStatus.REVISION_REQUESTED,
            )
            prompt = Path(result["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("skills get generate-mdl", prompt)
            self.assertIn("total_amount is CNY", prompt)
            self.assertIn("Do not self-approve or publish", prompt)
            self.assertIn("Do not connect directly to a database", prompt)

    def test_execute_revises_only_candidate_and_enters_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_root = root / "registry"
            base_project = root / "base_project"
            _write_wren_project(base_project)
            original_model = (base_project / "models" / "orders" / "metadata.yml").read_text(
                encoding="utf-8"
            )
            store = RevisionStore(registry_root)
            base = store.create_candidate(context_id="sales", project_path=base_project)
            codex_runner = EditingCodexRunner(registry_root)
            wren_runner = FakeWrenRunner()

            result = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=base.candidate_id,
                user_instruction="total_amount is CNY",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                smoke_sql="SELECT SUM(total_amount) FROM orders",
                execute_codex=True,
                max_repair_rounds=1,
                run_evals=True,
                store=store,
                wren_runner=wren_runner,
                codex_runner=codex_runner,
                eval_runner=PassingEvalRunner(),
            )

            candidate_project = Path(result["candidate_project_dir"])
            revised_model = (candidate_project / "models" / "orders" / "metadata.yml").read_text(
                encoding="utf-8"
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["revision_status"], "REVIEW_REQUIRED")
            self.assertEqual(result["candidate_status"], "REVIEW_REQUIRED")
            self.assertEqual(
                (base_project / "models" / "orders" / "metadata.yml").read_text(
                    encoding="utf-8"
                ),
                original_model,
            )
            self.assertIn("currency: CNY", revised_model)
            self.assertEqual(
                wren_runner.calls,
                [
                    ["context", "validate"],
                    ["context", "build"],
                    ["dry-run", "--sql", "SELECT SUM(total_amount) FROM orders"],
                ],
            )
            revision_dir = Path(result["revision_dir"])
            self.assertTrue((revision_dir / "prompts" / "round_0.md").exists())
            self.assertTrue((revision_dir / "validation" / "round_0.json").exists())
            self.assertTrue((revision_dir / "semantic_diff.json").exists())
            self.assertTrue((revision_dir / "smoke_eval.json").exists())
            persisted = json.loads(
                (revision_dir / "revision_result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["candidate_status"], "REVIEW_REQUIRED")

    def test_failed_outer_validation_preserves_candidate_for_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_root = root / "registry"
            base_project = root / "base_project"
            _write_wren_project(base_project)
            store = RevisionStore(registry_root)
            base = store.create_candidate(context_id="sales", project_path=base_project)
            codex_runner = EditingCodexRunner(registry_root)

            result = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=base.candidate_id,
                user_instruction="total_amount is CNY",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                execute_codex=True,
                max_repair_rounds=1,
                store=store,
                wren_runner=FailingWrenRunner(),
                codex_runner=codex_runner,
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["revision_status"], "VALIDATION_FAILED")
            self.assertEqual(result["candidate_status"], "VALIDATION_FAILED")
            self.assertTrue(Path(result["candidate_project_dir"]).exists())
            self.assertEqual(len(codex_runner.prompts), 2)
            self.assertIn("Outer Builder validation result", codex_runner.prompts[1])
            self.assertTrue(
                (Path(result["revision_dir"]) / "validation" / "round_1.json").exists()
            )

    def test_stale_base_outcome_cannot_satisfy_new_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_root = root / "registry"
            base_project = root / "base_project"
            _write_wren_project(base_project)
            _write_completed_outcome(base_project)
            store = RevisionStore(registry_root)
            base = store.create_candidate(context_id="sales", project_path=base_project)

            result = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=base.candidate_id,
                user_instruction="total_amount is CNY",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                execute_codex=True,
                max_repair_rounds=0,
                store=store,
                wren_runner=FakeWrenRunner(),
                codex_runner=SilentCodexRunner(),
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["revision_status"], "VALIDATION_FAILED")
            validation = result["codex"]["final_validation"]["revision_outcome"]
            self.assertIn("Missing revision outcome", validation["stderr"])

    def test_failed_smoke_moves_candidate_to_smoke_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_root = root / "registry"
            base_project = root / "base_project"
            _write_wren_project(base_project)
            store = RevisionStore(registry_root)
            base = store.create_candidate(context_id="sales", project_path=base_project)

            result = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=base.candidate_id,
                user_instruction="total_amount is CNY",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                execute_codex=True,
                run_evals=True,
                store=store,
                wren_runner=FakeWrenRunner(),
                codex_runner=EditingCodexRunner(registry_root),
                eval_runner=FailingEvalRunner(),
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["revision_status"], "SMOKE_FAILED")
            self.assertEqual(result["candidate_status"], "SMOKE_FAILED")
            self.assertTrue(Path(result["semantic_diff_path"]).exists())

            retried = retry_revision_evals(
                registry_root=registry_root,
                revision_id=result["revision_id"],
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                store=store,
                wren_runner=FakeWrenRunner(),
                eval_runner=PassingEvalRunner(),
            )
            self.assertTrue(retried["ok"])
            self.assertEqual(retried["revision_status"], "REVIEW_REQUIRED")
            self.assertTrue(Path(retried["review_packet_path"]).exists())

    def test_structured_clarification_creates_persistent_human_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_root = root / "registry"
            base_project = root / "base_project"
            _write_wren_project(base_project)
            store = RevisionStore(registry_root)
            base = store.create_candidate(context_id="sales", project_path=base_project)

            result = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=base.candidate_id,
                user_instruction="make revenue correct",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                execute_codex=True,
                store=store,
                wren_runner=FakeWrenRunner(),
                codex_runner=ClarificationCodexRunner(registry_root),
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["revision_status"], "CLARIFICATION_REQUIRED")
            self.assertEqual(result["candidate_status"], "DRAFT")
            task = store.get_human_task(
                result["revision_id"],
                result["clarification_task_id"],
            )
            self.assertEqual(task.status, HumanTaskStatus.OPEN)
            self.assertIn("statuses", task.questions[0].prompt)
            self.assertTrue((Path(result["revision_dir"]) / "open_questions.json").exists())

    def test_answered_clarification_resumes_same_revision_and_writes_review_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_root = root / "registry"
            base_project = root / "base_project"
            _write_wren_project(base_project)
            store = RevisionStore(registry_root)
            base = store.create_candidate(context_id="sales", project_path=base_project)
            initial = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=base.candidate_id,
                user_instruction="make revenue correct",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                execute_codex=True,
                store=store,
                wren_runner=FakeWrenRunner(),
                codex_runner=ClarificationCodexRunner(registry_root),
            )
            task = store.get_human_task(
                initial["revision_id"],
                initial["clarification_task_id"],
            )
            answer_result = answer_review_question(
                registry_root=registry_root,
                revision_id=initial["revision_id"],
                task_id=task.task_id,
                question_id=task.questions[0].question_id,
                answer="Only completed orders count as realized revenue.",
                store=store,
            )

            resumed = resume_revision(
                registry_root=registry_root,
                revision_id=initial["revision_id"],
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                execute_codex=True,
                store=store,
                wren_runner=FakeWrenRunner(),
                codex_runner=EditingCodexRunner(registry_root),
            )

            self.assertTrue(answer_result["ready_to_resume"])
            self.assertTrue(resumed["ok"])
            self.assertEqual(resumed["revision_id"], initial["revision_id"])
            self.assertEqual(resumed["candidate_id"], initial["candidate_id"])
            self.assertEqual(resumed["revision_status"], "REVIEW_REQUIRED")
            resume_root = Path(resumed["resume_artifact_dir"])
            self.assertIn(
                "Only completed orders count as realized revenue.",
                (resume_root / "prompt.md").read_text(encoding="utf-8"),
            )
            self.assertTrue((resume_root / "prompts" / "round_0.md").exists())
            review_packet = json.loads(
                Path(resumed["review_packet_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(review_packet["status"], "REVIEW_REQUIRED")
            self.assertEqual(len(review_packet["provenance"]), 2)

    def test_revising_review_candidate_marks_previous_revision_changes_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_root = root / "registry"
            base_project = root / "base_project"
            _write_wren_project(base_project)
            store = RevisionStore(registry_root)
            base = store.create_candidate(context_id="sales", project_path=base_project)
            first = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=base.candidate_id,
                user_instruction="total_amount is CNY",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                execute_codex=True,
                store=store,
                wren_runner=FakeWrenRunner(),
                codex_runner=EditingCodexRunner(registry_root),
            )

            second = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=first["candidate_id"],
                user_instruction="Use net amount instead of gross amount.",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                store=store,
            )

            self.assertEqual(
                store.get_revision(first["revision_id"]).status,
                RevisionStatus.CHANGES_REQUESTED,
            )
            self.assertEqual(second["changes_requested_revision_id"], first["revision_id"])

    def test_revision_can_use_and_archive_controlled_starrocks_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_root = root / "registry"
            base_project = root / "base_project"
            _write_wren_project(base_project)
            store = RevisionStore(registry_root)
            base = store.create_candidate(context_id="sales", project_path=base_project)
            codex_runner = InvestigatingCodexRunner(registry_root)

            result = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=base.candidate_id,
                user_instruction="Check whether order identifiers are still unique.",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                execute_codex=True,
                store=store,
                wren_runner=FakeWrenRunner(),
                codex_runner=codex_runner,
                starrocks_config=_starrocks_config(),
            )

            self.assertTrue(result["ok"])
            self.assertTrue(Path(result["starrocks_query_evidence_path"]).exists())
            evidence_validation = result["codex"]["final_validation"][
                "starrocks_query_evidence"
            ]
            self.assertEqual(evidence_validation["returncode"], 0)
            self.assertEqual(evidence_validation["executed_queries"], 1)
            self.assertIn("starrocks-query", codex_runner.prompts[0])
            access_record = json.loads(
                Path(result["starrocks_access_path"]).read_text(encoding="utf-8")
            )
            self.assertFalse(access_record["password_value_persisted"])

    def test_revision_rejects_starrocks_evidence_that_contains_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_root = root / "registry"
            base_project = root / "base_project"
            _write_wren_project(base_project)
            store = RevisionStore(registry_root)
            base = store.create_candidate(context_id="sales", project_path=base_project)

            result = revise_candidate(
                registry_root=registry_root,
                base_candidate_id=base.candidate_id,
                user_instruction="Check current status values.",
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                execute_codex=True,
                max_repair_rounds=0,
                store=store,
                wren_runner=FakeWrenRunner(),
                codex_runner=UnsafeEvidenceCodexRunner(registry_root),
                starrocks_config=_starrocks_config(),
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["revision_status"], "VALIDATION_FAILED")
            evidence_validation = result["codex"]["final_validation"][
                "starrocks_query_evidence"
            ]
            self.assertIn("contains result rows", evidence_validation["stderr"])


class EditingCodexRunner:
    def __init__(self, registry_root: Path) -> None:
        self.registry_root = registry_root
        self.prompts: list[str] = []

    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        self.prompts.append(prompt)
        candidate_projects = list(self.registry_root.glob("candidates/*/wren_project"))
        if len(candidate_projects) != 1:
            raise AssertionError(f"Expected one candidate workspace, found {candidate_projects}")
        model_path = candidate_projects[0] / "models" / "orders" / "metadata.yml"
        content = model_path.read_text(encoding="utf-8")
        if "currency: CNY" not in content:
            model_path.write_text(content + "currency: CNY\n", encoding="utf-8")
        _write_completed_outcome(candidate_projects[0])
        if last_message_path:
            last_message_path.parent.mkdir(parents=True, exist_ok=True)
            last_message_path.write_text("revision complete\n", encoding="utf-8")
        return CodexCommandResult(
            args=["exec", "-"],
            returncode=0,
            stdout="done",
            stderr="",
            last_message_path=str(last_message_path) if last_message_path else None,
        )


class FakeWrenRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args: list[str]) -> CommandResult:
        self.calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="OK", stderr="")


class FailingWrenRunner:
    def run(self, args: list[str]) -> CommandResult:
        if args == ["context", "validate"]:
            return CommandResult(args=args, returncode=1, stdout="", stderr="invalid metadata")
        return CommandResult(args=args, returncode=0, stdout="OK", stderr="")


class PassingEvalRunner:
    def run(self, **kwargs):
        return {
            "ok": True,
            "returncode": 0,
            "summary": {"total": 1, "passed": 1, "failed": 0},
        }


class FailingEvalRunner:
    def run(self, **kwargs):
        return {
            "ok": False,
            "returncode": 0,
            "summary": {"total": 1, "passed": 0, "failed": 1},
        }


class ClarificationCodexRunner:
    def __init__(self, registry_root: Path) -> None:
        self.registry_root = registry_root

    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        candidate_projects = list(self.registry_root.glob("candidates/*/wren_project"))
        if len(candidate_projects) != 1:
            raise AssertionError(f"Expected one candidate workspace, found {candidate_projects}")
        outcome_path = candidate_projects[0] / "onboarding" / "revision_outcome.json"
        outcome_path.parent.mkdir(parents=True, exist_ok=True)
        outcome_path.write_text(
            json.dumps(
                {
                    "status": "clarification_required",
                    "summary": "Revenue policy is ambiguous.",
                    "assumptions": [],
                    "unresolved_questions": ["Which statuses count as realized revenue?"],
                    "clarification_questions": [
                        {
                            "prompt": "Which order statuses count as realized revenue?",
                            "rationale": "The database cannot determine accounting policy.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return CodexCommandResult(
            args=["exec", "-"],
            returncode=0,
            stdout="clarification required",
            stderr="",
            last_message_path=str(last_message_path) if last_message_path else None,
        )


class SilentCodexRunner:
    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        return CodexCommandResult(
            args=["exec", "-"],
            returncode=0,
            stdout="done without outcome",
            stderr="",
            last_message_path=str(last_message_path) if last_message_path else None,
        )


class InvestigatingCodexRunner(EditingCodexRunner):
    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        result = super().run(prompt, last_message_path=last_message_path)
        candidate_project = list(self.registry_root.glob("candidates/*/wren_project"))[0]
        evidence_path = candidate_project / "onboarding" / "revision_query_evidence.jsonl"
        evidence_path.write_text(
            json.dumps(
                {
                    "status": "executed",
                    "sql_sha256": "abc",
                    "result_sha256": "def",
                    "returned_row_count": 1,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return result


class UnsafeEvidenceCodexRunner(EditingCodexRunner):
    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        result = super().run(prompt, last_message_path=last_message_path)
        candidate_project = list(self.registry_root.glob("candidates/*/wren_project"))[0]
        evidence_path = candidate_project / "onboarding" / "revision_query_evidence.jsonl"
        evidence_path.write_text(
            json.dumps({"status": "executed", "rows": [{"status": "completed"}]}) + "\n",
            encoding="utf-8",
        )
        return result


def _write_wren_project(project_dir: Path) -> None:
    model_path = project_dir / "models" / "orders" / "metadata.yml"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(
        "name: orders\ncolumns:\n- name: total_amount\n  type: DECIMAL\n",
        encoding="utf-8",
    )
    (project_dir / "wren_project.yml").write_text(
        "schema_version: 5\nname: sales\nversion: '0.1'\n",
        encoding="utf-8",
    )
    onboarding = project_dir / "onboarding"
    onboarding.mkdir()
    (onboarding / "schema_manifest.json").write_text("{}\n", encoding="utf-8")
    (project_dir / ".wren").mkdir()
    (project_dir / ".wren" / "state").write_text("generated\n", encoding="utf-8")
    (project_dir / "target").mkdir()
    (project_dir / "target" / "mdl.json").write_text("{}\n", encoding="utf-8")


def _write_completed_outcome(candidate_project: Path) -> None:
    outcome_path = candidate_project / "onboarding" / "revision_outcome.json"
    outcome_path.parent.mkdir(parents=True, exist_ok=True)
    outcome_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "summary": "Applied the user-declared currency.",
                "assumptions": ["Currency is based on the user statement."],
                "unresolved_questions": [],
                "clarification_questions": [],
            }
        ),
        encoding="utf-8",
    )


def _starrocks_config() -> StarRocksRevisionConfig:
    return StarRocksRevisionConfig(
        host="127.0.0.1",
        port=19030,
        database="sales",
        user="context_builder",
        allow_empty_password=True,
        allowed_catalogs=("default_catalog",),
        allowed_databases=("sales",),
        max_query_rows=20,
        query_timeout_seconds=5,
    )


if __name__ == "__main__":
    unittest.main()
