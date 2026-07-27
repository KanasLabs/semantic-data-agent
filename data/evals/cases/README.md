# Eval Cases

This directory stores JSONL eval case definitions for the Data Subagent.

Some cases are adapted from third-party benchmarks. In particular, committed
BIRD Mini-Dev cases and audits remain under CC BY-SA 4.0 and are not relicensed
under the repository's MIT license. See [`../../../THIRD_PARTY_NOTICES.md`](../../../THIRD_PARTY_NOTICES.md).

Current suite:

```text
jaffle_smoke.jsonl
bird_mini_dev_debit_card_specializing.jsonl
```

Run it with:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval --suite data\evals\cases\jaffle_smoke.jsonl --suite-name jaffle_smoke --limit 20
```

For `eval`, `--limit` means number of cases. Use `--query-limit` when you need
to change the SQL result row limit per case.

## External Dataset Conversion

BIRD Mini-Dev should be converted into this format after downloading the dataset
locally.

Example:

```powershell
.\.venv-wren\python.exe scripts\prepare_bird_mini_dev_subset.py `
  --input data\external\bird_mini_dev\mini_dev_sqlite.json `
  --output data\evals\cases\bird_mini_dev_subset.jsonl `
  --db-id debit_card_specializing `
  --limit 30
```

This only prepares eval case metadata. To actually run the suite through the
Data Subagent, the selected BIRD database still needs a corresponding Wren
project and Wren profile.

If the selected external dataset is a SQLite database, generate a DuckDB-backed
Wren project first:

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

Then run the suite with a Wren project override:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\bird_mini_dev_debit_card_specializing.jsonl `
  --suite-name bird_mini_dev_debit_card_specializing_smoke5 `
  --wren-project-dir data\wren\bird_debit_card_specializing_wren_project `
  --wren-home data\wren\home `
  --limit 5
```

The combined BIRD setup script performs both steps when the source files are
already local:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --source-dir data\external\bird_mini_dev\raw `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

If Hugging Face network access is available, the same script can attempt to
download first:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --download `
  --source-dir data\external\bird_mini_dev\raw `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

If Hugging Face is unavailable, the BIRD Mini-Dev README links an OSS zip. The
script has a shortcut for it:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --download-oss `
  --source-dir data\external\bird_mini_dev\raw `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

The OSS package was checked on 2026-07-09 and is about 764 MB compressed.

Latest real BIRD smoke result on 2026-07-09:

```text
run_id: 20260709-165501-bird_mini_dev_debit_card_specializing_smoke5
total: 5
passed: 4
failed: 1
duration_ms: 93138
report_path: data/evals/reports/20260709-165501-bird_mini_dev_debit_card_specializing_smoke5.md
```

Interpret this as a first triage sample, not a final model score. Two runtime
passes still need review because predicted and gold execution results differ.

## Case Schema

Minimal:

```json
{
  "eval_id": "jaffle_001",
  "dataset": "jaffle_shop",
  "db_id": "jaffle_shop",
  "question": "How many orders are there?",
  "expected_sql_contains": ["count", "orders"],
  "expected_row_count": 1,
  "expected_any_values": [99]
}
```

Optional fields currently understood by the eval runner:

```text
evidence
gold_sql
expected_status
expected_sql_not_contains
expected_first_row_contains
expected_any_row_contains
expected_any_values
constraints
```

External benchmark cases should keep `gold_sql`, but the runner does not score
exact SQL equivalence. Different SQL can be correct if execution and business
semantics match.

When a case with `gold_sql` fails automatic checks, the run report marks it as:

```text
review_status: needs_triage
```

The runner also dry-runs and executes read-only `gold_sql` through the active
Wren project. The run record stores:

```text
gold_sql_check.guardrail_ok
gold_sql_check.dry_run_ok
gold_sql_check.execute_ok
gold_sql_check.gold_row_count
gold_sql_check.execution_match
gold_sql_check.needs_triage
gold_sql_check.error
```

If automatic checks pass but predicted rows and gold rows differ, the case can
still be `status: pass` with `review_status: needs_triage`. The report lists
these cases under `Review Details`.

Triage rule:

- do not change prompts or Wren context from one failed gold-SQL case
- inspect Wren dry-run / execution first
- compare predicted and gold results where possible
- group repeated failures by cause before modifying the system
