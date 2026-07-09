import unittest

from data_subagent.llm_deepseek import DeepSeekLLMAdapter, LLMResponseParseError
from data_subagent.models import WrenContext


class DeepSeekLLMAdapterTest(unittest.TestCase):
    def test_summarize_result_falls_back_on_malformed_json(self):
        adapter = MalformedSummaryAdapter(api_key="test")
        answer, chart_spec, confidence = adapter.summarize_result(
            question="How many orders are there?",
            sql="select count(*) from orders",
            rows=[{"count_star()": 99}],
        )
        self.assertEqual(answer, "99")
        self.assertEqual(chart_spec, {})
        self.assertEqual(confidence, 0.5)

    def test_generate_sql_retries_after_parse_error(self):
        adapter = RetryThenSuccessAdapter(
            api_key="test",
            max_retries=2,
            retry_initial_delay_seconds=0,
        )

        sql = adapter.generate_sql(
            question="How many orders are there?",
            context=WrenContext(text="models: orders", raw={"models": [{"name": "orders"}]}),
            examples=[],
        )

        self.assertEqual(sql, "select count(*) as order_count from orders")
        self.assertEqual(adapter.calls, 2)

    def test_generate_sql_raises_after_retry_exhaustion(self):
        adapter = AlwaysMalformedAdapter(
            api_key="test",
            max_retries=2,
            retry_initial_delay_seconds=0,
        )

        with self.assertRaises(LLMResponseParseError):
            adapter.generate_sql(
                question="How many orders are there?",
                context=WrenContext(text="models: orders", raw={"models": [{"name": "orders"}]}),
                examples=[],
            )

        self.assertEqual(adapter.calls, 3)


class MalformedSummaryAdapter(DeepSeekLLMAdapter):
    def _json_chat(self, system, user, max_tokens):
        raise LLMResponseParseError("bad json")


class RetryThenSuccessAdapter(DeepSeekLLMAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0

    def _json_chat_once(self, system, user, max_tokens):
        self.calls += 1
        if self.calls == 1:
            raise LLMResponseParseError("empty response")
        return {"sql": "select count(*) as order_count from orders"}


class AlwaysMalformedAdapter(DeepSeekLLMAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0

    def _json_chat_once(self, system, user, max_tokens):
        self.calls += 1
        raise LLMResponseParseError("empty response")


if __name__ == "__main__":
    unittest.main()
