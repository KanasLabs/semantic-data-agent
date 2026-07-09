# New Session Prompt: Data Subagent MVP

下面这段可以直接复制到新的 Codex 会话中，作为开发启动 prompt。

```text
我现在要实现一个智能问数 Data Subagent 的 MVP。

背景：
我们之前讨论过一个 Hybrid 架构：外层 General Agent 负责对话、意图识别和任务分流；问数能力不做成死板 pipeline，而是封装成一个带受控 ReAct 能力的 Data Subagent。未来外层 Agent 可以把它当作 `ask_data_question` tool 调用。

当前阶段只实现 Data Subagent，不实现外层 General Agent，也不实现 Codex SDK 自改进闭环。

目标：
实现一个最小业务闭环：
用户自然语言问题
 -> Data Subagent
 -> 获取 Wren context
 -> 生成 SQL
 -> Wren dry-run
 -> 如果报错，错误回灌给 LLM 并修复 SQL，最多重试 N 次
 -> execute
 -> 返回答案、SQL、图表建议、trace_id
 -> 保存 trace

架构要求：
1. Data Subagent 是受控 ReAct，不是完全开放 agent。
2. 工具集合先限制为：
   - get_context
   - generate_sql
   - dry_run_sql
   - repair_sql
   - execute_sql
   - summarize_result
3. Wren 能力通过 adapter 抽象，例如：
   - get_context(question)
   - dry_run(sql)
   - execute(sql)
4. 第一版可以先写 mock WrenAdapter，跑通流程后再接真实 Wren。
5. 每次运行都要保存 trace，trace 后续用于 eval 和自改进闭环。

建议返回结构：
{
  "status": "success | need_clarification | failed",
  "answer": "...",
  "sql": "...",
  "rows": [],
  "chart_spec": {},
  "context_used": [],
  "trace_id": "...",
  "confidence": 0.0,
  "warnings": [],
  "error": null
}

请你先阅读当前目录结构，然后提出一个最小实现方案。如果项目目录为空，就按这个目标创建一个简单、清晰、可测试的项目结构。优先实现可运行闭环，不要先做复杂前端或完整外层 Agent。

请参考这些文件：
- data_subagent_mvp_handoff.md
- intelligent_text2sql_agent_architecture.html
- runtime_codex_hybrid_self_improving.html
```

## 建议一起带到新会话的文件

最少带这两个：

```text
data_subagent_mvp_handoff.md
new_session_prompt_for_data_subagent.md
```

如果新会话需要理解完整架构背景，再带：

```text
intelligent_text2sql_agent_architecture.html
runtime_codex_hybrid_self_improving.html
```

不建议带原始 `.jsonl` 会话文件。它包含过多运行时细节、路径、工具调用和内部字段。需要分享讨论内容时，用脱敏导出的 Markdown / HTML。

