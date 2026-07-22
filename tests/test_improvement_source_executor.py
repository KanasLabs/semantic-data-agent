from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from data_agent_improvement.evaluation import (
    CandidateEvaluationReason,
    CandidateEvaluationStatus,
    classify_candidate_evaluation,
)
from data_agent_improvement.source_executor import (
    CodexCliSourceExecutor,
    CommandSourceCandidateEvaluator,
    SourceEvaluationCommand,
)


class ImprovementSourceExecutorTest(unittest.TestCase):
    def test_completed_nonzero_command_is_assertion_failure(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            target = root / "target.jsonl"
            target.write_text("{}\n", encoding="utf-8")
            evaluator = CommandSourceCandidateEvaluator(
                [
                    SourceEvaluationCommand(
                        name="unit",
                        args=[sys.executable, "-c", "raise SystemExit(1)"],
                    )
                ]
            )

            raw = evaluator.evaluate(
                job=SimpleNamespace(required_suites=["unit"]),
                worktree_path=root,
                target_eval_path=target,
            )
            evaluation = classify_candidate_evaluation(raw)

            self.assertEqual(evaluation.status, CandidateEvaluationStatus.FAIL)
            self.assertEqual(
                evaluation.reason,
                CandidateEvaluationReason.ASSERTION_FAILED,
            )
            execution = raw["regression"]["suites"][0]["execution"]
            self.assertEqual(execution["returncode"], 1)
            self.assertEqual(execution["summary"], {"completed": True})

    def test_missing_required_command_invalidates_eval_target(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            target = root / "target.jsonl"
            target.write_text("{}\n", encoding="utf-8")
            raw = CommandSourceCandidateEvaluator([]).evaluate(
                job=SimpleNamespace(required_suites=["frozen_target"]),
                worktree_path=root,
                target_eval_path=target,
            )

            evaluation = classify_candidate_evaluation(raw)

            self.assertEqual(evaluation.status, CandidateEvaluationStatus.BLOCKED)
            self.assertEqual(
                evaluation.reason,
                CandidateEvaluationReason.EVAL_TARGET_INVALID,
            )

    def test_evaluation_command_rejects_credentials_and_duplicate_names(self):
        with self.assertRaisesRegex(ValueError, "credential variables"):
            SourceEvaluationCommand(
                name="unit",
                args=["python", "-m", "unittest"],
                environment={"API_KEY": "secret"},
            )
        command = SourceEvaluationCommand(name="unit", args=["python", "-V"])
        with self.assertRaisesRegex(ValueError, "must be unique"):
            CommandSourceCandidateEvaluator([command, command])
        with self.assertRaisesRegex(ValueError, "JSON array"):
            SourceEvaluationCommand.from_dict({"name": "unit", "args": "python -V"})

    def test_codex_adapter_reads_structured_completion(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            worktree = root / "worktree"
            evidence = root / "job" / "evidence"
            worktree.mkdir()
            evidence.mkdir(parents=True)
            runner = StructuredRunner("completed")
            executor = CodexCliSourceExecutor(
                host_session_development=True,
                runner_factory=lambda candidate, schema: runner,
            )

            result = executor.execute(
                job=SimpleNamespace(timeout_seconds=60),
                instruction="bounded source task",
                worktree_path=worktree,
                evidence_dir=evidence,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.outcome, "completed")
            self.assertEqual(result.summary, "Applied one bounded edit.")
            self.assertIn("bounded source task", runner.prompt)


class StructuredRunner:
    def __init__(self, status: str) -> None:
        self.status = status
        self.prompt = ""

    def run(self, prompt: str, *, last_message_path: Path):
        self.prompt = prompt
        last_message_path.write_text(
            json.dumps(
                {
                    "status": self.status,
                    "summary": "Applied one bounded edit.",
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(ok=True, stderr="", stdout="")


if __name__ == "__main__":
    unittest.main()
