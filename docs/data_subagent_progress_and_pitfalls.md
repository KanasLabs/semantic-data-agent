# Data Subagent Progress And Pitfalls

Last updated: 2026-07-09

This document is the project memory for future Codex sessions. Keep it concise
but current.

## 1. Current Status

The project has a runnable Data Subagent MVP.

Implemented runtime:

```text
question
-> local clarity check
-> Wren get_context
-> Wren recall_examples
-> DeepSeek generate_sql
-> local read-only SQL guardrail
-> Wren dry-plan
-> Wren dry-run
-> optional DeepSeek repair_sql loop
-> Wren execute
-> DeepSeek summarize_result
-> JSONL trace
```

Current real data source:

```text
Wren quickstart jaffle_shop
DuckDB database built from dbt
BIRD Mini-Dev debit_card_specializing
SQLite converted to DuckDB and generated Wren project
```

Current real integration:

- WrenAI CLI is installed and used through `WrenCliAdapter`.
- DeepSeek is used through `DeepSeekLLMAdapter`.
- DeepSeek calls now retry transient failures and malformed/empty JSON responses
  before surfacing an error.
- The CLI entry point supports `doctor-wren` and `ask`.
- A debug/eval-only repair demo can be triggered with `--inject-initial-sql`.
- The CLI entry point also supports `eval` for JSONL eval suites.
- The eval CLI supports Wren project overrides for external benchmark projects.

## 2. Architecture Decisions

WrenAI is not reimplemented in this repo. It is used as the semantic and
execution layer.

The boundary is:

```text
src/data_subagent/adapters/wren_base.py
src/data_subagent/adapters/wren_cli.py
```

`DataSubagent` owns the controlled loop. It decides when to call Wren, when to
call DeepSeek, when to repair, and when to save trace.

DeepSeek owns:

- SQL generation
- SQL repair after Wren errors
- result summarization and chart spec generation

Wren owns:

- model/context visibility
- semantic SQL expansion through dry-plan
- database executable validation through dry-run
- query execution

Codex SDK is not part of the online question-answering runtime. The intended
future use is:

```text
traces / evals / failure cases
-> Codex SDK background improvement runtime
-> candidate code, prompt, Wren context, or eval changes
-> tests and human review
```

## 3. Important Files

Core runtime:

```text
src/data_subagent/agent.py
src/data_subagent/cli.py
src/data_subagent/config.py
src/data_subagent/eval_runner.py
src/data_subagent/llm_deepseek.py
src/data_subagent/sql_guardrail.py
src/data_subagent/trace_store.py
src/data_subagent/adapters/wren_cli.py
```

Tests:

```text
tests/test_agent_loop.py
tests/test_eval_runner.py
tests/test_llm_deepseek.py
tests/test_prepare_bird_mini_dev_subset.py
tests/test_sql_guardrail.py
tests/test_trace_store.py
```

Wren project:

```text
data/wren/jaffle_wren_project/wren_project.yml
data/wren/jaffle_wren_project/models/*/metadata.yml
data/wren/jaffle_wren_project/relationships.yml
data/wren/jaffle_wren_project/knowledge/sql/*.md
```

Eval helpers:

```text
data/evals/cases/jaffle_smoke.jsonl
data/evals/cases/bird_mini_dev_debit_card_specializing.jsonl
data/evals/cases/README.md
scripts/prepare_bird_mini_dev_subset.py
scripts/prepare_sqlite_wren_project.py
scripts/setup_bird_mini_dev_eval.py
```

Docs:

```text
docs/data_subagent_architecture_workflow_react.html
docs/data_subagent_bird_smoke_cases.html
docs/data_subagent_mvp_real_case.html
docs/data_subagent_react_repair_demo.md
docs/data_subagent_eval_dataset_research.md
docs/wren_and_open_source_feasibility.md
docs/wren_jaffle_setup_and_smoke.md
docs/data_subagent_mvp_plan.md
```

Documentation update on 2026-07-09:

```text
docs/data_subagent_architecture_workflow_react.html
```

The architecture page now embeds the generated workflow/ReAct diagram directly
as a base64 data URI. It no longer depends on an external image reference and
now explains the diagram, workflow stages, ReAct repair loop, Wren dry-plan /
dry-run / execute, and Trace/Eval role in one page.

New upstream workstream prompt on 2026-07-09:

```text
new_session_prompt_for_wren_context_builder.md
docs/wren_context_builder_plan.md
```

