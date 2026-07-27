# Documentation Index

`docs/` 中的文件是项目设计、验证方法、实验结果和工程记录。它们应随代码一起版本化，因为代码评审需要知道“为什么这样实现”和“如何复现”；但并非每一份文档都适合作为对外产品说明。

## Data Subagent Runtime

- [`data_subagent_mvp_plan.md`](data_subagent_mvp_plan.md)：MVP 范围、受控 ReAct 流程和验收标准。
- [`data_subagent_architecture_workflow_react.html`](data_subagent_architecture_workflow_react.html)：可视化运行时架构与工作流。
- [`data_subagent_mvp_real_case.html`](data_subagent_mvp_real_case.html)：真实 MVP 案例。
- [`data_subagent_react_repair_demo.md`](data_subagent_react_repair_demo.md)：SQL dry-run 失败后的修复演示。
- [`wren_jaffle_setup_and_smoke.md`](wren_jaffle_setup_and_smoke.md)：本地 Wren jaffle_shop 设置与 smoke test。

## WrenAI Context Builder

- [`wren_context_builder_plan.md`](wren_context_builder_plan.md)：Context Builder 总体计划与当前实现。
- [`wren_context_builder_feasibility.md`](wren_context_builder_feasibility.md)：Wren CLI 能力和 onboarding 可行性验证。
- [`wren_context_builder_methods.html`](wren_context_builder_methods.html)：Context Builder 方法可视化说明。
- [`context_builder_conversational_revision_plan.md`](context_builder_conversational_revision_plan.md)：候选 Context 的对话式修订流程。
- [`starrocks_mvp_setup.md`](starrocks_mvp_setup.md)、[`starrocks_tpch_context_builder.md`](starrocks_tpch_context_builder.md)：StarRocks 与 TPC-H 演示流程。
- [`bird_starrocks_context_builder_test.md`](bird_starrocks_context_builder_test.md)：BIRD Mini-Dev 的真实集成验证。

## Controlled Improvement

- [`data_agent_self_improvement_architecture_si0_contract.md`](data_agent_self_improvement_architecture_si0_contract.md)：SI0-SI3 的架构、数据契约和权限边界。
- [`si2_docker_worker.md`](si2_docker_worker.md)：受限 Docker / CI 执行环境。
- [`SI0123自改进流程.md`](SI0123自改进流程.md)、[`自改进工作流程.md`](自改进工作流程.md)：中文流程说明。

## Evaluation And Integration

- [`data_subagent_eval_dataset_research.md`](data_subagent_eval_dataset_research.md)：Text-to-SQL 数据集选择与评测路线。
- [`data_agent_main_orchestrator_architecture.md`](data_agent_main_orchestrator_architecture.md)：未来主 Agent 与工具编排设计。
- [`wren_and_open_source_feasibility.md`](wren_and_open_source_feasibility.md)：WrenAI 与其他开源方案的可行性比较。

## Internal Engineering Memory

- [`data_subagent_progress_and_pitfalls.md`](data_subagent_progress_and_pitfalls.md) 是持续更新的开发记录，包含验证命令、历史结果、已知坑和下一步建议。

该工程记录经过公开前隐私复核后随代码发布，便于后续开发会话、代码评审和结果复现。它不应包含人员信息、本机路径、内部基础设施、真实业务数据或本地运行凭据；新增记录仍需按下述规则复核。

## Documentation Safety

提交文档前请确认：

- 使用相对路径或 `<project-root>`，不记录个人主目录。
- 不包含 API key、密码、token、Cookie 或带凭据的连接字符串。
- 生产 discovery snapshot 不包含未经脱敏的 observed/sample values。
- 截图、日志、trace 和评测输出不包含个人信息或真实业务数据。
- 生成物只有在可复现、已检查且确有评审价值时才进入版本控制。
