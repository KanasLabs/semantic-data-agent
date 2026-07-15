from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from data_subagent_context_builder.codex_runtime import CodexCommandResult
from data_subagent_context_builder.starrocks_onboarding import (
    build_starrocks_query_command,
    prepare_starrocks_skill_onboarding,
    validate_starrocks_onboarding_artifacts,
)
from data_subagent_context_builder.wren_cli import CommandResult


class StarRocksOnboardingTest(unittest.TestCase):
    def test_prompt_only_prepares_profile_and_controlled_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "tpch_wren"
            prompt_path = root / "prompt.md"
            wren_runner = FakeWrenRunner()

            with patch.dict("os.environ", {"STARROCKS_TEST_PASSWORD": "not-written"}):
                result = prepare_starrocks_skill_onboarding(
                    project_name="tpch",
                    project_dir=project_dir,
                    project_root=root,
                    wren_home=root / "wren_home",
                    wren_bin=root / "wren.exe",
                    host="127.0.0.1",
                    port=19030,
                    database="tpch_sf001",
                    user="context_builder",
                    password_env="STARROCKS_TEST_PASSWORD",
                    prompt_output_path=prompt_path,
                    wren_runner=wren_runner,
                )

            self.assertTrue(result["ok"])
            self.assertFalse(result["codex"]["executed"])
            self.assertEqual(len(wren_runner.calls), 3)
            profile = yaml.safe_load(Path(result["connection_path"]).read_text(encoding="utf-8"))
            self.assertEqual(profile["datasource"], "doris")
            self.assertEqual(profile["password"], "${STARROCKS_TEST_PASSWORD}")
            project = yaml.safe_load((project_dir / "wren_project.yml").read_text(encoding="utf-8"))
            self.assertEqual(project["name"], "tpch")
            self.assertNotIn("STARROCKS_TEST_PASSWORD=", prompt_path.read_text(encoding="utf-8"))
            prompt = prompt_path.read_text(encoding="utf-8")
            self.assertIn("skills get generate-mdl", prompt)
            self.assertIn("starrocks-query", prompt)
            self.assertIn("<READ_ONLY_SQL>", prompt)
            self.assertIn("discovery_snapshot.json", prompt)

    def test_execute_runs_codex_and_outer_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wren_runner = FakeWrenRunner()
            project_dir = root / "tpch_wren"
            codex_runner = FakeCodexRunner(project_dir)

            result = prepare_starrocks_skill_onboarding(
                project_name="tpch",
                project_dir=project_dir,
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                host="127.0.0.1",
                port=19030,
                database="tpch_sf001",
                user="root",
                allow_empty_password=True,
                smoke_sql="SELECT COUNT(*) FROM orders",
                execute_codex=True,
                wren_runner=wren_runner,
                codex_runner=codex_runner,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["codex"]["executed"])
            self.assertEqual(len(result["codex"]["rounds"]), 1)
            self.assertIn(["context", "validate"], wren_runner.calls)
            self.assertIn(["context", "build"], wren_runner.calls)
            self.assertIn(["dry-run", "--sql", "SELECT COUNT(*) FROM orders"], wren_runner.calls)
            artifacts = result["codex"]["final_validation"]["onboarding_artifacts"]
            self.assertEqual(artifacts["returncode"], 0)
            self.assertIn("1 executed evidence records", artifacts["stdout"])

    def test_artifact_validation_rejects_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = validate_starrocks_onboarding_artifacts(
                discovery_snapshot_path=root / "discovery_snapshot.json",
                schema_manifest_path=root / "schema_manifest.json",
                evidence_path=root / "starrocks_query_evidence.jsonl",
            )

            self.assertEqual(result["returncode"], 1)
            self.assertIn("Missing discovery snapshot", result["stderr"])
            self.assertIn("Missing schema manifest", result["stderr"])
            self.assertIn("Missing query evidence", result["stderr"])

    def test_query_command_contains_policy_not_password(self):
        command = build_starrocks_query_command(
            project_root=Path("C:/repo"),
            host="localhost",
            port=19030,
            database="tpch",
            user="builder",
            password_env="STARROCKS_PASSWORD",
            allow_empty_password=False,
            allowed_catalogs=("default_catalog",),
            allowed_databases=("tpch",),
            max_query_rows=50,
            query_timeout_seconds=10,
            evidence_path=Path("C:/repo/evidence.jsonl"),
        )
        self.assertIn("--password-env 'STARROCKS_PASSWORD'", command)
        self.assertIn("--allowed-database 'tpch'", command)
        self.assertIn("--max-rows 50", command)
        self.assertNotIn("password123", command)

    def test_accepts_timeout_candidate_only_after_outer_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "tpch_wren"
            result = prepare_starrocks_skill_onboarding(
                project_name="tpch",
                project_dir=project_dir,
                project_root=root,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                host="127.0.0.1",
                port=19030,
                database="tpch_sf001",
                user="root",
                allow_empty_password=True,
                smoke_sql="SELECT COUNT(*) FROM orders",
                execute_codex=True,
                wren_runner=FakeWrenRunner(),
                codex_runner=TimeoutArtifactCodexRunner(project_dir),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["codex"]["completion_status"], "accepted_after_timeout")
            self.assertTrue(result["codex"]["rounds"][0]["accepted_after_timeout"])
            self.assertIsNotNone(result["codex"]["final_validation"])


class FakeWrenRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args: list[str]) -> CommandResult:
        self.calls.append(args)
        if args[:2] == ["context", "init"]:
            project_dir = Path(args[args.index("--path") + 1])
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "wren_project.yml").write_text(
                "schema_version: 5\nname: my_project\nversion: '0.1'\n",
                encoding="utf-8",
            )
        return CommandResult(args=args, returncode=0, stdout="OK", stderr="")


class FakeCodexRunner:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir

    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        onboarding = self.project_dir / "onboarding"
        onboarding.mkdir(parents=True, exist_ok=True)
        (onboarding / "discovery_snapshot.json").write_text(
            json.dumps({"tables": ["orders"]}), encoding="utf-8"
        )
        (onboarding / "schema_manifest.json").write_text(
            json.dumps({"tables": [{"name": "orders"}]}), encoding="utf-8"
        )
        (onboarding / "starrocks_query_evidence.jsonl").write_text(
            json.dumps({"status": "executed", "result_sha256": "abc"}) + "\n",
            encoding="utf-8",
        )
        return CodexCommandResult(
            args=["exec", "-"],
            returncode=0,
            stdout="done",
            stderr="",
            last_message_path=str(last_message_path) if last_message_path else None,
        )


class TimeoutArtifactCodexRunner:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir

    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        model_path = self.project_dir / "models" / "orders" / "metadata.yml"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text("name: orders\n", encoding="utf-8")
        onboarding = self.project_dir / "onboarding"
        onboarding.mkdir(parents=True, exist_ok=True)
        (onboarding / "discovery_snapshot.json").write_text("{}", encoding="utf-8")
        (onboarding / "schema_manifest.json").write_text("{}", encoding="utf-8")
        (onboarding / "starrocks_query_evidence.jsonl").write_text(
            json.dumps({"status": "executed", "result_sha256": "abc"}) + "\n",
            encoding="utf-8",
        )
        return CodexCommandResult(
            args=["exec", "-"],
            returncode=124,
            stdout="",
            stderr="timed out",
            last_message_path=str(last_message_path) if last_message_path else None,
        )


if __name__ == "__main__":
    unittest.main()