This workstream is separate from the Data Subagent runtime. Its goal is to
research, design, and possibly implement a WrenAI Context Builder / MDL
Onboarding Tool that can take a database or dbt project and produce a Wren
project, validation/build results, onboarding report, and smoke eval cases.
The builder should use WrenAI native capabilities first and only use scripts as
glue/fallback scaffolding.

## 4. Verified Commands

Use `.venv-wren/python.exe`, not `.venv-wren/Scripts/python.exe`.

Run unit tests:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
```

Latest verified result:

```text
Ran 20 tests
OK
```

Check Wren setup:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli doctor-wren
```

Expected shape:

```json
{
  "models": ["customers", "orders", "stg_customers", "stg_orders", "stg_payments"],
  "dry_run_ok": true,
  "dry_run_message": "OK"
}
```

Ask a real question:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?"
```

Run a real Wren + DeepSeek ReAct repair demo:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?" --inject-initial-sql "SELECT bad_column FROM orders" --limit 5
```

The repair demo intentionally injects a bad first SQL attempt. The Wren error,
DeepSeek repair, Wren dry-run, Wren execute, and summarization are real.

Run the jaffle eval suite:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval --suite data\evals\cases\jaffle_smoke.jsonl --suite-name jaffle_smoke --limit 20
```

For `eval`, `--limit` means case count. Use `--query-limit` to change the row
limit for each SQL execution. For `ask`, `--limit` still means query row limit.

Latest verified eval result:

```text
run_id: 20260709-145158-jaffle_smoke
total: 5
passed: 5
failed: 0
duration_ms: 59300
run_path: data/evals/runs/20260709-145158-jaffle_smoke.jsonl
report_path: data/evals/reports/20260709-145158-jaffle_smoke.md
```

Eval records now include timing:

```text
suite started_at / finished_at / duration_ms
case started_at / finished_at / duration_ms
```

Rationale: pass/fail alone is not enough. Timing lets us compare prompt,
provider, Wren context, and repair-loop changes for latency regressions.

Eval records also preserve `gold_sql` when external converters provide it.
Failing cases with `gold_sql` get:

```text
review_status: needs_triage
```

This is deliberate. BIRD / Spider2-style benchmark labels can be noisy, so a
single gold-SQL mismatch must not automatically trigger prompt or Wren context
changes.

Eval now also validates read-only `gold_sql` through Wren:

```text
gold_sql_check.guardrail_ok
gold_sql_check.dry_run_ok
gold_sql_check.execute_ok
gold_sql_check.gold_row_count
gold_sql_check.execution_match
gold_sql_check.needs_triage
gold_sql_check.error
```

If automatic checks pass but predicted rows and gold rows differ, the case stays
`status: pass` but becomes `review_status: needs_triage`. The report includes
these cases under `Review Details`.

BIRD Mini-Dev conversion scaffold:

```powershell
.\.venv-wren\python.exe scripts\prepare_bird_mini_dev_subset.py `
  --input data\external\bird_mini_dev\mini_dev_sqlite.json `
  --output data\evals\cases\bird_mini_dev_subset.jsonl `
  --db-id debit_card_specializing `
  --limit 30
```

This only converts local BIRD JSON into eval case JSONL. It does not download
the dataset and does not create a Wren project. The next step is generating or
importing Wren context for the selected BIRD SQLite database.

SQLite-to-Wren project generation scaffold:

```powershell
.\.venv-wren\python.exe scripts\prepare_sqlite_wren_project.py `
  --sqlite-path data\external\bird_mini_dev\databases\<db_id>\<db_id>.sqlite `
  --output-dir data\wren\bird_<db_id>_wren_project `
  --duckdb-path data\wren\bird_<db_id>.duckdb `
  --project-name bird_<db_id> `
  --wren-home data\wren\home `
  --write-profile `
  --force
```

The Data Subagent CLI can now run against non-default Wren projects:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\bird_mini_dev_subset.jsonl `
  --suite-name bird_mini_dev_subset `
  --wren-project-dir data\wren\bird_<db_id>_wren_project `
  --wren-home data\wren\home
```

