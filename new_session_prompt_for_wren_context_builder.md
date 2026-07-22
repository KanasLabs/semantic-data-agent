# New Session Prompt: WrenAI Context Builder / MDL Onboarding Tool

本会话只关注 Wren Context Builder / MDL onboarding，不要修改在线 Data
Subagent 问答主链路，除非发现两者之间必须修复的接口问题。

开始工作前依次阅读：

1. `AGENTS.md`
2. `docs/data_subagent_progress_and_pitfalls.md`
3. `docs/wren_context_builder_plan.md`
4. `docs/wren_context_builder_feasibility.md`
5. `docs/context_builder_conversational_revision_plan.md`

## 当前定位

Context Builder 是在线 Data Subagent 的上游工具，负责把数据库、dbt 项目
或已有上下文接入 Wren 语义层。

当前实现应称为“带 Codex 执行能力的有界 agentic workflow tool”，还不是
完整 subagent。外层代码固定工作阶段、重试上限和停止条件；Codex 在单轮内
按照 Wren skill 完成需要推理的 MDL 建模和修复。

新的核心产品目标是“自然语言驱动的候选 Context 修订”：用户负责确认业务真相，
Codex 负责把自然语言反馈转化为 Wren Context 修改，Builder 负责新版本、provenance、
semantic diff、Wren 验收、smoke/regression 和发布门禁。人工审核不应要求用户直接
编辑 Wren YAML，Codex 也不能自行 approve 或 publish。

## 已实现的第一线路

```text
DB / existing context
-> Context Builder 准备 schema 事实和可查询 runtime
-> Codex 读取并遵循 Wren generate-mdl skill
-> Codex 生成或修改 Wren MDL
-> Builder 外层执行 Wren validate / build / dry-run
-> 失败时将结构化 Wren errors 反馈给 Codex
-> 最多 N 个 repair rounds
-> onboarding report / smoke-eval artifacts
```

SQLite 输入目前会被转换为 DuckDB，因为当前本地 Wren runtime 使用 DuckDB
profile 执行验证和查询。这是本项目针对 SQLite onboarding 的适配行为，不是
Wren 要求所有数据源都必须转换为 DuckDB。

