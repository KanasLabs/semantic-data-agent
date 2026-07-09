# New Session Prompt: WrenAI Context Builder / MDL Onboarding Tool

请先阅读：

1. `AGENTS.md`
2. `docs/data_subagent_progress_and_pitfalls.md`
3. `docs/wren_context_builder_plan.md`

本次新会话不要继续改 Data Subagent runtime 主链路，除非发现必须修复的接口问题。当前 Data Subagent MVP 的职责是在线问数 runtime，它消费已有 Wren context / MDL；本次目标是单独调研、设计并实现上游配套能力：

```text
WrenAI Context Builder / MDL Onboarding Tool
```

## 核心目标

设计并验证一个最小工具链，用于把真实数据库或 dbt project onboarding 到 WrenAI 语义层：

```text
database / dbt project
-> WrenAI native import if available
-> Wren project / MDL / profiles
-> rules / knowledge / examples
-> validate / build / dry-run
-> onboarding report
-> smoke eval cases for Data Subagent
```

## 边界要求

- WrenAI 仍然是强制依赖，优先使用 WrenAI 原生能力，不要重造 WrenAI。
- 如果 WrenAI CLI 只支持 dbt import，要明确记录，不要假装能直接高质量导入任意数据库。
- 如果必须写脚本，只写 glue code、schema inspection、校验、报告、smoke case 生成。
- 不要把 Context Builder 混入 Data Subagent runtime。
- 不要把自动生成的 schema-level MDL 说成高质量业务语义层；真实业务指标、字段口径、同义词、权限和时间口径需要人工或业务文档参与。

## 第一阶段要做的事

1. 验证当前本地 `.venv-wren/Scripts/wren.exe` 对 `context import`、`profile import`、`context validate`、`context build` 的真实能力。
2. 调研 WrenAI GitHub/docs 里是否已有 database introspection、MDL generation、dbt import、profile import 能力。
3. 梳理当前 repo 已有的 BIRD SQLite -> DuckDB -> generated Wren project 脚本，判断哪些可以复用，哪些只能作为临时 benchmark glue。
4. 设计 Context Builder 的最小 CLI：

```text
python -m data_subagent_context_builder.cli inspect ...
python -m data_subagent_context_builder.cli import-dbt ...
python -m data_subagent_context_builder.cli generate-from-db ...
python -m data_subagent_context_builder.cli validate ...
python -m data_subagent_context_builder.cli make-smoke-eval ...
```

5. 输出或更新文档：

```text
docs/wren_context_builder_plan.md
docs/wren_context_builder_feasibility.md
```

## 建议产物

```text
src/data_subagent_context_builder/
scripts/...
docs/wren_context_builder_plan.md
docs/wren_context_builder_feasibility.md
data/evals/cases/<project>_smoke.jsonl
data/wren/<project>/
```

## 验证要求

每做一个阶段，要记录：

- 使用的 WrenAI 命令
- 输入数据源
- 生成/导入的 Wren project 路径
- `wren context validate` 结果
- `wren context build` 结果
- 至少一个 `wren dry-run` 结果
- 发现的坑和 workaround

重要进度和踩坑必须同步更新：

```text
docs/data_subagent_progress_and_pitfalls.md
```

## 当前已知事实

- Data Subagent MVP 已跑通 WrenAI CLI + DeepSeek + trace/eval。
- 当前 BIRD benchmark 的 Wren project 是 repo 脚本从 SQLite schema 生成的 schema-level context，不是 WrenAI 原生自动推理出的完整业务 MDL。
- 当前 WrenAI CLI 之前观察到 `context import` / `profile import` 来源主要是 `dbt`，新会话需要重新验证并记录具体命令输出。
- 本地 DeepSeek key 在 `deepseek_apikey.txt`，不要打印、复制或写入文档。

