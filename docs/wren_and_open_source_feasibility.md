# WrenAI 与开源方案可行性调研

日期：2026-07-08

## 1. 结论

WrenAI 是本项目智能问数 MVP 已确定的语义层和执行底座。我们不应该在 Data Subagent 中重写 Wren，而应该通过 adapter 调用 Wren 的 CLI / SDK / API 能力。

当前更稳妥的落地方式：

```text
Data Subagent
  -> WrenAdapter
      -> Wren CLI / SDK
          -> Wren context layer / memory / dry-plan / dry-run / query
```

原因：

- WrenAI 已经提供 context layer、MDL、memory、dry-plan、dry-run、query 等 primitives。
- WrenAI 的设计本身就是让 agent 负责编排，Wren 提供可信语义和校验执行路径。
- 我们的差异化工作应该放在业务级问数 loop、trace、eval、工具化接口、后续自改进输入，而不是复制 semantic engine。

## 2. WrenAI 当前形态

调研来源：

- GitHub: https://github.com/Canner/WrenAI
- OSS Quickstart: https://docs.getwren.ai/oss/get_started/quickstart
- CLI Reference: https://docs.getwren.ai/oss/reference/cli

重要事实：

- WrenAI 是开源 GenBI / text-to-SQL / governed BI engine，核心强调 open context layer。
- GitHub README 显示 2026-05-07 之后 Wren Engine 已合并进 `Canner/WrenAI` 仓库的 `core/` 下；旧的 Docker chat-first GenBI app 保留在 `legacy/v1`。
- WrenAI OSS 提供 CLI、core、SDK、skills，并且 README 标注 core / SDK / skills 以 Apache-2.0 开放。
- Wren 支持通过 MDL 表达 models、views、relationships 和 business semantics。
- Wren CLI 支持 `memory fetch`、`memory recall`、`dry-plan`、`dry-run`、`query`。
- Quickstart 明确提到 Codex / Claude Code 等 agent 可以通过 Wren CLI skills/tools 与 Wren 协作。

## 3. 对我们最有用的 Wren 能力

### 3.1 Context / Memory

Wren CLI reference 描述：

- `wren memory describe`：把 MDL manifest 转成给人和 LLM 可读的结构化 plain text。
- `wren memory fetch -q ... --output json`：给 LLM 获取 schema context，并按 schema 大小在 full context 和 embedding search 间切换。
- `wren memory recall -q ... --output json`：检索已有 NL-SQL pair。
- `wren memory store`：把成功 NL-SQL pair 写入 `knowledge/sql/*.md`。

这正好对应 Data Subagent 的 `get_context` 和 `recall_examples`。

### 3.2 SQL 校验与执行

Wren CLI reference 描述：

- `wren dry-plan --sql ...`：把 MDL SQL 转换成目标数据源 dialect SQL，不需要数据库连接。
- `wren dry-run --sql ...`：在真实数据库上 dry-run，不返回 rows，成功输出 OK，失败输出错误原因。
- `wren query --sql ... --output json --limit ...`：执行 SQL 并输出结果。

这正好对应 Data Subagent 的 `dry_plan_sql`、`dry_run_sql`、`execute_sql`。

### 3.3 Skills / Prompt shaping

Wren CLI 有 `wren skills get usage`、`generate-mdl` 等 workflow guide，也有 `wren ask "<question>" --guided|--direct` 生成 prompt 的能力。

MVP 可以先不依赖它们，但它们可以作为 prompt 设计和真实接 Wren 的参考。

## 4. Wren 集成可行性判断

### 可行

- `WrenCliAdapter` 可以用 Python `subprocess` 调 CLI。
- CLI 支持 JSON 输出的命令可直接解析。
- dry-run 错误可以转成 `DryRunResult(error=...)` 回灌给 LLM。
- Query 结果可用 JSON 输出进入 `DataAnswer.rows` 和 trace。
- Wren project、MDL、connection profile 可以独立于 Data Subagent 管理。

### 风险

- Wren CLI 需要环境准备：Python 3.11+、`wrenai[...]`、数据库 connector、profile、MDL build、memory index。
- `memory` extra 包含较大的 native dependencies；文档提到 LanceDB / sentence-transformers / torch 体积较大。
- CLI 输出格式升级可能影响 adapter 解析，所以 adapter 必须集中封装。
- 如果要用 Wren 的 Python SDK，后续需要再确认 SDK 的稳定 API；CLI 是更直接的 MVP 路径。
- Wren OSS 当前不是“给我们的 Python 应用直接调用一个固定 REST API”的形态；CLI/SDK integration 更自然。

### 对策

- 先做 `WrenAdapter` 抽象，再做 `WrenCliAdapter`。
- CLI 命令、超时、stdout/stderr、exit code 全进 trace。
- 单测默认用 `FakeWrenAdapter`，真实 Wren 测试标记为 integration test。
- 文档明确 Wren 环境准备是部署前置条件，不放进 Data Subagent 代码里隐式完成。

## 5. 类似开源方案

本节的目的不是选择替代产品，而是理解同类项目的实现逻辑，吸收适合本项目的设计。第一版运行时依赖仍固定为 WrenAI。

### 5.1 WrenAI