Combined BIRD Mini-Dev setup scaffold:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --source-dir data\external\bird_mini_dev\raw `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

If Hugging Face network access works, add `--download`:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --download `
  --source-dir data\external\bird_mini_dev\raw `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

If Hugging Face is unavailable, use the BIRD OSS package shortcut:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --download-oss `
  --source-dir data\external\bird_mini_dev\raw `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

OSS package check on 2026-07-09:

```text
URL: https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip
Status: 200
Content-Length: 800943648 bytes
Approx size: 764 MB compressed
```

The script expects to find BIRD files such as:

```text
data/external/bird_mini_dev/raw/**/mini_dev_sqlite.json
data/external/bird_mini_dev/raw/**/<db_id>.sqlite
```

It emits:

```text
data/evals/cases/bird_mini_dev_<db_id>.jsonl
data/wren/bird_<db_id>.duckdb
data/wren/bird_<db_id>_wren_project/
```

Verified with real BIRD Mini-Dev `debit_card_specializing` on 2026-07-09:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --source-dir data\external\bird_mini_dev\raw\minidev\minidev\MINIDEV `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

Result:

```text
emitted: 30
models: customers, gasstations, products, transactions_1k, yearmonth
relationships: 2
duckdb_path: data/wren/bird_debit_card_specializing.duckdb
wren_project_dir: data/wren/bird_debit_card_specializing_wren_project
```

Wren verification:

```powershell
$env:WREN_HOME='<project-root>\data\wren\home'
<project-root>\.venv-wren\Scripts\wren.exe context validate
<project-root>\.venv-wren\Scripts\wren.exe context build
<project-root>\.venv-wren\Scripts\wren.exe dry-run --sql "select count(*) as customer_count from customers"
```

Result:

```text
context validate: Valid - 5 models, 0 views, 2 relationships
context build: built target/mdl.json
dry-run: OK
```

BIRD smoke eval:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\bird_mini_dev_debit_card_specializing.jsonl `
  --suite-name bird_mini_dev_debit_card_specializing_smoke5 `
  --wren-project-dir data\wren\bird_debit_card_specializing_wren_project `
  --wren-home data\wren\home `
  --limit 5
```

Latest verified result:

```text
run_id: 20260709-165501-bird_mini_dev_debit_card_specializing_smoke5
total: 5
passed: 4
failed: 1
duration_ms: 93138
run_path: data/evals/runs/20260709-165501-bird_mini_dev_debit_card_specializing_smoke5.jsonl
report_path: data/evals/reports/20260709-165501-bird_mini_dev_debit_card_specializing_smoke5.md
```

Representative trace IDs:

```text
auto_pass: trace_73da8bceb38d4ed68bf72244d8e5f2e3
auto_pass: trace_f1188fd1f14f460c97182b60efdf4f29
needs_triage gold mismatch: trace_9e4f4e17a9c04474bda41a7ab49aa190
needs_triage gold mismatch: trace_1b5e4bc5d42447909e9e3aaa847538bc
DeepSeek empty-response failure: trace_3d6666ca72ef486380c7696a419a7494
```

Interpretation:

- 4/5 means the runtime produced executable Wren-backed answers.
- 2/5 were auto-pass with predicted and gold execution matching.
- 2/5 were runtime pass but `review_status: needs_triage` because predicted
  and gold result rows differed.
- 1/5 failed because DeepSeek returned an empty or unparsable SQL JSON response.
- This result should drive grouped triage, not blind prompt edits.

Verified on 2026-07-09 with a temporary BIRD-shaped fixture:

```text
setup_bird_mini_dev_eval.py emitted 1 SELECT-only case
created eval JSONL
created DuckDB file
created Wren project
created Wren profile
```

Verified on 2026-07-09 with a temporary SQLite fixture:

```text
prepare_sqlite_wren_project.py emitted 2 models and 1 relationship
wren context validate: Valid — 2 models, 0 views, 1 relationships.
wren context build: built target/mdl.json
wren dry-run "select count(*) as order_count from orders": OK
```

## 5. Real Demo Cases

### Normal Success Path

Question:

```text
收入最高的前5个客户是谁？
```

Final SQL:

```sql
SELECT first_name, last_name, customer_lifetime_value
FROM customers
ORDER BY customer_lifetime_value DESC
LIMIT 5
```

Result:

```text
Howard R.      99.0
Kathleen P.    65.0
Norma C.       64.0
Christina W.   57.0
Rose M.        57.0
```

Trace:

```text
trace_f4babfdf564c4efdb646fca1e2141505
```

### ReAct Repair Path

Question:

```text
How many orders are there?
```

Injected bad SQL:

```sql
SELECT bad_column FROM orders
```

Wren dry-run observation:

```text
Binder Error: Referenced column "bad_column" not found in FROM clause!
phase=SQL_DRY_RUN
```

DeepSeek repaired SQL:

```sql
SELECT COUNT(*) FROM orders
```

Result:

```json
[{"count_star()": 99}]
```

Trace:

```text
trace_8123219a172d4ed2b7c977e8af45a4d1
```

## 6. Wren Usage Details

This repo uses a real WrenAI CLI installation, not a mock context layer.

Current config:

```text
wren_bin: .venv-wren/Scripts/wren.exe
wren_project_dir: data/wren/jaffle_wren_project
wren_home: data/wren/home
```

Adapter mapping:

```text
get_context()
  -> wren context show --output json
  -> wren memory describe

