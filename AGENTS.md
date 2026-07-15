# AGENTS.md

This file is the persistent entry point for new Codex sessions in this project.
Read it before making changes.

## Project Goal

Build a small Data Agent system with two deliberately separate workstreams:

1. `data_subagent`: the online intelligent data-questioning runtime.
2. `data_subagent_context_builder`: the upstream WrenAI context / MDL onboarding
   workflow tool.

The Data Subagent MVP is runnable. The Context Builder also has a runnable first
implementation and must remain outside the online ask path.

The current agreed architecture is:

```text
User / future General Agent
  -> ask_data_question(...)
      -> Data Subagent controlled loop
          -> WrenAI semantic context / dry-plan / dry-run / query
          -> DeepSeek SQL generation / repair / summarization
          -> JSONL trace store
```

WrenAI is mandatory in the runtime path. Do not replace it with DB-GPT, Vanna,
SQLChat, MindsDB, or a hand-rolled semantic layer. Those projects are design
references only.

The upstream relationship is:

```text
database / existing context
  -> WrenAI Context Builder / MDL onboarding
      -> reviewed Wren project / context
          -> Data Subagent online runtime
```

## First File To Read

After this file, always read:

```text
docs/data_subagent_progress_and_pitfalls.md
```

It records current progress, verified commands, known pitfalls, and open next
steps. Update it whenever you make a meaningful project change or discover a new
pitfall.

Then read the files for the active workstream:

```text
Data Subagent runtime:
- docs/data_subagent_architecture_workflow_react.html
- docs/data_subagent_mvp_real_case.html

WrenAI Context Builder:
- new_session_prompt_for_wren_context_builder.md
- docs/wren_context_builder_plan.md
- docs/wren_context_builder_feasibility.md
- docs/wren_context_builder_methods.html
```

## Current Runtime Choices

- Wren environment: `.venv-wren`
- Wren CLI: `.venv-wren/Scripts/wren.exe`
- Python for project commands: `.venv-wren/python.exe`
- Wren project: `data/wren/jaffle_wren_project`
- Wren home: `data/wren/home`
- Demo data source: Wren quickstart `jaffle_shop` on DuckDB
- LLM provider: DeepSeek
- Default DeepSeek model: `deepseek-v4-flash`
- Trace path: `data/traces/data_subagent.jsonl`

The local DeepSeek key lives in `deepseek_apikey.txt`. Treat it as a secret.
Never print it, copy it into docs, or commit it.

## Important Commands

Run tests:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
```

Latest verified result on 2026-07-15:

```text
Ran 81 tests
OK
```

Check Wren:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli doctor-wren
```

Ask a real question:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?"
```

Run the real ReAct repair demo:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?" --inject-initial-sql "SELECT bad_column FROM orders" --limit 5
```

Run the current eval suite:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval --suite data\evals\cases\jaffle_smoke.jsonl --suite-name jaffle_smoke --limit 20
```

Run against a non-default Wren project:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?" --wren-project-dir data\wren\<project> --wren-home data\wren\home
```

Inspect the Context Builder command surface:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent_context_builder.cli --help
```

Implemented Context Builder commands:

```text
inspect
generate-from-db
generate-schema-draft
validate
enrich-with-codex
register-candidate
revise-candidate
review-candidate
answer-review-question
resume-revision
retry-revision-evals
approve-candidate
reject-candidate
publish-candidate
rollback-context
make-smoke-eval
starrocks-query
generate-from-starrocks
```

Prepare the local TPC-H SF 0.01 StarRocks fixture:

```powershell
.\.venv-wren\python.exe scripts\setup_starrocks_tpch.py --host 127.0.0.1 --port 19030 --database tpch_sf001 --scale-factor 0.01 --allow-empty-password --force
```

Run the StarRocks skill-first Context Builder:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent_context_builder.cli --project-root . generate-from-starrocks --project-name tpch_starrocks --project-dir data\wren\tpch_starrocks_wren_project --host 127.0.0.1 --port 19030 --database tpch_sf001 --user root --allow-empty-password --smoke-sql "SELECT COUNT(*) AS order_count FROM orders" --execute --force
```

Prepare a local BIRD Mini-Dev SQLite eval subset:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py --source-dir data\external\bird_mini_dev\raw --db-id debit_card_specializing --limit 30 --force
```

If Hugging Face network access works, add `--download` to let the script fetch
`birdsql/bird_mini_dev` into the same source directory.

If Hugging Face is unavailable but the BIRD OSS package is acceptable to
download, use:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py --download-oss --source-dir data\external\bird_mini_dev\raw --db-id debit_card_specializing --limit 30 --force
```

The OSS package is about 764 MB compressed.

## Implementation Boundaries

- Keep the online question-answering runtime small and deterministic.
- Use `DataSubagent` as the controlled loop, not an open-ended agent.
- Use `WrenAdapter` as the boundary around Wren details.
- Use `WrenCliAdapter` for the real MVP runtime.
- Use `FakeWrenAdapter` only for unit tests.
- Keep `data_subagent_context_builder` upstream and separate from
  `data_subagent`; it prepares and validates Wren projects but is not called by
  the online ask loop.
- Prefer the Context Builder's Wren `generate-mdl` skill path. The deterministic
  schema draft is an explicit fallback/debug path, not a business-ready MDL.
- Context Builder Codex execution is prompt-only by default. `--execute` is
  required, and the builder owns bounded post-generation Wren
  validate/build/dry-run checks.
- Keep Codex SDK out of the online question-answering path for now. It is a
  later background improvement runtime that consumes traces and evals.
- Avoid editing generated/local Wren state unless the task is explicitly about
  Wren setup:
  - `data/wren/home/`
  - `data/wren/jaffle_shop_duckdb/`
  - `data/wren/jaffle_wren_project/.wren/`
  - `data/traces/*.jsonl`

## Documentation Maintenance Rule

When you finish a meaningful change, update
`docs/data_subagent_progress_and_pitfalls.md` with:

- what changed
- how it was verified
- any new trace IDs or demo commands
- any pitfall or workaround that should help the next session
