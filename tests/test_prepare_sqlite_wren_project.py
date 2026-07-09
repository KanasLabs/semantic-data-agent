import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import duckdb
import yaml


class PrepareSqliteWrenProjectTest(unittest.TestCase):
    def test_convert_sqlite_to_duckdb_and_wren_project_files(self):
        module = _load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "sales.sqlite"
            duckdb_path = root / "sales.duckdb"
            project_dir = root / "sales_wren"
            _create_sqlite_fixture(sqlite_path)

            tables, relationships = module.convert_sqlite_to_duckdb(sqlite_path, duckdb_path)
            self.assertEqual([table.name for table in tables], ["customers", "orders"])
            self.assertEqual(len(relationships), 1)

            rows = duckdb.connect(str(duckdb_path), read_only=True).execute(
                "select count(*) from orders"
            ).fetchone()
            self.assertEqual(rows[0], 2)

            files = module.generate_wren_project_files(
                tables=tables,
                relationships=relationships,
                project_name="sales",
                sqlite_path=sqlite_path,
                duckdb_path=duckdb_path,
            )
            module._write_files(project_dir, files)

            project = yaml.safe_load((project_dir / "wren_project.yml").read_text())
            self.assertEqual(project["data_source"], "duckdb")
            self.assertEqual(project["profile"], "sales")

            orders = yaml.safe_load(
                (project_dir / "models" / "orders" / "metadata.yml").read_text()
            )
            self.assertEqual(orders["table_reference"]["catalog"], "sales")
            self.assertEqual(orders["primary_key"], "order_id")

            rels = yaml.safe_load((project_dir / "relationships.yml").read_text())
            self.assertEqual(rels["relationships"][0]["join_type"], "MANY_TO_ONE")

    def test_write_duckdb_profile(self):
        module = _load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wren_home = root / "home"
            duckdb_path = root / "sales.duckdb"
            module.write_duckdb_profile(wren_home, "sales", duckdb_path)

            profiles = yaml.safe_load((wren_home / "profiles.yml").read_text())
            self.assertEqual(profiles["active"], "sales")
            self.assertEqual(profiles["profiles"]["sales"]["datasource"], "duckdb")
            self.assertEqual(profiles["profiles"]["sales"]["url"], str(root))


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
            INSERT INTO orders VALUES (11, 1, 7.5);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "prepare_sqlite_wren_project.py"
    spec = importlib.util.spec_from_file_location("prepare_sqlite_wren_project", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
