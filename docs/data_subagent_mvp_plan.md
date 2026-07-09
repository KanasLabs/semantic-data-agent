# Data Subagent MVP 实施计划

日期：2026-07-08

## 1. 当前判断

我们不自己实现 Wren，并且第一版必须使用 WrenAI。这个约束已经确定，不再把 DB-GPT、Vanna、SQLChat、MindsDB/Minds 作为直接依赖或替代路线。

Data Subagent 的职责是把“智能问数”做成一个可被外层 General Agent 调用的业务能力：

```text
ask_data_question(question, user_id, conversation_context, constraints)
  -> 判断问题是否足够明确
  -> 调 Wren 获取语义上下文 / 历史 NL-SQL 记忆
  -> 调 LLM 生成或修复 SQL
  -> 调 Wren dry-plan / dry-run / query
  -> 汇总答案、表格、图表建议
  -> 保存 trace
```

Wren 的职责是语义层、MDL、memory、SQL 转译、dry-run 和查询执行路径。Data Subagent 只通过 adapter 调用它，不复制它的能力。

第一版真实数据源优先使用 Wren quickstart 的 `jaffle_shop`。如果后续发现更适合 text-to-SQL MVP 的开源数据库，也只能作为评估/扩展数据源，不能替代 WrenAI 作为语义与执行底座。

LLM provider 使用 DeepSeek。本地 API key 文件为：

```text
<project-root>\deepseek_apikey.txt
```

该文件只作为本地 secret 使用，不进入 trace、日志或版本化文档内容。

## 2. MVP 不做什么

- 不实现完整外层 General Agent。
- 不自己造 Wren 的 semantic engine、MDL、memory、SQL executor。
- 不把其他开源 text-to-SQL 产品作为本项目运行时依赖；只研究其设计逻辑。
- 不绕过 Wren 直接猜底层数据库结构。
- 不做自动修改 Wren context 的自改进闭环。
- 不做复杂前端。
- 不在第一版做复杂权限系统；只预留 `user_id`、`constraints`、trace 字段。

## 3. 我们要做什么

第一版代码应该只包含这些边界清晰的模块：

```text
src/data_subagent/
  __init__.py
  models.py              # DataAnswer, TraceRecord, WrenContext, SQLAttempt
  agent.py               # 受控 ReAct loop / ask_data_question
  llm.py                 # LLM adapter interface
  llm_deepseek.py        # DeepSeek adapter
  sql_guardrail.py       # 只读 SQL、LIMIT、危险语句等基础检查
  trace_store.py         # JSONL 或 SQLite trace store
  adapters/
    wren_base.py         # WrenAdapter interface
    wren_cli.py          # 调 wren CLI 的真实 adapter
    fake_wren.py         # 仅用于离线单测，不当作 Wren 实现
  cli.py                 # 本地 smoke test 入口
tests/
  test_agent_loop.py
  test_trace_store.py
  test_sql_guardrail.py
docs/
  ...
```

## 4. 受控 ReAct 流程

工具集合固定，不做开放式 tool calling：

1. `get_context`
2. `generate_sql`
3. `dry_plan_sql`
4. `dry_run_sql`
5. `repair_sql`
6. `execute_sql`
7. `summarize_result`
8. `save_trace`

建议最大循环：

- SQL 生成：1 次。
- dry-run 修复：最多 2 次。
- 总执行步数：不超过 10 步。

失败时返回结构化失败，而不是继续无限尝试。

## 5. Wren Adapter 目标接口

第一版 adapter 面向 Data Subagent，而不是暴露全部 Wren 能力：

```python
class WrenAdapter:
    def get_context(self, question: str) -> WrenContext: ...
    def recall_examples(self, question: str, limit: int = 3) -> list[NLSQLExample]: ...
    def dry_plan(self, sql: str) -> DryRunResult: ...
    def dry_run(self, sql: str) -> DryRunResult: ...
    def execute(self, sql: str, limit: int = 100) -> ExecuteResult: ...
```

其中 `WrenCliAdapter` 初步映射：

- `get_context` -> `wren memory fetch -q ... --output json`
- `recall_examples` -> `wren memory recall -q ... --output json`
- `dry_plan` -> `wren dry-plan --sql ...`
- `dry_run` -> `wren dry-run --sql ...`
- `execute` -> `wren query --sql ... --output json --limit ...`

`FakeWrenAdapter` 只用于测试 loop、trace 和错误修复，不宣称替代 Wren。

## 6. Trace 设计