recall_examples()
  -> read data/wren/jaffle_wren_project/knowledge/sql/*.md

dry_plan(sql)
  -> wren dry-plan --sql ...

dry_run(sql)
  -> wren dry-run --sql ...

execute(sql)
  -> wren query --sql ... --output json --quiet --limit ...
```

`recall_examples()` currently reads markdown examples directly instead of using
`wren memory recall`. This was a stability choice for Windows.

For BIRD SQLite evals, the current Wren context layer is generated by this repo,
then consumed by WrenAI CLI. It is not a WrenAI-native automatic SQLite import:

```text
BIRD SQLite schema
-> scripts/prepare_sqlite_wren_project.py
-> data/wren/bird_<db_id>_wren_project/
-> WrenAI CLI context validate/build/dry-plan/dry-run/query
```

This means:

- WrenAI is still mandatory and is used for context validation, semantic SQL
  expansion, dry-run, and execution.
- The minimal BIRD MDL/model metadata files are authored by our generator.
- The generated BIRD context is schema-level only and currently lacks curated
  business metrics, synonyms, rules, and high-quality examples.
- Relationship generation has a known issue for `debit_card_specializing`:
  generated conditions include `"customers"."None"`. Fix this before relying
  on relationship-driven joins.

## 7. Known Pitfalls And Workarounds

### Python Path In The Wren Env

The project-local environment uses:

```text
.venv-wren/python.exe
```

Do not assume this exists:

```text
.venv-wren/Scripts/python.exe
```

### Wren CLI Unicode On Windows

Wren CLI can print Unicode symbols that fail under a GBK console. Use:

```powershell
$env:PYTHONIOENCODING='utf-8'
```

`WrenCliAdapter` already sets this for subprocess calls.

### Wren Memory Fetch / Recall On Windows

`wren memory fetch` and `wren memory recall` can hang during first-time
memory/embedding initialization on Windows.

Current workaround:

- `get_context()` uses `context show --output json` and `memory describe`
- `recall_examples()` reads confirmed examples from `knowledge/sql/*.md`

### Wren CLI Output Formats

Observed behavior:

- `dry-plan` returns expanded SQL text, not JSON.
- `dry-run` returns `OK` or error text, not JSON.
- `query --output json --quiet` can return JSON object lines, not only a JSON
  array.

The adapter already handles this.

### Chinese Trace Display In PowerShell

Trace JSONL is written as UTF-8. `Get-Content` can display Chinese as mojibake
depending on the console encoding. The file contents are still valid UTF-8.

### Secret Handling

`deepseek_apikey.txt` is local-only and ignored by `.gitignore`. Do not print or
copy it into documentation, traces, commits, or screenshots.

### DeepSeek Summary JSON Can Be Malformed

An eval run on 2026-07-09 initially got 4/5 passing cases. The failing case had
valid SQL, valid Wren dry-run, and valid Wren execution, but the DeepSeek summary
response could not be parsed as strict JSON:

```text
Unterminated string starting at: line 2 column 13
```

Fix:

- SQL generation and repair still require strict JSON.
- `summarize_result()` now falls back to a deterministic summary when only the
  summary JSON parse fails.

Verification after fix:

```text
Ran 12 tests
OK

jaffle_smoke eval: 5/5 passed
```

### DeepSeek Empty Or Malformed JSON Should Retry

Earlier BIRD smoke testing produced a failure where DeepSeek returned an empty
or unparsable SQL JSON response before Wren dry-plan/dry-run could run:

```text
trace_3d6666ca72ef486380c7696a419a7494
Failed to parse LLM JSON response: ''
```

Fix on 2026-07-09:

- `DeepSeekLLMAdapter` retries parse failures, unexpected response shapes,
  network timeouts, URL errors, HTTP 429, and HTTP 5xx responses.
- Defaults are `max_retries=2`, `retry_initial_delay_seconds=1.0`, and
  exponential backoff factor `2.0`.
- HTTP 400/401-style configuration or request errors are not retried.
- `summarize_result()` still falls back to deterministic text after retry
  exhaustion, while `generate_sql()` and `repair_sql()` surface the error.

Verification:

```text
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest tests.test_llm_deepseek
Ran 3 tests
OK

$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
Ran 20 tests
OK
```

### Eval Timing Should Be Recorded

Eval runs now record UTC timestamps and elapsed duration:

```text
suite started_at / finished_at / duration_ms
case started_at / finished_at / duration_ms
```

Use timestamps to align with trace records, and use duration to catch latency
regressions across prompt/model/Wren changes. `duration_ms` is measured with a
monotonic timer.

### Wren Context Import Is dbt-Only In Current CLI

Checked on 2026-07-09:

```powershell
.\.venv-wren\Scripts\wren.exe context import --help
.\.venv-wren\Scripts\wren.exe profile import --help
```

Both import commands currently list `dbt` as the external import source. Wren
can use DuckDB profiles, but it does not automatically introspect arbitrary
SQLite databases into a Wren project through `context import`.

Workaround:

- convert SQLite data into a local DuckDB file
- generate minimal Wren model metadata from SQLite schema
- create/update a Wren DuckDB profile pointing to the DuckDB file directory
- run Data Subagent with `--wren-project-dir`

### SQLite-To-DuckDB Conversion Must Be Bulk Imported

The initial SQLite converter copied rows with Python `executemany`, which timed
out on the real BIRD `debit_card_specializing` database.

Fix:

- use DuckDB `sqlite_scanner` when available
- set DuckDB extension directory to `data/duckdb_extensions`
- bulk import each SQLite table with `CREATE TABLE ... AS SELECT ...`
- fall back to Python row copying only if the extension path fails

Real verification on 2026-07-09:

```text
debit_card_specializing.sqlite: 34 MB
generated DuckDB + Wren project: about 2 seconds through setup script
```

### DuckDB WAL Locks On Windows

Interrupted eval or conversion runs can leave `.venv-wren\python.exe` processes
holding `data/wren/bird_debit_card_specializing.duckdb.wal`.

Observed Wren error:

```text
[ATTACH_DUCKDB_ERROR] Cannot open file ... bird_debit_card_specializing.duckdb.wal
File is already open in ... .venv-wren\python.exe
```

Fixes added on 2026-07-09:

- `setup_bird_mini_dev_eval.py --force` removes both `.duckdb` and `.duckdb.wal`
- `prepare_sqlite_wren_project.py` runs `CHECKPOINT` after conversion
- eval runner flushes JSONL after each case, so a timeout does not lose all
  completed case records

If this recurs, inspect and stop only stale project-local Python processes:

```powershell
Get-Process | Where-Object { $_.Path -like '*dataAgent_mvpLoop*.venv-wren*python.exe' }
```

Do not kill unrelated Python processes.

### Eval Limit Semantics

Before 2026-07-09, `data_subagent.cli eval --limit` accidentally controlled
query row limit, while case count required `--max-cases`. This caused a supposed
smoke5 run to process all 30 BIRD cases.

Current behavior:

```text
ask --limit N       -> SQL result row limit
eval --limit N      -> number of eval cases
eval --query-limit N -> SQL result row limit per case
```

### External Benchmark Results Need Manual Triage

BIRD Mini-Dev is still the recommended first external benchmark, but do not
treat every gold mismatch as proof that the MVP is wrong. A 2026 benchmark audit
reported substantial annotation-error rates in BIRD Mini-Dev / Spider2-style
benchmarks. Use failures as triage inputs:

- check Wren dry-run / execution first
- compare predicted and gold result tables where possible
- group repeated failures by cause before prompt or context changes
- record timing and trace IDs for every run

Current implementation:

- `EvalCase.gold_sql`
- `EvalRunRecord.gold_sql`
- `EvalRunRecord.gold_sql_check`
- `EvalRunRecord.review_status`
- `needs_triage` for failed cases that include `gold_sql`
- `needs_triage` for pass cases whose predicted rows differ from executable
  gold SQL rows

### Hugging Face Network Can Be Unavailable

Observed on 2026-07-09:

```text
huggingface_hub.list_repo_files("birdsql/bird_mini_dev")
WinError 10013 under sandbox
WinError 10060 timeout after approval
```

Do not block on live download. `scripts/setup_bird_mini_dev_eval.py` supports a
local `--source-dir` flow. Put manually downloaded BIRD Mini-Dev SQLite files
under `data/external/bird_mini_dev/raw/`, then run the setup script without
`--download`.

GitHub availability:

```text
git ls-remote https://github.com/bird-bench/mini_dev.git HEAD: OK
shallow clone to data/external/bird_mini_dev/repo: OK
```

The GitHub repo contains README/evaluation/baseline files, but not the full
SQLite database package. Use Hugging Face, OSS zip, or a manually downloaded
package for the actual databases and `mini_dev_sqlite.json`.

### Generated / Local Wren State

Avoid hand-editing or committing:

```text
data/wren/home/
data/wren/jaffle_shop_duckdb/
data/wren/jaffle_wren_project/.wren/
data/traces/*.jsonl
```

### Local Git Metadata Is Incomplete

Observed on 2026-07-09:

```text
git status --short
fatal: not a git repository (or any of the parent directories): .git
```

There is a `.git/` directory, but `.git/HEAD` is missing. Treat `git diff`,
`git status`, and `git diff --check` as unavailable in this workspace until the
repository metadata is repaired or reinitialized. Use direct file inspection for
local verification.

These are local runtime or generated artifacts.

## 8. Current Limitations

- The clarity check is only a local minimal heuristic:

  ```python
  len(question.strip()) >= 4 and any(char.isalpha() for char in question.strip())
  ```

  It does not yet understand business ambiguity.

- Real data sources currently include jaffle_shop and BIRD Mini-Dev
  `debit_card_specializing`.
- Wren Python SDK is not used; the MVP uses Wren CLI through subprocess.
- `memory fetch` / `memory recall` are not on the main path.
- There is no FastAPI service yet; CLI is the smoke-test interface.
- Eval runner exists for `jaffle_smoke` and generated BIRD Mini-Dev subsets.
- BIRD eval quality is still early. The generated Wren project has minimal
  schema/relationship context and no curated business examples.
- The SQLite-to-Wren generator creates a minimal schema/foreign-key context. It
  does not infer business metrics, synonyms, caveats, or high-quality NL-SQL
  examples. Those should be added from BIRD evidence/gold SQL or real business
  docs after the first external eval run.

## 9. Recommended Next Steps

1. Add a reproducible setup script for Wren + jaffle_shop.
2. Add skippable integration tests for real Wren CLI and DeepSeek.
3. Triage the BIRD smoke5 failures and `needs_triage` cases before changing
   prompts or Wren context.
4. Add BIRD-derived Wren knowledge/rules/examples for repeated business
   patterns such as `Date` year/month semantics and `Consumption` vs
   transaction `Price`.
5. Run a clean BIRD 30-case subset after the smoke5 triage fixes.
6. Improve SQL alias quality, for example `order_count` instead of
   `count_star()`.
7. Add trace inspection CLI utilities, such as latest traces and failure summary.
8. Upgrade clarity checking to combine local rules, DeepSeek clarification
   classification, and Wren field/metric matching.
9. Design the later Codex SDK improvement runtime around traces and evals.

## 11. Eval Dataset Research Update

Open-source text-to-SQL datasets were reviewed on 2026-07-09. The current
recommendation is:

```text
Phase E0: internal jaffle_shop eval suite
Phase E1: BIRD Mini-Dev SQLite SELECT-only subset
Phase E2: Spider2-DBT
Phase E3: BIRD-Interact / LiveSQLBench for later interactive evaluation
```

Reasoning:

- BIRD Mini-Dev is the best next external fit because it has SQLite variants,
  professional/business-like databases, question/evidence/SQL records, and a
  smaller development subset.
- Spider2-DBT is relevant after the eval harness is stable because it is closer
  to our dbt/DuckDB/Wren setup.
- Spider 1.0 is useful as a classical baseline but is less business-realistic.
- Gretel synthetic_text_to_sql is useful for broad synthetic coverage but should
  not be the primary business validation benchmark.

Detailed notes are in:

```text
docs/data_subagent_eval_dataset_research.md
```

## 10. Documentation Update Protocol

When a future session changes behavior, update this document with:

- new command or result
- changed architecture decision
- new trace ID for a representative run
- new pitfall or workaround
- test result after the change

Do not treat this file as polished public docs. Treat it as engineering memory.