定位：open context layer + governed text-to-SQL + GenBI。

优点：

- 更贴合“语义层先行”的架构。
- 有 MDL、memory、dry-plan、dry-run、query。
- 与 agent / Codex workflow 的关系明确。
- 更适合作为底座，我们做上层受控 Data Subagent。

限制：

- 需要先建设 Wren project / MDL / profile。
- 第一版最好按 CLI adapter 接入，而不是假设有稳定 REST 服务。

### 5.2 Vanna

来源：https://github.com/vanna-ai/vanna

定位：自然语言到 SQL，再到答案/表格/图表的 Python agent framework。

调研发现：

- GitHub 页面显示该仓库在 2026-03-29 被归档为 read-only。
- README 介绍 Vanna 2.0 有 user-aware permissions、FastAPI integration、web component、trace 等能力。
- MIT license。

判断：

- 能力完整，但仓库已归档，不适合作为当前 MVP 的主底座。
- 可参考其 user-aware tools、trace、streaming UI 思路。

### 5.3 DB-GPT

来源：https://github.com/eosphoros-ai/DB-GPT

定位：开源 agentic AI data assistant，覆盖数据库、CSV/Excel、知识库、SQL、Python 分析、报表。

调研发现：

- README 描述其可连接数据库和文件，让 AI 自动写 SQL，并执行分析 workflow。
- 提供 webserver、agent、RAG、multi-model、sandboxed execution 等能力。
- MIT license。

判断：

- 很完整，但比我们当前 MVP 重很多。
- 如果目标是快速搭一个全功能数据助手，DB-GPT 可评估；如果目标是围绕 Wren semantic layer 做受控问数 subagent，DB-GPT 不是最小路径。

### 5.4 SQLChat

来源：https://github.com/sqlchat/sqlchat

定位：chat-based SQL client/editor。

判断：

- 更像 SQL client + chat UI，不是语义层/业务上下文优先。
- 可作为交互体验参考，不适合作为核心架构底座。

### 5.5 Minds / MindsDB

来源：https://github.com/mindsdb/mindsdb

定位：更泛化的数据/AI agent 平台。

判断：

- 范围较大，适合平台化 agent，不是当前最小 Data Subagent 的直接依赖。

## 6. 推荐选择

主路径：

```text
Data Subagent + WrenAI OSS CLI/SDK
```

其他项目只作为设计参考，不作为第一版运行时依赖。具体吸收点：

- DB-GPT：参考其多工具数据助手的 workflow 分层，但不引入其完整平台。
- Vanna：参考其 NL-SQL example / trace / user-aware permission 思路，但不依赖已归档仓库。
- SQLChat：参考 chat SQL client 的交互方式，但不采用其作为语义层。
- MindsDB/Minds：参考平台化 agent 边界，但不引入其平台 runtime。

不推荐第一版使用：

- Vanna：仓库已归档。
- SQLChat：语义层和受控业务 loop 不够贴合。
- MindsDB/Minds：范围过大。

## 7. 实现前建议

1. 先确认使用 WrenAI OSS CLI 作为第一版真实集成路径。
2. 准备一个 Wren project：
   - 可以先用 Wren quickstart 的 `jaffle_shop`。
   - 或使用业务库生成 MDL。
3. Data Subagent 先实现 adapter interface 和 trace，不把 Wren 安装/初始化混入主逻辑。
4. 将 Wren 环境检查做成独立命令，例如：

```text
python -m data_subagent.cli doctor-wren
```

5. 所有真实 Wren 调用都打 integration test 标记，避免本地无 Wren 时单测失败。

## 8. 已确认实施选择

- 第一版必须使用 WrenAI。
- WrenAI 安装允许使用 `wrenai[memory,main]`。
- 第一版真实数据源优先使用 Wren quickstart 的 `jaffle_shop`。
- LLM provider 使用 DeepSeek。
- DeepSeek API key 本地文件路径为 `deepseek_apikey.txt`，按 secret 处理。
- 其他开源 text-to-SQL 产品仅作为架构参考，不直接使用。

## 9. Codex SDK Runtime 的位置

讨论中“Codex SDK 实现业务 runtime”容易混淆。更准确的拆分是：

```text
在线业务 runtime
  Data Subagent -> WrenAI -> DeepSeek -> trace

后台自改进 runtime
  trace/eval/failure cases -> Codex SDK -> 候选代码/prompt/Wren context/eval 改动 -> 人工 review
```

Codex SDK 不适合第一版直接进入实时问数链路，因为实时链路需要稳定、低延迟、权限和可观测性可控。Codex SDK 更适合作为后台工程 agent，消费 trace 和 eval，产生可审查改动。

因此当前 MVP 的正确做法是：

- 先实现稳定的在线业务 runtime。
- trace 和 eval 结构提前设计好。
- 后续再把 Codex SDK 接入为自改进 runtime adapter。

## 10. 下一步

在确认主路径后，建议先实现：

1. `WrenAdapter` interface。
2. `FakeWrenAdapter` 测受控 loop。
3. `TraceStore`。
4. `WrenCliAdapter`。
5. `ask_data_question`。
6. 3-5 个 eval cases。

这样既不重复造 Wren，又能把我们自己的业务编排能力做成可测试模块。