每次调用都落 trace，后续给 eval 和自改进使用：

```json
{
  "trace_id": "trace_xxx",
  "created_at": "2026-07-08T00:00:00Z",
  "question": "...",
  "user_id": null,
  "status": "success | need_clarification | failed",
  "context_used": [],
  "examples_used": [],
  "sql_attempts": [
    {
      "step": "generate_sql | repair_sql",
      "sql": "...",
      "error_feedback": null
    }
  ],
  "dry_plan_results": [],
  "dry_run_results": [],
  "final_sql": "...",
  "row_count": 0,
  "result_preview": [],
  "answer": "...",
  "chart_spec": {},
  "warnings": [],
  "error": null
}
```

MVP 可先用 JSONL，后续如果要查询失败案例、做 eval dashboard，再迁移 SQLite。

## 7. 实施阶段

### Phase 0：调研和设计落盘

目标：确认不自己实现 Wren，只做 adapter + orchestration。输出：

- `docs/data_subagent_mvp_plan.md`
- `docs/wren_and_open_source_feasibility.md`

### Phase 1：离线可测闭环

目标：在没有真实 Wren 环境时跑通受控 loop。

内容：

- 核心类型。
- `FakeWrenAdapter`。
- 规则型或 stub LLM adapter。
- trace JSONL。
- 单测覆盖成功、dry-run 失败后修复、无法修复失败、问题需澄清。

注意：Fake adapter 只用于测试 Data Subagent 的控制流，不是 Wren 实现。

### Phase 2：Wren CLI Adapter

目标：对接真实 WrenAI OSS CLI。

内容：

- `WrenCliAdapter`。
- 解析 `--output json` 结果。
- 捕获 CLI exit code、stdout、stderr。
- 将 Wren dry-run 错误回灌给 LLM。
- 本地 smoke test 使用 Wren quickstart 或业务方准备的 Wren project。
- 第一版 smoke test 默认使用 Wren quickstart 的 `jaffle_shop`。

### Phase 3：LLM Adapter

目标：把 SQL 生成和修复从 stub 替换成 DeepSeek。

内容：

- `LLMAdapter.generate_sql(...)`
- `LLMAdapter.repair_sql(...)`
- `LLMAdapter.summarize_result(...)`
- prompt 模板版本化并进入 trace。
- API key 优先从环境变量读取；本地开发可从 `deepseek_apikey.txt` 读取。

### Phase 3.5：Codex SDK Runtime 边界说明

讨论中提到“可以用 Codex SDK 实现业务的 runtime”，这里需要拆开理解：

- 在线问数业务 runtime：用户问问题时实时执行的链路。它应该是 `Data Subagent + WrenAI + DeepSeek + trace`，不建议让 Codex SDK 直接参与每次线上问数。
- 后台工程/自改进 runtime：消费 trace、失败案例、eval、Wren context、prompt 和代码，生成可审查的候选改动。Codex SDK 更适合做这一层。

因此第一版 MVP 不把 Codex SDK 放进实时问数主链路。我们先把 trace、eval、adapter 和 prompt 版本化做好，给后续 Codex SDK 自改进 runtime 留入口。

### Phase 4：真实业务样例 eval

目标：形成 3-5 个最小 eval case。

内容：

- 每个 case 包含自然语言问题、期望 SQL 特征、期望字段、期望图表类型。
- 回归测试至少验证状态、SQL guardrail、trace 完整性。

## 8. 待确认问题

实现前最好确认这些输入：

1. Wren quickstart 的 `jaffle_shop` 是否足够覆盖第一版演示问题；如果不够，再补一个公开 text-to-SQL 数据库作扩展 eval。
2. `wrenai[memory,main]` 的安装环境是否使用当前 Python，还是单独 venv/conda env。
3. DeepSeek 模型使用哪个具体 endpoint / model name。
4. trace 存放路径是否固定为 `data/traces/data_subagent.jsonl`。
5. 是否需要为 Wren project、DeepSeek、trace 路径提供 `.env` 或 TOML 配置文件。

## 9. 第一版验收标准

- 运行一个自然语言问题后返回 `DataAnswer`。
- 能通过 Wren adapter 获取 context / examples。
- 能生成 SQL，并通过 Wren `dry-plan` / `dry-run`。
- dry-run 失败时最多修复 N 次。
- 成功时调用 Wren query 并返回 rows。
- 失败时返回结构化错误。
- 每次调用都有完整 trace。
- Data Subagent 可被未来外层 General Agent 包成 `ask_data_question` tool。
