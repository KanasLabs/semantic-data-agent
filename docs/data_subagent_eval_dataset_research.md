# Data Subagent Eval Dataset Research

Date: 2026-07-09

This document records candidate open-source text-to-SQL datasets for validating
the Data Subagent MVP.

## Goal

We need an eval path that can answer:

- Does the MVP generate executable SQL through Wren?
- Does Wren dry-plan / dry-run catch errors before execution?
- Does DeepSeek repair failed SQL when Wren returns useful errors?
- Do traces capture enough evidence for later improvement?
- Which prompt, Wren context, NL-SQL examples, or guardrail changes improve
  measurable behavior?

Because WrenAI is mandatory in this project, any external benchmark must either:

1. be converted into a Wren project, or
2. be used only as a source of ideas for manually authored Wren-backed evals.

## Candidate Datasets

### 1. BIRD Mini-Dev / BIRD-SQL

Best fit for the next MVP eval.

Why:

- BIRD is explicitly designed around database-grounded text-to-SQL.
- It includes real-world-ish databases, question-SQL pairs, external knowledge
  evidence, and execution-based evaluation.
- BIRD Mini-Dev is much smaller than full BIRD and has SQLite variants, which is
  better for local MVP iteration.
- The project page says Mini-Dev was created for efficient and cost-effective
  development cycles.

Useful facts from current research:

- BIRD full dataset: 12,751 question-SQL pairs, 95 big databases, 33.4 GB total,
  37+ professional domains.
- BIRD Mini-Dev V2: 780 instances; 500 are high-quality SELECT-only instances
  selected from original BIRD-Dev, plus 270 newer instances with SELECT and CRUD
  coverage across 18 new end-user-level databases.
- Mini-Dev includes SQLite, MySQL, and PostgreSQL variants.
- Mini-Dev records include `db_id`, `question`, `evidence`, and `SQL`.
- The public Mini-Dev repository documents a Hugging Face dataset path
  `birdsql/bird_mini_dev` and shows `mini_dev_sqlite`, `mini_dev_mysql`, and
  `mini_dev_pg` splits.
- The repository README states the SQLite data includes database folders with
  `database_description` CSV files and SQLite database contents, plus
  `mini_dev_sqlite.json` containing `db_id`, `question`, `evidence`, and `SQL`.

Recommendation:

Start with BIRD Mini-Dev SQLite, but only use SELECT-only cases at first. Pick
one or two business-like databases, such as financial / debit card / schools,
and convert them into Wren projects.

Risks:

- Some BIRD data can contain noisy or corrected examples across releases.
- Full BIRD is too large for MVP.
- Wren project generation is required before our Data Subagent can use it.
- A 2026 paper reports high annotation-error rates in BIRD Mini-Dev and
  Spider2-Snow subsets. Treat benchmark failures as investigation leads rather
  than automatic product failures; inspect repeated failure clusters and
  compare predicted/gold execution results before changing prompts or Wren
  context.

### 2. Spider 2.0 / Spider2-DBT

Best fit after the MVP eval harness is stable.

Why:

- Spider 2.0 targets real-world enterprise text-to-SQL workflows.
- It includes complex cloud/local databases, long metadata, multiple SQL
  dialects, and repo-level workflows.
- Spider2-DBT is especially relevant because our current jaffle setup already
  came through dbt and Wren can import dbt context.

Useful facts from current research:

- Spider 2.0 has 632 real-world enterprise workflow problems.
- Databases often contain more than 1,000 columns and use systems such as
  BigQuery and Snowflake.
- Spider2-DBT has 68 DuckDB/DBT tasks and is designed for quick benchmarking.

Recommendation:

Use Spider2-DBT as Phase 2. It is closer to our Wren/dbt route than the full
Spider 2.0 cloud variants.

Risks:

- Full Spider 2.0 is too heavy for the current MVP.
- Some settings require BigQuery/Snowflake or external hosted data.
- Tasks can involve multi-query workflows that exceed the current
  single-question/single-SQL MVP.

### 3. Spider 1.0

Useful as a classical baseline, but not ideal for business MVP validation.

