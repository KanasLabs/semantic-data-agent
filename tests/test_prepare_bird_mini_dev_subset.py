import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from data_subagent.eval_runner import load_eval_cases


class PrepareBirdMiniDevSubsetTest(unittest.TestCase):
    def test_convert_select_only_records(self):
        module = _load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "mini_dev.json"
            output = root / "bird_subset.jsonl"
            source.write_text(
                json.dumps(
                    [
                        {
                            "db_id": "business_db",
                            "question": "How many orders are there?",
                            "evidence": "Use the orders table.",
                            "SQL": "SELECT COUNT(*) FROM orders",
                        },
                        {
                            "db_id": "business_db",
                            "question": "Delete old orders",
                            "SQL": "DELETE FROM orders",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            records = module._load_records(source)
            self.assertEqual(len(records), 2)
            self.assertTrue(module._is_readonly_sql(records[0]["SQL"]))
            self.assertFalse(module._is_readonly_sql(records[1]["SQL"]))

            with output.open("w", encoding="utf-8") as file:
                emitted = 0
                for index, record in enumerate(records, start=1):
                    if not module._is_readonly_sql(record["SQL"]):
                        continue
                    file.write(
                        json.dumps(
                            {
                                "eval_id": module._eval_id(record["db_id"], index),
                                "dataset": "bird_mini_dev",
                                "db_id": record["db_id"],
                                "question": record["question"],
                                "evidence": record["evidence"],
                                "gold_sql": record["SQL"],
                                "expected_sql_contains": module._expected_sql_fragments(record["SQL"]),
                            }
                        )
                        + "\n"
                    )
                    emitted += 1

            self.assertEqual(emitted, 1)
            cases = load_eval_cases(output)
            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0].dataset, "bird_mini_dev")
            self.assertEqual(cases[0].db_id, "business_db")
            self.assertEqual(cases[0].expected_sql_contains, ["select", "count"])


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "prepare_bird_mini_dev_subset.py"
    spec = importlib.util.spec_from_file_location("prepare_bird_mini_dev_subset", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
