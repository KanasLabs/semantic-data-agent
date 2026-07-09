# WrenAI Context Builder / MDL Onboarding Tool Plan

Last updated: 2026-07-09

This document defines a separate upstream workstream from the Data Subagent MVP.

## 1. Positioning

The current Data Subagent MVP is the online question-answering runtime:

```text
user question
-> Data Subagent controlled workflow
-> WrenAI context / dry-plan / dry-run / execute
-> DeepSeek SQL generation / repair / summarization
-> trace / eval
```

The WrenAI Context Builder is an upstream onboarding tool:

```text
database or dbt project
-> WrenAI-native import if available
-> Wren project / MDL / profiles
-> rules / knowledge / examples
-> Wren validate / build / dry-run
-> smoke eval cases
```

Keep these responsibilities separate. The Data Subagent should consume a Wren
context; it should not own full semantic-layer construction.

## 2. Design Principles

- Use WrenAI as the source of truth for semantic-layer capabilities.
- Prefer WrenAI native import/build/validation commands over custom generation.
- Use scripts only as glue code, schema inspection, reporting, or fallback
  scaffolding.
- Treat generated schema-level MDL as a draft, not a business-ready semantic
  layer.
- Make every onboarding run reproducible through commands and saved reports.
- Produce smoke eval cases that the Data Subagent can run without special logic.

## 3. First Feasibility Questions

Answer these before implementing a larger tool:

1. What does the installed WrenAI CLI support today?
2. Does `wren context import` support anything beyond dbt?
3. Does `wren profile import` support anything beyond dbt?
4. Can WrenAI introspect a database directly into model metadata / MDL?
5. If database introspection is not supported, what is the cleanest fallback?
6. Which parts of the existing BIRD SQLite setup scripts are reusable as generic
   glue, and which parts are benchmark-only?

## 4. Proposed MVP Scope

The first useful version should support two paths.

### Path A: dbt-first

Input:

```text
dbt project directory
database profile
project name
```

Process:

```text
wren context import dbt ...
wren profile import dbt ...
wren context validate
wren context build
wren dry-run smoke SQL
```

Output:

```text
data/wren/<project>/
docs/<project>_wren_onboarding_report.md
data/evals/cases/<project>_smoke.jsonl
```

### Path B: database fallback

Input:

```text
SQLite / DuckDB / supported database connection
project name
optional business notes
optional seed questions
```

Process:

```text
inspect schema
generate draft Wren project if WrenAI has no native DB import
write profile
wren context validate
wren context build
wren dry-run smoke SQL
emit report with limitations
```

Output:

```text
data/wren/<project>/
docs/<project>_wren_onboarding_report.md
data/evals/cases/<project>_smoke.jsonl
```

## 5. Non-Goals

- Do not promise fully automatic high-quality business MDL.
- Do not fold onboarding code into `DataSubagent`.
- Do not replace WrenAI import/build/validation with a parallel semantic layer.
- Do not optimize BIRD benchmark generation before clarifying generic Wren
  onboarding requirements.

## 6. Initial CLI Sketch

Possible package:

```text
src/data_subagent_context_builder/
```

Possible commands:

```powershell
python -m data_subagent_context_builder.cli inspect --db ...
python -m data_subagent_context_builder.cli import-dbt --dbt-project ...
python -m data_subagent_context_builder.cli generate-from-db --db ...
python -m data_subagent_context_builder.cli validate --wren-project-dir ...
python -m data_subagent_context_builder.cli make-smoke-eval --wren-project-dir ...
```

The exact command surface should be decided after feasibility checks against the
installed WrenAI CLI and current WrenAI documentation/source.

## 7. Integration With Data Subagent

The builder should hand off artifacts to the existing runtime:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli ask `
  "..." `
  --wren-project-dir data\wren\<project> `
  --wren-home data\wren\home
```

Smoke evals should use the existing eval runner:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\<project>_smoke.jsonl `
  --suite-name <project>_smoke `
  --wren-project-dir data\wren\<project> `
  --wren-home data\wren\home
```

## 8. Documentation Requirements

Every meaningful onboarding experiment should record:

- date
- source database or dbt project
- WrenAI version / command output
- generated or imported project path
- validation result
- build result
- dry-run result
- known limitations
- next action

Also update:

```text
docs/data_subagent_progress_and_pitfalls.md
```

when this workstream changes repo behavior, adds a new reusable command, or
discovers a new WrenAI pitfall.

