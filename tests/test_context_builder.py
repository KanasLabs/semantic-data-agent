from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import yaml

from data_subagent_context_builder.sqlite_onboarding import (
    generate_from_sqlite,
    validate_project,
)
from data_subagent_context_builder.wren_cli import CommandResult


class ContextBuilderTest(unittest.TestCase):
    def test_generate_from_sqlite_writes_project_profile_report_and_runs_wren_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "sales.sqlite"
            project_dir = root / "sales_wren"
            duckdb_path = root / "sales.duckdb"
            wren_home = root / "wren_home"
            report_path = root / "reports" / "sales_onboarding.md"
            _create_sqlite_fixture(sqlite_path)
            runner = FakeRunner()

            result = generate_from_sqlite(
                sqlite_path=sqlite_path,
                project_name="sales",
                project_dir=project_dir,
                duckdb_path=duckdb_path,
                wren_home=wren_home,
                wren_bin=root / "wren.exe",
                smoke_sql="select count(*) as order_count from orders",
                report_path=report_path,
                force=False,
                runner=runner,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["models"], ["customers", "orders"])
            self.assertEqual(result["relationship_count"], 1)
            self.assertTrue((project_dir / "wren_project.yml").exists())
            self.assertTrue((project_dir / "models" / "orders" / "metadata.yml").exists())
            self.assertTrue(duckdb_path.exists())
            self.assertTrue(report_path.exists())

            profile = yaml.safe_load((wren_home / "profiles.yml").read_text(encoding="utf-8"))
            self.assertEqual(profile["active"], "sales")
            self.assertEqual(profile["profiles"]["sales"]["datasource"], "duckdb")

            self.assertEqual(
                runner.calls,
                [
                    ["context", "init", "--path", str(project_dir.resolve()), "--empty"],
                    ["context", "validate"],
                    ["context", "build"],
                    ["dry-run", "--sql", "select count(*) as order_count from orders"],
                ],
            )
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("Wren Context Builder Onboarding Report", report)
            self.assertIn("schema-level MDL", report)

    def test_validate_project_runs_wren_steps_without_generating_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "existing"
            project_dir.mkdir()
            model_path = project_dir / "models" / "orders" / "metadata.yml"
            model_path.parent.mkdir(parents=True)
            model_path.write_text("name: orders\n", encoding="utf-8")
            (project_dir / "relationships.yml").write_text(
                "relationships:\n- name: orders_to_customers\n",
                encoding="utf-8",
            )
            runner = FakeRunner()

            result = validate_project(
                project_name="existing",
                project_dir=project_dir,
                wren_home=root / "wren_home",
                wren_bin=root / "wren.exe",
                smoke_sql=None,
                runner=runner,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(runner.calls, [["context", "validate"], ["context", "build"]])
            self.assertEqual(result["source"], "existing_wren_project")
            self.assertEqual(result["models"], ["orders"])
            self.assertEqual(result["relationship_count"], 1)


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args: list[str]) -> CommandResult:
        self.calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="OK", stderr="")


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
