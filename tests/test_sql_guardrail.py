import unittest

from data_subagent.sql_guardrail import SQLGuardrailError, validate_readonly_sql


class SQLGuardrailTest(unittest.TestCase):
    def test_allows_select(self):
        self.assertEqual(validate_readonly_sql("select * from orders;"), "select * from orders")

    def test_rejects_mutation(self):
        with self.assertRaises(SQLGuardrailError):
            validate_readonly_sql("delete from orders")

    def test_rejects_multiple_statements(self):
        with self.assertRaises(SQLGuardrailError):
            validate_readonly_sql("select 1; select 2")


if __name__ == "__main__":
    unittest.main()
