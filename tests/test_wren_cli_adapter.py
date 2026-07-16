from pathlib import Path
import unittest

from data_subagent.adapters.wren_cli import WrenCliAdapter, WrenCommandResult


class RecordingWrenCliAdapter(WrenCliAdapter):
    def __init__(self) -> None:
        super().__init__(Path("wren"), Path("project"), Path("home"))
        self.args: list[str] = []

    def _run(self, args: list[str]) -> WrenCommandResult:
        self.args = args
        return WrenCommandResult(args=args, returncode=0, stdout='{"value": 1}\n', stderr="")


class WrenCliAdapterTest(unittest.TestCase):
    def test_execute_uses_cli_limit_when_sql_has_no_limit(self):
        adapter = RecordingWrenCliAdapter()
        result = adapter.execute("SELECT * FROM orders", limit=25)
        self.assertTrue(result.ok)
        self.assertEqual(adapter.args[-2:], ["--limit", "25"])

    def test_execute_does_not_duplicate_existing_limit(self):
        adapter = RecordingWrenCliAdapter()
        result = adapter.execute("SELECT * FROM orders LIMIT 1", limit=25)
        self.assertTrue(result.ok)
        self.assertNotIn("--limit", adapter.args)
        self.assertIn("LIMIT 1", adapter.args[2])

    def test_execute_clamps_existing_limit(self):
        adapter = RecordingWrenCliAdapter()
        adapter.execute("SELECT * FROM orders LIMIT 1000", limit=25)
        self.assertNotIn("--limit", adapter.args)
        self.assertIn("LIMIT 25", adapter.args[2])


if __name__ == "__main__":
    unittest.main()
