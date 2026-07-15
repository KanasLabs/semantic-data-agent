from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_subagent_context_builder.starrocks_query import (
    QueryRows,
    StarRocksQueryError,
    StarRocksQueryPolicy,
    run_starrocks_query,
    validate_starrocks_readonly_sql,
)


class StarRocksQueryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = StarRocksQueryPolicy(
            allowed_catalogs=("default_catalog",),
            allowed_databases=("analytics",),
            max_rows=2,
            timeout_seconds=5,
        )

    def test_allows_discovery_and_readonly_queries(self):
        cases = {
            "SHOW CATALOGS": "show_catalogs",
            "SHOW DATABASES": "show_databases",
            "SHOW TABLES FROM analytics": "show_tables",
            "SHOW TABLES FROM default_catalog.analytics": "show_tables",
            "DESCRIBE analytics.orders": "describe_table",
            "SHOW CREATE TABLE analytics.orders": "show_metadata",
            "SHOW INDEX FROM analytics.orders": "show_metadata",
            "SHOW PARTITIONS FROM analytics.orders": "show_metadata",
            "SELECT * FROM analytics.orders": "select_query",
            "SELECT * FROM default_catalog.analytics.orders": "select_query",
            "EXPLAIN SELECT * FROM analytics.orders": "explain_query",
        }

        for sql, expected_kind in cases.items():
            with self.subTest(sql=sql):
                validated = validate_starrocks_readonly_sql(sql, self.policy)
                self.assertEqual(validated.statement_kind, expected_kind)

    def test_rejects_mutation_multiple_statements_and_unsafe_show(self):
        cases = [
            "DROP TABLE analytics.orders",
            "SELECT 1; DELETE FROM analytics.orders",
            "SHOW GRANTS",
            "EXPLAIN DELETE FROM analytics.orders",
            "SELECT SLEEP(10)",
        ]

        for sql in cases:
            with self.subTest(sql=sql):
                with self.assertRaises(StarRocksQueryError):
                    validate_starrocks_readonly_sql(sql, self.policy)

    def test_rejects_cross_database_and_information_schema_queries(self):
        cases = [
            "SELECT * FROM finance.orders",
            "SELECT * FROM external_catalog.analytics.orders",
            "SELECT * FROM information_schema.tables",
            "SHOW TABLES FROM finance",
        ]

        for sql in cases:
            with self.subTest(sql=sql):
                with self.assertRaises(StarRocksQueryError):
                    validate_starrocks_readonly_sql(sql, self.policy)

    def test_filters_discovery_rows_truncates_results_and_writes_redacted_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "evidence" / "queries.jsonl"
            executor = FakeExecutor(
                QueryRows(
                    columns=["Catalog"],
                    rows=[("default_catalog",), ("external_catalog",), ("default_catalog",)],
                )
            )

            result = run_starrocks_query(
                sql="SHOW CATALOGS",
                database="analytics",
                policy=self.policy,
                evidence_path=evidence_path,
                executor=executor,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["returned_row_count"], 2)
            self.assertFalse(result["truncated"])
            self.assertEqual(
                result["rows"],
                [{"Catalog": "default_catalog"}, {"Catalog": "default_catalog"}],
            )
            self.assertEqual(executor.calls, [("SHOW CATALOGS", 2, 5)])

            evidence = json.loads(evidence_path.read_text(encoding="utf-8").strip())
            self.assertEqual(evidence["status"], "executed")
            self.assertNotIn("rows", evidence)
            self.assertIn("result_sha256", evidence)
            self.assertNotIn("password", json.dumps(evidence).lower())

    def test_records_rejected_query_without_calling_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "queries.jsonl"
            executor = FakeExecutor(QueryRows(columns=[], rows=[]))

            with self.assertRaises(StarRocksQueryError):
                run_starrocks_query(
                    sql="DELETE FROM analytics.orders",
                    database="analytics",
                    policy=self.policy,
                    evidence_path=evidence_path,
                    executor=executor,
                )

            self.assertEqual(executor.calls, [])
            evidence = json.loads(evidence_path.read_text(encoding="utf-8").strip())
            self.assertEqual(evidence["status"], "rejected")


class FakeExecutor:
    def __init__(self, result: QueryRows) -> None:
        self.result = result
        self.calls: list[tuple[str, int, int]] = []

    def execute(self, sql: str, *, max_rows: int, timeout_seconds: int) -> QueryRows:
        self.calls.append((sql, max_rows, timeout_seconds))
        return self.result


if __name__ == "__main__":
    unittest.main()
