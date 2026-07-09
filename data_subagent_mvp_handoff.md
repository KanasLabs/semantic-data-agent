# Data Subagent MVP Handoff

本文用于把当前架构讨论迁移到新的开发会话。目标不是复述全部讨论，而是给新会话一个足够清晰、可执行的开发上下文。

## 1. 当前目标

先实现一个最小可用的智能问数 Subagent。

暂时不实现完整外层 General Agent，也不急着实现自改进闭环。第一阶段重点是把“问数能力”本身做成一个可被外部调用的模块。

最终形态可以理解为：

```text
General Agent
  -> ask_data_question tool
      -> Data Subagent ReAct Loop
          -> Wren context / semantic engine / dry-run / execute
          -> trace store
```

但当前 MVP 只做中间这一层：

```text
User Question
  -> Data Subagent
      -> Wren Context
      -> SQL generation
      -> Wren dry-run / execute
      -> answer / chart suggestion / trace
```

## 2. 架构判断

之前讨论过四类架构：

- Pipeline + Wren
- Agent / Tool Calling + Wren
- Hybrid
- Controlled Self-Improving Loop

现在的选择是 Hybrid 的一个更清晰版本：

```text
外层 General Agent 负责对话、意图识别、任务分流。
内层 Data Subagent 负责问数任务内部的 ReAct 推理。
Wren 负责语义层、semantic engine、SQL 转译和执行能力。
```

这样做的原因：

- 外层 Agent 不应该变得太胖。
- 问数任务需要多步推理、context 检索、SQL 修复和错误回灌。
- 这些 ReAct 能力更适合封装在 Data Subagent 里，而不是放在外层 Agent。
- 对外仍然可以把 Data Subagent 包装成一个 tool，例如 `ask_data_question(...)`。

## 3. MVP 范围

第一版只做以下能力：

1. 接收自然语言问题。
2. 调用 Wren context 能力，获取相关 model / view / metric / relationship / business rule。
3. 基于 Wren 语义层生成 SQL。
4. 调用 Wren dry-run。
5. 如果 SQL 报错，将错误回灌给 LLM，最多修复 N 次。
6. dry-run 通过后执行查询。
7. 返回自然语言解释、表格结果、图表建议。
8. 保存一次完整 trace，供后续复盘和 eval 使用。

暂时不做：

- 完整外层 General Agent。
- 多业务工具路由。
- 自动修改 Wren context。
- Codex SDK 驱动的自改进闭环。
- 复杂权限系统。
- 复杂前端。

## 4. Data Subagent 内部流程

建议流程：

```text
输入用户问题
  -> 判断问题是否足够明确
  -> 检索 Wren context
  -> 生成 SQL 草稿
  -> Wren dry-run
      -> 成功：继续 execute
      -> 失败：带错误信息修复 SQL，最多重试 N 次
  -> Wren execute
  -> 生成答案解释
  -> 生成 chart suggestion
  -> 记录 trace
  -> 返回结构化结果
```

最小 ReAct loop 可以控制在这些 action 内：

```text
think
  -> get_context
  -> generate_sql
  -> dry_run_sql
  -> repair_sql
  -> execute_sql
  -> summarize_result
```

不要一开始做完全开放的 agent。MVP 应该是“受控 ReAct”，工具集合和最大循环次数都要有限制。

## 5. 对外接口建议

外部调用时，可以先把 Data Subagent 暴露成一个函数或服务接口：

```python
ask_data_question(
    question: str,
    user_id: str | None = None,
    conversation_context: list | None = None,
    constraints: dict | None = None,
) -> DataAnswer
```

返回结构建议：

```json
{
  "status": "success | need_clarification | failed",
  "answer": "自然语言答案",
  "sql": "最终 SQL",
  "rows": [],
  "chart_spec": {},
  "context_used": [],
  "trace_id": "trace_xxx",
  "confidence": 0.0,
  "warnings": [],
  "error": null
}
```

## 6. Trace 设计

每次问数都应该记录 trace。MVP 可以先用本地 JSONL 或 SQLite。

建议至少保存：

```json
{
  "trace_id": "trace_xxx",
  "question": "...",
  "context_used": [],
  "generated_sql_attempts": [],
  "dry_run_results": [],
  "final_sql": "...",
  "execution_result_summary": {},
  "answer": "...",
  "status": "success | failed | need_clarification",
  "error": null,
  "created_at": "..."
}
```

trace 的价值不只是日志，而是后续自改进闭环的输入：

```text
失败案例 -> 聚合 -> 专家标注 -> eval set -> Wren context/rule/prompt/code 改进
```

## 7. Wren 的角色

Wren 不是普通数据库连接器，而是语义层和 semantic engine。

Data Subagent 应该尽量基于 Wren 的 model / view / metric / relationship / business rule 来生成 SQL，而不是绕开 Wren 直接猜真实数据库结构。

Wren 相关工具可以先抽象成 adapter：

```python
class WrenAdapter:
    def get_context(question: str) -> WrenContext: ...
    def dry_run(sql: str) -> DryRunResult: ...
    def execute(sql: str) -> ExecuteResult: ...
```

后续如果 Wren API 细节变化，只需要改 adapter。

## 8. 和 Codex SDK / 自改进闭环的关系

当前 MVP 不直接实现 Codex SDK 自改进。

但 trace、eval、成功案例、失败案例的结构要提前设计好，因为后续可以加上：

```text
Data Subagent 运行
  -> 产生 trace / feedback / failure cases
  -> 专家审查并形成 eval
  -> Codex SDK 作为 improvement runtime
  -> 修改代码、prompt、Wren context、business rules、confirmed NL-SQL examples
  -> 跑回归测试
  -> 人工 review 后合入
```

也就是说，Data Subagent MVP 是业务闭环的第一步；Codex SDK 自改进是后续叠加的工程闭环。

## 9. 推荐开发顺序

1. 新建项目目录。
2. 定义 `DataAnswer`、`TraceRecord`、`WrenAdapter` 等核心类型。
3. 实现一个 fake / mock WrenAdapter，用于离线跑通流程。
4. 实现 Data Subagent 的受控 ReAct loop。
5. 实现 dry-run 失败后的 SQL repair。
6. 实现 trace 保存。
7. 写 3-5 个最小 eval case。
8. 再替换成真实 Wren adapter。

## 10. 验收标准

MVP 至少满足：

- 能输入一个自然语言问数问题。
- 能检索或模拟检索 Wren context。
- 能生成 SQL。
- 能 dry-run。
- dry-run 报错时能尝试修复。
- 能返回结构化答案。
- 能记录 trace。
- 代码边界清楚，后续能被外层 General Agent 当作 tool 调用。

