# Semantic Data Agent

一个以 WrenAI 语义上下文为核心的小型 Data Agent 项目。当前仓库包含可运行的在线问数 MVP、独立的 WrenAI Context Builder，以及受控的离线自改进工作流。

## 项目结构

项目刻意保持三个工作流相互分离：

1. `data_subagent`：在线问数运行时。通过受控循环调用 WrenAI 获取语义上下文、执行 `dry-plan` / `dry-run` / query，并使用 DeepSeek 生成、修复 SQL 和总结结果。
2. `data_subagent_context_builder`：上游 Context / MDL 建设工具。负责数据库检查、候选 Wren 项目生成、验证、评审、发布和回滚，不进入在线问数路径。
3. `data_agent_improvement`：开发期的受控改进工作流。把 trace、eval 和业务反馈整理为可评审候选；它不会自行批准、合并或部署变更。

```text
User / future General Agent
  -> Data Subagent
      -> WrenAI semantic context and query controls
      -> DeepSeek SQL generation / repair / summary
      -> versioned traces and evals

Database / existing context
  -> Context Builder
      -> reviewed Wren project
          -> Data Subagent

Traces / evals / feedback
  -> Controlled Improvement
      -> reviewable Context or source candidate
```

WrenAI 是在线运行路径中的必要组件；Context Builder 和 Controlled Improvement 均保持在该路径之外。

## 当前状态

- Data Subagent MVP 可通过 CLI 运行。
- Context Builder 已具备首个可运行实现，并支持 StarRocks onboarding 流程。
- Controlled Improvement 已完成 SI0-SI3 的受控候选工作流。
- 当前以本地开发和验证为主，尚未提供 FastAPI 服务或生产部署配置。

## 本地运行

当前项目约定使用 Windows PowerShell、项目本地 `.venv-wren` 环境和 Wren CLI。仓库不会提交虚拟环境、API key、运行 trace、评测运行结果或本地 Wren 状态。

运行全部单元测试：

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m unittest discover -s tests
```

检查 Wren：

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent.cli doctor-wren
```

执行一个真实问题：

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?"
```

查看 Context Builder 命令：

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli --help
```

## 文档

详细入口见 [`docs/README.md`](docs/README.md)。建议先阅读：

- [`docs/data_subagent_mvp_plan.md`](docs/data_subagent_mvp_plan.md)：在线问数 MVP 的边界和实现计划。
- [`docs/wren_context_builder_plan.md`](docs/wren_context_builder_plan.md)：Context Builder 的定位、命令和集成方式。
- [`docs/data_agent_self_improvement_architecture_si0_contract.md`](docs/data_agent_self_improvement_architecture_si0_contract.md)：受控改进架构和 SI0-SI3 契约。
- [`docs/data_subagent_progress_and_pitfalls.md`](docs/data_subagent_progress_and_pitfalls.md)：供开发者续接工作的内部工程记录。

## 安全说明

- `deepseek_apikey.txt`、`*apikey*.txt`、`.env` 和本地虚拟环境已被 Git 忽略。
- 不要把生产数据库凭据、真实业务数据、原始 trace 或未经脱敏的 onboarding discovery snapshot 提交到仓库。
- Pull Request 和 `master` 分支推送会运行 Gitleaks；它是额外防线，不能替代提交前人工检查。
- 当前样例数据和 TPCH discovery 内容为演示数据。接入真实数据源时，应只保留必要的 schema 信息，并对样例值、查询结果和标识符进行脱敏。

## 限制

- 项目尚未提供从零创建 `.venv-wren` 的统一依赖安装脚本。
- 在线入口目前是 CLI，尚无 Web API。
- 真实数据源覆盖仍有限，外部评测结果需要人工复核。
- 自改进工作流只生成候选，不拥有业务真值确认、发布、Git 合并或部署权限。
