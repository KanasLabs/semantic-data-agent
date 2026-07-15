from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "setup_starrocks_tpch.py"
SPEC = importlib.util.spec_from_file_location("setup_starrocks_tpch", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SetupStarRocksTpchTest(unittest.TestCase):
    def test_defines_complete_tpch_schema(self):
        self.assertEqual(
            [spec.name for spec in MODULE.TABLE_SPECS],
            ["region", "nation", "supplier", "customer", "part", "partsupp", "orders", "lineitem"],
        )

    def test_create_table_sql_uses_single_replica_duplicate_key_table(self):
        orders = next(spec for spec in MODULE.TABLE_SPECS if spec.name == "orders")
        sql = MODULE.create_table_sql(orders)
        self.assertIn("DUPLICATE KEY(`o_orderkey`)", sql)
        self.assertIn('"replication_num" = "1"', sql)
        self.assertIn("DISTRIBUTED BY HASH(`o_orderkey`) BUCKETS 1", sql)

    def test_rejects_unsafe_database_identifier(self):
        with self.assertRaises(ValueError):
            MODULE.validate_identifier("tpch; DROP DATABASE tpch")


if __name__ == "__main__":
    unittest.main()
