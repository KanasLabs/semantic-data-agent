from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from data_subagent_context_builder.semantic_diff import generate_semantic_diff


class SemanticDiffTest(unittest.TestCase):
    def test_reports_domain_level_wren_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base"
            candidate = root / "candidate"
            _write_project(base, currency_description="Gross order amount.")
            _write_project(candidate, currency_description="Gross order amount in CNY.")
            (candidate / "knowledge" / "rules" / "revenue.md").write_text(
                "Only completed orders are realized revenue.\n",
                encoding="utf-8",
            )
            (candidate / "relationships.yml").write_text(
                "relationships:\n- name: orders_to_customers\n  models: [orders, customers]\n  join_type: MANY_TO_ONE\n  condition: orders.customer_id = customers.customer_id\n",
                encoding="utf-8",
            )

            diff = generate_semantic_diff(
                revision_id="revision_1",
                base_candidate_id="candidate_1",
                candidate_id="candidate_2",
                base_project_dir=base,
                candidate_project_dir=candidate,
                assumptions=["Currency was supplied by the user."],
            )

            self.assertEqual(len(diff.fields), 1)
            self.assertEqual(diff.fields[0]["model"], "orders")
            self.assertEqual(diff.fields[0]["field"], "total_amount")
            self.assertEqual(diff.fields[0]["change"], "changed")
            self.assertEqual(diff.rules[0]["path"], "revenue.md")
            self.assertEqual(diff.rules[0]["change"], "added")
            self.assertEqual(diff.relationships[0]["change"], "added")
            self.assertEqual(diff.assumptions, ["Currency was supplied by the user."])


def _write_project(project_dir: Path, *, currency_description: str) -> None:
    model_path = project_dir / "models" / "orders" / "metadata.yml"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(
        "name: orders\n"
        "columns:\n"
        "- name: total_amount\n"
        "  type: DECIMAL\n"
        "  properties:\n"
        f"    description: {currency_description}\n",
        encoding="utf-8",
    )
    rules_dir = project_dir / "knowledge" / "rules"
    rules_dir.mkdir(parents=True)
    (project_dir / "relationships.yml").write_text("relationships: []\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
