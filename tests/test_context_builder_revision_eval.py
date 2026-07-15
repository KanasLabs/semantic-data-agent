from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from data_subagent.eval_runner import load_eval_cases
from data_subagent_context_builder.revision_eval import (
    DataSubagentCliEvalRunner,
    eval_test_coverage,
    run_revision_evals,
)


class RevisionEvalTest(unittest.TestCase):
    def test_cli_eval_runner_uses_candidate_project_and_parses_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = DataSubagentCliEvalRunner(
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                python_bin=root / "python.exe",
            )
            completed = CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps({"total": 1, "passed": 1, "failed": 0}),
                stderr="",
            )

            with patch("subprocess.run", return_value=completed) as run:
                result = runner.run(
                    suite_path=root / "suite.jsonl",
                    suite_name="revision_smoke",
                    candidate_project_dir=root / "candidate",
                    output_dir=root / "runs",
                    report_dir=root / "reports",
                )

            self.assertTrue(result["ok"])
            command = run.call_args.args[0]
            self.assertIn(str((root / "candidate").resolve()), command)
            self.assertIn("data_subagent.cli", command)
            self.assertEqual(result["summary"]["failed"], 0)

    def test_generates_smoke_and_runs_regression_suites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "candidate"
            revision_dir = root / "revision"
            regression_suite = root / "existing_regression.jsonl"
            _write_project(project_dir)
            regression_suite.write_text(
                json.dumps({"eval_id": "existing_count", "question": "Count orders"}) + "\n",
                encoding="utf-8",
            )
            runner = FakeEvalRunner()

            result = run_revision_evals(
                revision_id="revision_1",
                candidate_project_dir=project_dir,
                revision_dir=revision_dir,
                eval_runner=runner,
                regression_suites=[regression_suite],
                smoke_max_cases=2,
            )

            self.assertTrue(result["ok"])
            generated_cases = load_eval_cases(revision_dir / "evals" / "generated_smoke.jsonl")
            self.assertEqual(len(generated_cases), 1)
            self.assertEqual(len(runner.calls), 2)
            self.assertTrue(all(len(call["suite_name"]) <= 64 for call in runner.calls))
            self.assertTrue((revision_dir / "smoke_eval.json").exists())
            self.assertTrue((revision_dir / "regression_eval.json").exists())
            coverage = eval_test_coverage(result)
            self.assertEqual([item["kind"] for item in coverage], ["smoke", "regression"])
            self.assertTrue(all(item["passed"] for item in coverage))

    def test_failed_smoke_fails_revision_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "candidate"
            _write_project(project_dir)

            result = run_revision_evals(
                revision_id="revision_1",
                candidate_project_dir=project_dir,
                revision_dir=root / "revision",
                eval_runner=FakeEvalRunner(fail_first=True),
            )

            self.assertFalse(result["ok"])
            self.assertFalse(result["smoke"]["ok"])


class FakeEvalRunner:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls: list[dict[str, str]] = []

    def run(self, **kwargs):
        self.calls.append({key: str(value) for key, value in kwargs.items()})
        failed = 1 if self.fail_first and len(self.calls) == 1 else 0
        return {
            "ok": failed == 0,
            "returncode": 0,
            "summary": {"total": 1, "passed": 1 - failed, "failed": failed},
        }


def _write_project(project_dir: Path) -> None:
    model_path = project_dir / "models" / "orders" / "metadata.yml"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(
        "name: orders\ncolumns:\n- name: order_id\n  type: BIGINT\n",
        encoding="utf-8",
    )
    (project_dir / "wren_project.yml").write_text(
        "schema_version: 5\nname: sales\nversion: '0.1'\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