## 已实现命令

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli inspect ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli generate-from-db ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli generate-schema-draft ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli validate ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli enrich-with-codex ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli make-smoke-eval ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli starrocks-query ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli generate-from-starrocks ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli register-candidate ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli revise-candidate ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli review-candidate ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli answer-review-question ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli resume-revision ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli approve-candidate ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli reject-candidate ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli publish-candidate ...
.\.venv-wren\python.exe -m data_subagent_context_builder.cli rollback-context ...
```

关键行为：

- `generate-from-db` 默认走 `mode=skill`，这是第一线路。
- 它只准备空 Wren project、DuckDB runtime/profile、schema manifest 和 Codex
  prompt，不会默认用确定性代码写 `models/*/metadata.yml`。
- Codex prompt 明确规定 Wren 安装的 `generate-mdl` skill 优先；manifest 只是
  seed evidence，Codex 可按 skill 需要直接查询 DuckDB。
- 使用 `--execute` 后，Builder 会在 Codex 返回后独立执行 Wren
  validate/build/dry-run，并通过 `--max-repair-rounds` 控制外层修复轮次。
- `generate-schema-draft` 是确定性 schema-level YAML fallback/debug 路线，
  不是推荐的业务语义建模线路。

## 已验证结果

真实 BIRD Mini-Dev `debit_card_specializing` 已经通过第一线路完成 onboarding：

```text
Codex round 0: return code 0
repair rounds used: 0
Wren validate: 5 models, 4 relationships
Wren build: target/mdl.json generated
Wren dry-run: OK
```

每轮产物保存在目标 Wren project：

```text
onboarding/prompts/round_<n>.md
onboarding/codex_last_messages/round_<n>.md
onboarding/validation/round_<n>.json
```

最新完整测试：

```text
Ran 130 tests
OK
```

2026-07-14 已实现并真实验证 StarRocks 安全查询原语 `starrocks-query`：

- 通过 `mysqlclient/MySQLdb` 连接 StarRocks MySQL 协议端口。
- 只允许受控的 `SHOW / DESCRIBE / SELECT / WITH / EXPLAIN`。
- 实施 Catalog/Database allowlist、单语句、超时和最大返回行数。
- 密码只从指定环境变量读取；空密码必须显式使用 `--allow-empty-password`，且只适用于
  隔离的本地 fixture。
- 每次执行、拒绝或失败都会写 JSONL evidence；默认不保存结果值。
- 已在 `127.0.0.1:19030/data_agent_mvp` 完成 Catalog、Database、Table、Column
  和有限采样查询，`DELETE` 在执行前被拒绝。

WrenAI CLI 没有名为 `starrocks` 的 datasource。项目已有真实验证，使用 Wren
`doris` datasource 可以连接本地 StarRocks 3.5 fixture。

`generate-from-starrocks` 已实现 Skill-first 流程：Builder 创建空项目、导入并绑定
环境变量凭据的 `doris` profile；Codex 只能通过 `starrocks-query` 自主 discovery，
并生成 `discovery_snapshot/schema_manifest` 和候选 Wren Context；Builder 独立检查
Wren validate/build/dry-run 以及 discovery artifacts/evidence。

真实本地 fixture 已生成 2 个 Models、1 个通过 join coverage/orphan query 验证的
Relationship 和 24 条受控 evidence。首次运行中 Codex 已完成，但旧 stdout pipe
捕获方式被可选 Wren memory 子进程拖到外层 timeout；现在 prompt 禁止 memory
index/fetch/recall，runner 使用临时文件捕获输出并结构化处理进程树超时。

TPC-H SF 0.01 StarRocks 已完成真实 Skill-first onboarding：Codex 只通过
`starrocks-query` 执行 69 次 discovery，生成 8 Models、8 个零孤儿关系、snapshot、
manifest、rules 和 examples；Wren validate/build、三表 Join、复合键 Join 均通过，
Data Subagent smoke rerun 为 5/5。项目路径是
`data/wren/tpch_starrocks_wren_project`。

BIRD Mini-Dev `debit_card_specializing` 也已完成 StarRocks Skill-first 集成测试：
五张表约 42 万行通过 `scripts/setup_starrocks_bird.py` 可复现导入；Codex 执行 37 条
受控查询，生成 5 Models、4 个零孤儿关系，Wren 验收通过且未复现旧
`customers.None` 关系。30 条原始 Gold 已分类，首批 Verified10 覆盖五表四关系；
修复测试链路的 Wren 重复 LIMIT、Windows UTF-8 和浮点比较后，评测为 10/10，
其中 7 auto-pass、3 needs-triage。详见
`docs/bird_starrocks_context_builder_test.md`。

BIRD case 0012 还完成了真实 clarification/resume HITL：Codex 对缺少 grain、
denominator 和 NULL policy 的请求返回 `CLARIFICATION_REQUIRED`；用户回答后在同一
revision 恢复，生成基于 distinct LAM customer 的规则和 SQL example。Wren、3 条
smoke、Verified10 和新语义回归全部通过，结果为 3,594 / 3,611 = 99.5292163%。
用户查看 review packet 后已显式批准，候选和 revision 均为 `APPROVED`，批准
provenance 为 `user_review_decision`。尚未 publish，且 published pointer 不存在。

## 当前边界和未完成项

- WrenAI CLI `0.12.0` 的原生 import 已验证主要面向 dbt；任意数据库 onboarding
  仍需要 agent/script 做 schema discovery。
- Context Builder 已实现 SQLite/DuckDB 和 StarRocks 两条 Skill-first onboarding
  路线；两者的数据源准备与 discovery 边界不同。
- StarRocks 已有受控查询工具、`generate-from-starrocks` Skill-first onboarding
  和独立 Wren `doris` runtime fixture。
- 已有 `register-candidate`、`revise-candidate`、resume/HITL、评测和发布生命周期；
  revision 可按每次显式授权使用受控 StarRocks 再调查。
- dbt-native import orchestration 还没有加入 CLI。
- 成功 onboarding 后还没有自动运行 `make-smoke-eval` 和 Data Subagent eval。
- 尚无策略层来决定数据源路线、识别语义缺口、主动询问业务问题、安排 enrichment
  或计算 readiness/quality score，因此不要把当前工具描述成完整 subagent。
- 自动生成的语义层不能被宣称为业务完备；关系、指标、口径、规则和 examples 必须
  有 schema、运行数据、业务文档或用户说明作为证据。

## 下一步优先级

R0-R3 MVP 已实现：

```text
src/data_subagent_context_builder/revision_store.py
tests/test_context_builder_revision_store.py
src/data_subagent_context_builder/revision_engine.py
tests/test_context_builder_revision_engine.py
src/data_subagent_context_builder/semantic_diff.py
src/data_subagent_context_builder/revision_eval.py
tests/test_context_builder_semantic_diff.py
tests/test_context_builder_revision_eval.py
src/data_subagent_context_builder/review_workflow.py
tests/test_context_builder_review_workflow.py
src/data_subagent_context_builder/revision_starrocks.py
tests/test_context_builder_revision_starrocks.py
```

R0 提供 candidate/revision/HITL ID、原子 JSON、状态迁移、change request、
provenance、clarification/approval 门禁和 semantic diff/review packet schema。
R1 增加 `register-candidate` 与 `revise-candidate`：复制基线到 Registry 候选目录，
Codex 只在候选 Wren project 内写入，Builder 独立运行 validate/build/dry-run 和有界
repair。成功进入 `REVIEW_REQUIRED`，失败保留为 `VALIDATION_FAILED`，原候选不变。
Codex 仍不得直接写 Registry 状态，也不能 approve/publish。

R2 要求 Codex 写结构化 `revision_outcome.json`。歧义会被 Builder 转成持久化
`CLARIFICATION_REQUIRED` task；完成的候选会生成 Models/fields/Relationships/rules/
SQL Examples 级 semantic diff。CLI 的 `revise-candidate --execute` 默认通过现有
Data Subagent CLI 运行自动 smoke，并可重复传入 `--regression-suite`。评测失败进入
`SMOKE_FAILED`。自动 smoke 目前是保守结构级检查，业务口径仍需 regression suite。

R3 已实现：`answer-review-question` 持久化业务答案，`resume-revision` 在同一
revision/candidate 上启动新 Codex 执行；验收后生成 review packet。
`approve-candidate` 使用独立 `user_review_decision` provenance，且不会发布。
`publish-candidate` 单独更新原子 Context pointer，`rollback-context` 只能切回已经
发布过的候选并记录历史。对审核中候选再次 `revise-candidate` 会把旧 revision 标记为
`CHANGES_REQUESTED` 并创建新候选版本。

`revise-candidate` 和 `resume-revision` 支持每次执行显式授权的 StarRocks 再调查。
Catalog/Database、最大行数和超时受限，evidence 不得保存结果行并由外层验收归档。
授权不会从旧候选自动继承。StarRocks 账号仍必须是数据库级只读、库级受限账号；
Builder allowlist 不能替代数据库 grants。

1. 实现 R4 Main Agent 路由：只消费 `PUBLISHED + HEALTHY` Context pointer。
2. 增加 published Context 健康检查、失效标记和自动/人工 rollback 策略。
3. 设计 change-request-aware 业务 smoke 生成。
4. 增加 dbt-native import orchestration。
5. 再设计 ContextBuilderSubagent 的策略状态、ask-user 规则、质量评分和停止条件。

本地 DeepSeek key 位于 `deepseek_apikey.txt`。不得打印、复制或写入文档、日志、
trace、测试输出或提交内容。
