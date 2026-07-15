from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from data_subagent.eval_runner import load_eval_cases
from data_subagent_context_builder.smoke_eval import make_smoke_eval


class SmokeEvalGeneratorTest(unittest.TestCase):
    def test_make_smoke_eval_generates_loadable_count_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "sales_wren"
            output_path = root / "sales_smoke.jsonl"
            _write_wren_project(project_dir)

            result = make_smoke_eval(
                wren_project_dir=project_dir,
                output_path=output_path,
                dataset="sales_dataset",
                db_id="sales_db",
                max_cases=2,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["emitted"], 2)
            cases = load_eval_cases(output_path)
            self.assertEqual([case.eval_id for case in cases], ["sales_customers_count", "sales_orders_count"])
            self.assertEqual(cases[0].dataset, "sales_dataset")
            self.assertEqual(cases[0].db_id, "sales_db")
            self.assertEqual(cases[0].expected_sql_contains, ["count", "customers"])
            self.assertEqual(cases[0].expected_row_count, 1)

    def test_make_smoke_eval_can_emit_relationship_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "sales_wren"
            output_path = root / "sales_smoke.jsonl"
            _write_wren_project(project_dir)

            result = make_smoke_eval(
                wren_project_dir=project_dir,
                output_path=output_path,
                max_cases=3,
                include_relationship_case=True,
            )

            self.assertEqual(result["emitted"], 3)
            cases = load_eval_cases(output_path)
            self.assertEqual(cases[-1].eval_id, "sales_orders_customers_relationship_smoke")
            self.assertEqual(cases[-1].question, "How many orders rows have related customers?")
            self.assertIn("count", cases[-1].expected_sql_contains)
            self.assertIn("orders", cases[-1].expected_sql_contains)
            self.assertIn("customers", cases[-1].expected_sql_contains)
            self.assertNotIn("limit", cases[-1].expected_sql_contains)
            self.assertEqual(cases[-1].expected_row_count, 1)


def _write_wren_project(project_dir: Path) -> None:
    (project_dir / "models" / "customers").mkdir(parents=True)
    (project_dir / "models" / "orders").mkdir(parents=True)
    (project_dir / "wren_project.yml").write_text(
        "schema_version: 5\nname: sales\nversion: '0.1'\n",
        encoding="utf-8",
    )
    (project_dir / "models" / "customers" / "metadata.yml").write_text(
        """
name: customers
columns:
- name: customer_id
  type: INT
""".lstrip(),
        encoding="utf-8",
    )
    (project_dir / "models" / "orders" / "metadata.yml").write_text(
        """
name: orders
columns:
- name: order_id
  type: INT
""".lstrip(),
        encoding="utf-8",
    )
    (project_dir / "relationships.yml").write_text(
        """
relationships:
- name: orders_to_customers
  models:
  - orders
  - customers
  join_type: MANY_TO_ONE
  condition: orders.customer_id = customers.customer_id
""".lstrip(),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
