import json
import tempfile
import unittest
from pathlib import Path

from data_subagent.models import TraceRecord
from data_subagent.trace_store import JsonlTraceStore


class TraceStoreTest(unittest.TestCase):
    def test_append_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            trace = TraceRecord.start("How many orders?")
            trace.status = "success"
            JsonlTraceStore(path).append(trace)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["question"], "How many orders?")


if __name__ == "__main__":
    unittest.main()
