from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from data_subagent_context_builder.codex_runtime import CodexCommandResult
from data_subagent_context_builder.skill_onboarding import prepare_sqlite_skill_onboarding
from data_subagent_context_builder.wren_cli import CommandResult


class SkillOnboardingTest(unittest.TestCase):
    def test_prepare_sqlite_skill_onboarding_writes_manifest_prompt_and_not_mdl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "sales.sqlite"
            project_dir = root / "sales_wren"
            prompt_path = root / "prompt.md"
            _create_sqlite_fixture(sqlite_path)
            wren_runner = FakeWrenRunner()

            result = prepare_sqlite_skill_onboarding(
                sqlite_path=sqlite_path,
                project_name="sales",
                project_dir=project_dir,
                duckdb_path=root / "sales.duckdb",
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                project_root=root,
                smoke_sql="select count(*) as order_count from orders",
                prompt_output_path=prompt_path,
                wren_runner=wren_runner,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["mode"], "skill")
            self.assertEqual(result["models"], ["customers", "orders"])
            self.assertEqual(
                wren_runner.calls,
                [["context", "init", "--path", str(project_dir.resolve()), "--empty"]],
            )
            self.assertTrue((root / "sales.duckdb").exists())
            self.assertTrue(prompt_path.exists())
            self.assertFalse((project_dir / "models" / "orders" / "metadata.yml").exists())

            manifest_path = Path(result["schema_manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["runtime"]["type"], "duckdb")
            orders = next(table for table in manifest["tables"] if table["name"] == "orders")
            amount = next(column for column in orders["columns"] if column["name"] == "amount")
            self.assertEqual(amount["normalized_type"], "FLOAT")
            self.assertIn("generate-mdl skill", manifest["notes"][0])

            prompt = prompt_path.read_text(encoding="utf-8")
            self.assertIn("skills get generate-mdl", prompt)
            self.assertIn(str(manifest_path), prompt)

    def test_prepare_sqlite_skill_onboarding_executes_codex_only_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "sales.sqlite"
            _create_sqlite_fixture(sqlite_path)
            codex_runner = FakeCodexRunner()

            result = prepare_sqlite_skill_onboarding(
                sqlite_path=sqlite_path,
                project_name="sales",
                project_dir=root / "sales_wren",
                duckdb_path=root / "sales.duckdb",
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                project_root=root,
                execute_codex=True,
                codex_last_message_path=root / "last.txt",
                wren_runner=FakeWrenRunner(),
                codex_runner=codex_runner,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["codex"]["executed"])
            self.assertIn("generate-mdl", codex_runner.prompt)
            self.assertEqual(codex_runner.last_message_path, root / "last.txt")
            self.assertEqual(len(result["codex"]["rounds"]), 1)
            self.assertIn("final_validation", result["codex"])

    def test_prepare_sqlite_skill_onboarding_repairs_after_outer_validation_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "sales.sqlite"
            _create_sqlite_fixture(sqlite_path)
            wren_runner = RepairWrenRunner()
            codex_runner = FakeCodexRunner()
            report_path = root / "reports" / "sales_onboarding.md"

            result = prepare_sqlite_skill_onboarding(
                sqlite_path=sqlite_path,
                project_name="sales",
                project_dir=root / "sales_wren",
                duckdb_path=root / "sales.duckdb",
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                project_root=root,
                smoke_sql="select count(*) as order_count from orders",
                execute_codex=True,
                max_repair_rounds=1,
                report_path=report_path,
                wren_runner=wren_runner,
                codex_runner=codex_runner,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(len(result["codex"]["rounds"]), 2)
            self.assertEqual(result["codex"]["repair_rounds_used"], 1)
            self.assertIn("Outer Wren validation result", codex_runner.prompts[1])
            self.assertTrue((root / "sales_wren" / "onboarding" / "prompts" / "round_1.md").exists())
            self.assertTrue((root / "sales_wren" / "onboarding" / "validation" / "round_0.json").exists())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("Codex Execution", report)
            self.assertIn("Final Outer Validation", report)


class FakeWrenRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args: list[str]) -> CommandResult:
        self.calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="OK", stderr="")


class RepairWrenRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.validation_round = 0

    def run(self, args: list[str]) -> CommandResult:
        self.calls.append(args)
        if args == ["context", "init", "--path", str(args[-1])]:
            return CommandResult(args=args, returncode=0, stdout="OK", stderr="")
        if args == ["context", "validate"] and self.validation_round == 0:
            return CommandResult(args=args, returncode=1, stdout="", stderr="missing model metadata")
        if args[0:2] == ["dry-run", "--sql"]:
            self.validation_round += 1
        return CommandResult(args=args, returncode=0, stdout="OK", stderr="")


class FakeCodexRunner:
    def __init__(self) -> None:
        self.prompt = ""
        self.prompts: list[str] = []
        self.last_message_path: Path | None = None

    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        self.prompt = prompt
        self.prompts.append(prompt)
        self.last_message_path = last_message_path
        return CodexCommandResult(
            args=["exec", "-"],
            returncode=0,
            stdout="done",
            stderr="",
            last_message_path=str(last_message_path) if last_message_path else None,
        )


def _create_sqlite_fixture(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                amount REAL,
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
            );
            INSERT INTO customers VALUES (1, 'Ada');
            INSERT INTO orders VALUES (10, 1, 12.5);
            """
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()
