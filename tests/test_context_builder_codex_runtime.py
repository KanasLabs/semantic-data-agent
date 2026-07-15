from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data_subagent_context_builder.codex_runtime import (
    CodexCliRunner,
    CodexCommandResult,
    build_codex_enrichment_prompt,
    build_codex_generate_mdl_prompt,
    prepare_codex_enrichment,
)


class CodexRuntimeTest(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows batch shim test")
    def test_cli_runner_captures_file_backed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shim = root / "fake_codex.cmd"
            shim.write_text(
                "@echo off\r\nmore > nul\r\necho fake stdout\r\necho fake stderr 1>&2\r\nexit /b 0\r\n",
                encoding="utf-8",
            )
            runner = CodexCliRunner(codex_bin=str(shim), project_root=root, timeout_seconds=5)

            result = runner.run("test prompt")

            self.assertEqual(result.returncode, 0)
            self.assertIn("fake stdout", result.stdout)
            self.assertIn("fake stderr", result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows process-tree timeout test")
    def test_cli_runner_returns_structured_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shim = root / "slow_codex.cmd"
            shim.write_text(
                "@echo off\r\nmore > nul\r\nping 127.0.0.1 -n 6 > nul\r\n",
                encoding="utf-8",
            )
            runner = CodexCliRunner(codex_bin=str(shim), project_root=root, timeout_seconds=1)

            result = runner.run("test prompt")

            self.assertEqual(result.returncode, 124)
            self.assertIn("timed out after 1 seconds", result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows command resolution test")
    def test_cli_runner_resolves_command_shim_with_which(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shim = root / "resolved_codex.cmd"
            shim.write_text("@echo off\r\nmore > nul\r\necho resolved\r\n", encoding="utf-8")
            runner = CodexCliRunner(codex_bin="codex", project_root=root, timeout_seconds=5)

            with patch("shutil.which", return_value=str(shim)):
                result = runner.run("test prompt")

            self.assertEqual(result.returncode, 0)
            self.assertIn("resolved", result.stdout)

    def test_cli_runner_returns_structured_start_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing-codex-executable"
            runner = CodexCliRunner(codex_bin=str(missing), project_root=root, timeout_seconds=5)

            result = runner.run("test prompt")

            self.assertEqual(result.returncode, 127)
            self.assertIn("Failed to start Codex executable", result.stderr)

    def test_build_prompt_keeps_codex_work_in_context_builder_boundary(self):
        prompt = build_codex_enrichment_prompt(
            project_root=Path("repo").resolve(),
            wren_project_dir=Path("repo/data/wren/demo").resolve(),
            wren_home=Path("repo/data/wren/home").resolve(),
            wren_bin=Path("repo/.venv-wren/Scripts/wren.exe").resolve(),
            smoke_sql="select count(*) from orders",
            extra_instructions="Add model descriptions.",
        )

        self.assertIn("WrenAI Context Builder", prompt)
        self.assertIn("Do not modify the Data Subagent online question-answering runtime", prompt)
        self.assertIn("skills get generate-mdl", prompt)
        self.assertIn("context validate", prompt)
        self.assertIn("context build", prompt)
        self.assertIn("dry-run --sql", prompt)
        self.assertIn("Add model descriptions.", prompt)

    def test_build_generate_mdl_prompt_makes_skill_the_primary_path(self):
        prompt = build_codex_generate_mdl_prompt(
            project_root=Path("repo").resolve(),
            wren_project_dir=Path("repo/data/wren/demo").resolve(),
            wren_home=Path("repo/data/wren/home").resolve(),
            wren_bin=Path("repo/.venv-wren/Scripts/wren.exe").resolve(),
            schema_manifest_path=Path("repo/data/wren/demo/onboarding/schema_manifest.json").resolve(),
            duckdb_path=Path("repo/data/wren/demo.duckdb").resolve(),
            smoke_sql="select count(*) from orders",
            extra_instructions="Prefer conservative relationships.",
        )

        self.assertIn("Follow WrenAI's installed generate-mdl skill", prompt)
        self.assertIn("prefer the Wren skill", prompt)
        self.assertIn("skills get generate-mdl", prompt)
        self.assertIn("Schema manifest seed:", prompt)
        self.assertIn("Use the schema manifest as seed evidence", prompt)
        self.assertIn("Inspect the runtime database directly", prompt)
        self.assertIn("Add relationships only when they are defensible", prompt)
        self.assertIn("Generate or update Wren YAML", prompt)
        self.assertIn("Prefer conservative relationships.", prompt)

    def test_prepare_codex_enrichment_writes_prompt_without_executing_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt_path = root / "codex_prompt.md"

            result = prepare_codex_enrichment(
                project_root=root,
                wren_project_dir=root / "wren_project",
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                smoke_sql=None,
                extra_instructions=None,
                prompt_output_path=prompt_path,
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["executed"])
            self.assertTrue(prompt_path.exists())
            self.assertNotIn("codex_command", result)

    def test_prepare_codex_enrichment_executes_only_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = FakeCodexRunner()

            result = prepare_codex_enrichment(
                project_root=root,
                wren_project_dir=root / "wren_project",
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                smoke_sql="select 1",
                extra_instructions="Improve relationships.",
                execute=True,
                last_message_path=root / "last.txt",
                runner=runner,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["executed"])
            self.assertEqual(runner.last_message_path, root / "last.txt")
            self.assertIn("Improve relationships.", runner.prompt)
            self.assertEqual(result["codex_command"]["returncode"], 0)


class FakeCodexRunner:
    def __init__(self) -> None:
        self.prompt = ""
        self.last_message_path: Path | None = None

    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        self.prompt = prompt
        self.last_message_path = last_message_path
        return CodexCommandResult(
            args=["exec", "-"],
            returncode=0,
            stdout="done",
            stderr="",
            last_message_path=str(last_message_path) if last_message_path else None,
        )


if __name__ == "__main__":
    unittest.main()