Why:

- Very well-known, easy to reason about, and broad.
- It contains 10,181 questions and 5,693 unique SQL queries over 200 databases
  across 138 domains.

Limitations:

- It is older and more academic.
- It does not stress real enterprise context layers as much as BIRD or Spider
  2.0.
- It still requires converting databases/schema into Wren projects.

Recommendation:

Use only as a later compatibility baseline, not as the next step.

### 4. Gretel synthetic_text_to_sql

Useful for generating many small synthetic cases, not as the primary benchmark.

Why:

- Apache-2.0 dataset on Hugging Face.
- 105,851 records, 100 domains/verticals.
- Includes SQL context with table/view create statements and inserts.
- Covers analytics/reporting, joins, aggregations, window functions, and more.

Limitations:

- Synthetic data is useful for breadth but weaker as business validation.
- Records are isolated examples, not necessarily reusable multi-table business
  databases with persistent Wren projects.

Recommendation:

Use later for stress-testing SQL patterns or generating small local Wren eval
fixtures. Do not use it as the primary MVP benchmark.

### 5. LiveSQLBench / BIRD-Interact

Promising but too heavy for now.

Why:

- These aim at more realistic interaction, external knowledge, business rule
  drift, and test-case-driven validation.

Limitations:

- More agentic and interactive than our current MVP.
- Best used after we have eval harness, Wren project generation, and trace
  analysis in place.

Recommendation:

Track as future direction for multi-turn clarification and ReAct evaluation.

## Recommended Evaluation Roadmap

### Phase E0: Internal Jaffle Eval

Before importing external datasets, formalize a local jaffle eval set:

```text
5-10 questions
expected SQL features
expected columns
expected row counts or result checks
expected chart type where relevant
```

This validates our eval runner and trace recording without introducing Wren
project generation complexity.

### Phase E1: BIRD Mini-Dev SQLite Subset

Use a small SELECT-only subset:

```text
1-2 databases
10-30 cases
SQLite source DBs
Wren project per DB
questions + evidence + gold SQL
execution-match scoring
```

This is the recommended next external benchmark step.

### Phase E2: Spider2-DBT

Use dbt/DuckDB tasks once the eval harness can handle multiple Wren projects.

### Phase E3: Larger / Interactive Benchmarks

Evaluate BIRD-Interact or LiveSQLBench only after the MVP supports clarification
and richer tool loops.

## Proposed Eval Result Schema

Store eval cases separately from runtime traces.

Suggested paths:

```text
data/evals/cases/jaffle_smoke.jsonl
data/evals/cases/bird_mini_dev_subset.jsonl
data/evals/runs/YYYYMMDD-HHMMSS-<suite>.jsonl
data/evals/reports/YYYYMMDD-HHMMSS-<suite>.md
```

Suggested case schema:

```json
{
  "eval_id": "jaffle_001",
  "dataset": "jaffle_shop",
  "db_id": "jaffle_shop",
  "question": "How many orders are there?",
  "evidence": "",
  "expected_sql_features": ["count", "orders"],
  "expected_columns": ["order_count"],
  "expected_row_count": 1,
  "expected_result": [{"order_count": 99}],
  "wren_project_dir": "data/wren/jaffle_wren_project"
}
```

Suggested run record schema:

```json
{
  "eval_id": "jaffle_001",
  "dataset": "jaffle_shop",
  "db_id": "jaffle_shop",
  "status": "pass",
  "review_status": "auto_pass",
  "trace_id": "trace_xxx",
  "final_sql": "SELECT COUNT(*) AS order_count FROM orders",
  "gold_sql": "",
  "gold_sql_check": {
    "guardrail_ok": true,
    "dry_run_ok": true,
    "execute_ok": true,
    "gold_row_count": 1,
    "execution_match": true,
    "needs_triage": false,
    "error": null
  },
  "metrics": {
    "dry_run_ok": true,
    "execution_match": true,
    "sql_feature_match": true,
    "row_count_match": true,
    "repair_count": 0
  },
  "failure_reason": null
}
```

## How Eval Should Drive Modification

