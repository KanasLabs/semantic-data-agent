from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from data_subagent_context_builder.inspect import inspect_sqlite_schema


class ContextBuilderInspectTest(unittest.TestCase):
    def test_inspect_sqlite_schema_writes_json_and_markdown_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "sales.sqlite"
            json_path = root / "reports" / "schema.json"
            markdown_path = root / "reports" / "schema.md"
            _create_sqlite_fixture(sqlite_path)

            result = inspect_sqlite_schema(
                sqlite_path=sqlite_path,
                project_name="sales",
                json_output_path=json_path,
                report_path=markdown_path,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["project_name"], "sales")
            self.assertEqual(result["table_count"], 2)
            self.assertEqual(result["relationship_count"], 1)
            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertFalse((root / "sales_wren").exists())

            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["tables"][0]["name"], "customers")
            orders = next(table for table in loaded["tables"] if table["name"] == "orders")
            amount = next(column for column in orders["columns"] if column["name"] == "amount")
            self.assertEqual(amount["normalized_type"], "FLOAT")

            report = markdown_path.read_text(encoding="utf-8")
            self.assertIn("SQLite Schema Inspection Report", report)
            self.assertIn("orders_to_customers_0", report)
            self.assertIn("No warnings.", report)

    def test_inspect_sqlite_schema_reports_incomplete_foreign_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "bad_fk.sqlite"
            _create_invalid_fk_fixture(sqlite_path)

            result = inspect_sqlite_schema(sqlite_path=sqlite_path)

            self.assertFalse(result["ok"])
            self.assertEqual(result["relationship_count"], 0)
            self.assertIn("foreign key metadata is incomplete", result["warnings"][0])


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


def _create_invalid_fk_fixture(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE customers (
                CustomerID INTEGER PRIMARY KEY,
                Segment TEXT
            );
            CREATE TABLE yearmonth (
                Date TEXT,
                CustomerID INTEGER,
                Consumption REAL,
                PRIMARY KEY(Date, CustomerID),
                FOREIGN KEY(CustomerID) REFERENCES customers
            );
            INSERT INTO customers VALUES (1, 'A');
            INSERT INTO yearmonth VALUES ('2024-01', 1, 12.5);
            """
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()
