import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from data_subagent.eval_runner import load_eval_cases


class SetupBirdMiniDevEvalTest(unittest.TestCase):
    def test_prepare_local_bird_subset_and_find_sqlite(self):
        module = _load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            db_dir = raw / "databases" / "debit_card_specializing"
            db_dir.mkdir(parents=True)
            records_path = raw / "mini_dev_sqlite.json"
            sqlite_path = db_dir / "debit_card_specializing.sqlite"
            output_path = root / "bird_subset.jsonl"
            _create_sqlite_fixture(sqlite_path)
            records_path.write_text(
                json.dumps(
                    [
                        {
                            "db_id": "debit_card_specializing",
                            "question": "How many cards are there?",
                            "evidence": "Use cards.",
                            "SQL": "SELECT COUNT(*) FROM cards",
                        },
                        {
                            "db_id": "debit_card_specializing",
                            "question": "Delete cards",
                            "SQL": "DELETE FROM cards",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            found_records = module.find_records_file(raw)
            records = module.load_records(found_records)
            db_id = module.choose_db_id(records)
            found_db = module.find_sqlite_database(raw, db_id)
            emitted = module.write_eval_subset(records, output_path, db_id=db_id, limit=10)

            self.assertEqual(found_records, records_path)
            self.assertEqual(db_id, "debit_card_specializing")
            self.assertEqual(found_db, sqlite_path)
            self.assertEqual(emitted, 1)
            cases = load_eval_cases(output_path)
            self.assertEqual(cases[0].gold_sql, "SELECT COUNT(*) FROM cards")


def _create_sqlite_fixture(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE cards (
                card_id INTEGER PRIMARY KEY,
                card_type TEXT
            );
            INSERT INTO cards VALUES (1, 'credit');
            """
        )
        conn.commit()
    finally:
        conn.close()


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "setup_bird_mini_dev_eval.py"
    spec = importlib.util.spec_from_file_location("setup_bird_mini_dev_eval", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
