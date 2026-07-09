# AGENTS.md

This file is the persistent entry point for new Codex sessions in this project.
Read it before making changes.

## Project Goal

Build a minimal Data Subagent MVP for intelligent data questioning.

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

## First File To Read

After this file, read:

```text
docs/data_subagent_progress_and_pitfalls.md
```

It records current progress, verified commands, known pitfalls, and open next
steps. Update it whenever you make a meaningful project change or discover a new
pitfall.

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
