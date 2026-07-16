from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "setup_starrocks_bird.py"
SPEC = importlib.util.spec_from_file_location("setup_starrocks_bird", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SetupStarRocksBirdTest(unittest.TestCase):
    def test_defines_all_debit_card_specializing_tables(self):
        self.assertEqual(
            [spec.name for spec in MODULE.TABLE_SPECS],
            ["customers", "gasstations", "products", "transactions_1k", "yearmonth"],
        )

    def test_yearmonth_ddl_preserves_composite_key(self):
        yearmonth = next(spec for spec in MODULE.TABLE_SPECS if spec.name == "yearmonth")
        sql = MODULE.create_table_sql(yearmonth)
        self.assertIn("DUPLICATE KEY(`Date`, `CustomerID`)", sql)
        self.assertIn("DISTRIBUTED BY HASH(`CustomerID`) BUCKETS 1", sql)
        self.assertIn('"replication_num" = "1"', sql)

    def test_source_validation_rejects_missing_tables(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            connection = sqlite3.connect(Path(temporary_dir) / "empty.sqlite")
            try:
                with self.assertRaisesRegex(ValueError, "missing required tables"):
                    MODULE.verify_source(connection)
            finally:
                connection.close()

    def test_rejects_unsafe_database_identifier(self):
        with self.assertRaises(ValueError):
            MODULE.validate_identifier("bird; DROP DATABASE bird")


if __name__ == "__main__":
    unittest.main()