The improvement loop should be explicit:

```text
eval run
-> JSONL run records
-> failure report
-> group failures by cause
-> decide change type
   - prompt change
   - Wren knowledge/rule/example change
   - SQL guardrail change
   - adapter/parser change
   - clarification behavior change
-> run regression
-> update progress docs
```

Do not modify prompts or Wren context from a single failure unless it is clearly
structural. Prefer grouping repeated failures first.

## Current Recommendation

The eval runner is implemented on jaffle_shop, and BIRD Mini-Dev SQLite is now
the first external benchmark path.

Implemented internal eval:

```text
src/data_subagent/eval_runner.py
src/data_subagent/cli.py eval --suite data/evals/cases/jaffle_smoke.jsonl
data/evals/cases/jaffle_smoke.jsonl
docs/eval report output
```

Implemented BIRD setup:

```text
scripts/prepare_bird_mini_dev_subset.ps1 or .py
scripts/prepare_sqlite_wren_project.py
scripts/setup_bird_mini_dev_eval.py
data/evals/cases/bird_mini_dev_debit_card_specializing.jsonl
data/wren/bird_debit_card_specializing_wren_project/
```

The BIRD setup should be scripted, not manually assembled.

Current local scaffold:

- `scripts/prepare_bird_mini_dev_subset.py` converts local BIRD JSON records
  into Data Subagent eval JSONL.
- `scripts/prepare_sqlite_wren_project.py` converts a local SQLite database
  into a DuckDB-backed Wren project and optional Wren profile.
- `scripts/setup_bird_mini_dev_eval.py` combines local/Hugging Face source
  discovery, SELECT-only eval JSONL creation, SQLite-to-DuckDB conversion, Wren
  project generation, and Wren profile creation.
  It also supports the BIRD OSS zip via `--download-oss`; the package is about
  764 MB compressed based on a 2026-07-09 HEAD check.
- The Data Subagent CLI supports `--wren-project-dir`, `--wren-home`, and
  `--wren-bin` runtime overrides for running non-jaffle Wren projects.
- Eval records preserve `gold_sql`. A failing external benchmark case with
  `gold_sql` is marked `review_status: needs_triage` so benchmark noise does
  not automatically drive prompt/context changes.
- Eval also executes read-only `gold_sql` through Wren and records
  `gold_sql_check`. A case can be automatic `status: pass` but still
  `review_status: needs_triage` if predicted rows and gold rows differ or if the
  gold SQL cannot run.

## First Real BIRD Smoke Result

Run on 2026-07-09:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\bird_mini_dev_debit_card_specializing.jsonl `
  --suite-name bird_mini_dev_debit_card_specializing_smoke5 `
  --wren-project-dir data\wren\bird_debit_card_specializing_wren_project `
  --wren-home data\wren\home `
  --limit 5
```

Result:

```text
run_id: 20260709-165501-bird_mini_dev_debit_card_specializing_smoke5
total: 5
passed: 4
failed: 1
duration_ms: 93138
```

Observed categories:

- auto-pass with gold execution match: 2 cases
- runtime pass but gold execution mismatch: 2 cases, marked
  `review_status: needs_triage`
- failed SQL generation due empty/unparsable DeepSeek JSON: 1 case

Important interpretation:

- This is a smoke test, not a final score.
- The minimal generated Wren project lacks curated business context, synonyms,
  and examples.
- Gold mismatch must be triaged manually because external labels can be noisy
  and because SQL that differs from gold can still be semantically acceptable
  in some cases.

## Sources

- BIRD-SQL project: https://bird-bench.github.io/
- BIRD Mini-Dev repository: https://github.com/bird-bench/mini_dev
- BIRD Mini-Dev Hugging Face dataset: https://huggingface.co/datasets/birdsql/bird_mini_dev
- Annotation-error paper: https://arxiv.org/abs/2601.08778
- Spider 2.0 project: https://spider2-sql.github.io/
- Spider 1.0 project: https://yale-lily.github.io/spider
- Gretel synthetic text-to-SQL: https://huggingface.co/datasets/gretelai/synthetic_text_to_sql
