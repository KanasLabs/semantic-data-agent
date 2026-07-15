from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.prepare_starrocks_revision_baseline import prepare_baseline


class PrepareStarRocksRevisionBaselineTest(unittest.TestCase):
    def test_removes_business_semantics_without_changing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            _write_source(source)

            result = prepare_baseline(
                source_project=source,
                output_project=output,
                force=False,
            )

            self.assertTrue(result["ok"])
            source_text = (source / "models" / "orders" / "metadata.yml").read_text(
                encoding="utf-8"
            )
            output_model = yaml.safe_load(
                (output / "models" / "orders" / "metadata.yml").read_text(encoding="utf-8")
            )
            amount = next(
                column for column in output_model["columns"] if column["name"] == "total_amount"
            )
            self.assertIn("CNY", source_text)
            self.assertNotIn("CNY", amount["properties"]["description"])
            self.assertIn(
                "No currency or realized-revenue business policy",
                (output / "knowledge" / "rules" / "general.md").read_text(encoding="utf-8"),
            )


def _write_source(project_dir: Path) -> None:
    model_path = project_dir / "models" / "orders" / "metadata.yml"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(
        "name: orders\n"
        "columns:\n"
        "- name: total_amount\n"
        "  type: DECIMAL\n"
        "  properties:\n"
        "    description: Gross order amount in CNY.\n",
        encoding="utf-8",
    )
    rules = project_dir / "knowledge" / "rules"
    rules.mkdir(parents=True)
    (rules / "general.md").write_text("CNY revenue rule\n", encoding="utf-8")
    (project_dir / "wren_project.yml").write_text(
        "schema_version: 5\nname: starrocks_mvp\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
