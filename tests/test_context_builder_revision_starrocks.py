from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_subagent_context_builder.revision_starrocks import (
    StarRocksRevisionConfig,
    prepare_starrocks_revision_access,
    validate_revision_query_evidence,
)


class RevisionStarRocksAccessTest(unittest.TestCase):
    def test_prepares_scoped_command_without_password_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            access = prepare_starrocks_revision_access(
                config=StarRocksRevisionConfig(
                    host="127.0.0.1",
                    port=19030,
                    database="sales",
                    user="context_builder",
                    password_env="STARROCKS_TEST_PASSWORD",
                    allowed_databases=("sales",),
                ),
                project_root=root,
                candidate_project_dir=root / "candidate",
                artifact_root=root / "revision",
                require_credentials=False,
            )

            self.assertIn("starrocks-query", access.query_command)
            self.assertIn("--allowed-database 'sales'", access.query_command)
            self.assertIn("--password-env 'STARROCKS_TEST_PASSWORD'", access.query_command)
            record = json.loads(access.access_record_path.read_text(encoding="utf-8"))
            self.assertFalse(record["password_value_persisted"])
            self.assertNotIn("password", record)

    def test_evidence_validation_rejects_rows_and_requires_executed_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.jsonl"
            path.write_text(
                json.dumps({"status": "executed", "rows": [{"secret": "value"}]}) + "\n",
                encoding="utf-8",
            )

            result = validate_revision_query_evidence(path)

            self.assertEqual(result["returncode"], 1)
            self.assertIn("contains result rows", result["stderr"])

    def test_missing_evidence_means_authorized_but_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_revision_query_evidence(Path(tmp) / "missing.jsonl")

            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["status"], "not_used")


if __name__ == "__main__":
    unittest.main()
