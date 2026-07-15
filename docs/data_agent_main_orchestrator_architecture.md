# Data Agent 主 Agent 与工具编排架构

## 1. 当前判断

目前项目已经具备两个独立能力，但还没有一个上层 **Main Agent / Data Agent Orchestrator** 来发现状态、选择工具并串联流程。

```text
已有能力
├── Context Builder
│   └── 数据库 → Wren Project / MDL / Context Layer
└── Data Subagent
    └── 用户问题 + 已就绪 Context → SQL → 查询 → 答案

缺失能力
└── Main Agent / Orchestrator
    └── 判断当前应该建 Context、问数，还是修复 Context
```

完整入口应该变成：

```text
用户提供数据库或提出数据问题
                ↓
        Main Data Agent
                ↓
      识别数据库和 Context 状态
                ↓
      ┌─────────┼──────────┐
      ↓         ↓          ↓
   无 Context  已发布可用   已存在但异常
      ↓         ↓          ↓
Context Builder Data Subagent Semantic Improvement
      ↓         ↓          ↓
  审核、发布    返回答案    修复、验证、发布
      └─────────┴──────────┘
```

## 2. Main Agent 的核心职责

Main Agent 的核心不是生成 SQL 或 MDL，而是完成以下四类工作。

### 2.1 识别数据源

判断数据库身份、类型、连接配置，以及是否曾经完成 onboarding。

### 2.2 检查 Context 状态

不应仅检查目录是否存在，而要检查：

- 是否有对应 Wren Project
- `context validate` 是否通过
- `context build` 是否成功
- 数据库 Schema 是否发生变化
- Context 是否经过审核和发布
- 当前版本是否处于健康状态

### 2.3 路由到正确工具

```text
Context 不存在
  → Context Builder 首次建设

Context 是 draft
  → 继续验证或请求人工审核

Context 已发布且健康
  → Data Subagent 问数

Context 已过期
  → 增量重建或重新验证

查询出现重复语义问题
  → Semantic Improvement Loop

数据库无法连接
  → 基础设施错误，不调用问数
```

### 2.4 维护任务状态

Context Builder 可能需要较长时间，并可能等待业务人员补充口径，因此 Main Agent 要能够返回：

```text
onboarding_required
onboarding_in_progress
waiting_for_business_review
context_ready
query_completed
context_improvement_required
failed
```

## 3. Context Registry

系统需要引入一个目前还不存在的 **Context Registry**：

```text
datasource_id
database_fingerprint
wren_project_dir
context_version
schema_fingerprint
status
validation_result
published_at
last_query_health
```

推荐的 Context 生命周期是：

```text
ABSENT
  → BUILDING
  → VALIDATING
  → NEEDS_REVIEW
  → PUBLISHED
  → STALE / DEGRADED
  → IMPROVING
  → PUBLISHED
```

## 4. 路由原则

Main Agent 的路由逻辑应尽量确定性：

```python
if not context_exists:
    run_context_builder()
elif context_is_stale:
    refresh_or_validate_context()
elif not context_is_published:
    request_review()
elif context_is_degraded:
    run_semantic_improvement()
else:
    ask_data_subagent()
```

LLM 可以帮助理解用户意图和处理模糊情况，但“Context 是否可用”应该由 Registry、Schema 指纹和 Wren 验证结果决定，不能让 LLM 凭感觉判断。

## 5. 当前缺失的上层模块

现在不只是缺 Semantic Improvement Loop，而是缺两个上层模块：

```text
1. Main Agent / Orchestrator
   负责数据源识别、Context readiness 判断和工具路由

2. Semantic Improvement Loop
   负责把运行反馈和用户自然语言业务说明转换为经过验证的新 Context 版本
```

Semantic Improvement 的核心交互不是要求领域专家直接编辑 Wren YAML，而是：

```text
用户用自然语言确认或修正业务语义
-> Codex 将反馈转换为 Context Layer 修改
-> Builder 运行版本化、semantic diff、Wren 验收和回归测试
-> 用户审核语义变化并明确批准
-> Registry 发布新版本
```

详细目标和分阶段计划见：

```text
docs/context_builder_conversational_revision_plan.md
```

## 6. 目标架构

```text
General Agent / 用户
        ↓
Main Data Agent / Orchestrator
        ├── Context Registry
        ├── Context Builder Tool
        ├── Data Subagent Tool
        └── Semantic Improvement Tool
                 ↓
          Versioned Context Layer
                 ↓
              WrenAI
                 ↓
             真实数据库
```

系统应遵守一条硬规则：**Context 未达到 `PUBLISHED + HEALTHY` 状态时，Main Agent 不能绕过 Wren 直接让 Data Subagent 查询数据库。**
