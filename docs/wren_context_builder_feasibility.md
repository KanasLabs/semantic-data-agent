# WrenAI Context Builder Feasibility

Last updated: 2026-07-10

This document records the first feasibility pass for the separate WrenAI
Context Builder / MDL Onboarding Tool workstream.

## 1. Scope

The Context Builder is upstream of the Data Subagent runtime.

It should turn a database or dbt project into Wren-consumable artifacts:

```text
database / dbt project
-> Wren-native import where available
-> Wren project / MDL / profile
-> rules / examples / knowledge drafts
-> validate / build / dry-run
-> onboarding report
-> smoke eval JSONL for the existing Data Subagent eval runner
```

It must not be mixed into `DataSubagent`. The runtime consumes Wren context; it
does not own onboarding or semantic-layer construction.

## 2. Installed Wren CLI Check

Local Wren CLI:

```powershell
.\.venv-wren\Scripts\wren.exe --version
```

Result:

```text
wrenai 0.12.0
```

Top-level commands include:

```text
query, dry-plan, dry-run, context, cube, utils, skills, memory, profile
```

## 3. Native Import Capability

Verified command:

```powershell
.\.venv-wren\Scripts\wren.exe context import --help
```

Important output:

```text
Usage: wren context import [OPTIONS] SOURCE
Import source (currently: dbt)
--project-dir
--profiles-path
--profile
--target
--dry-run
--force
```

Verified command:

```powershell
.\.venv-wren\Scripts\wren.exe profile import --help
```

Important output:

```text
Usage: wren profile import [OPTIONS] SOURCE
Import source (currently: dbt)
--project-dir
--profiles-path
--profile
--target
--name
--activate / --no-activate
```

Conclusion:

- In the installed CLI, native `context import` and `profile import` are dbt
  import paths.
- Do not represent arbitrary SQLite / DuckDB / Postgres onboarding as native
  Wren import unless a later Wren version adds it and it is verified again.

## 4. Other Wren-Supported Onboarding Inputs

`wren context init --help` shows:

```text
--from-mdl
--from-osi
--data-source
--semantic-model
--empty
```

`wren context validate --help` and `wren context build --help` also support:

```text
--from-osi
--data-source
--semantic-model
```

This means OSI can be used as a source for validate/build, and `context init`
can migrate from OSI or existing MDL JSON. This is separate from automatic
database introspection.

## 5. Wren Agent Skill Guidance

Verified command:

```powershell
.\.venv-wren\Scripts\wren.exe skills list
```

Relevant skills:

```text
onboarding
generate-mdl
usage
enrich-context
dlt-connector
```

Verified command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv-wren\Scripts\wren.exe skills get generate-mdl
```

The installed `generate-mdl` workflow says the agent should:

- detect an existing Wren project
- establish connection and scope
- discover schema using SQLAlchemy, database drivers, MCP connectors, or SQL
- normalize raw DB types with `wren.type_mapping` or `wren utils parse-type`
- scaffold with `wren context init`
- write model YAML and relationships
- run `wren context validate`
- run `wren context build`
- run a smoke query
- optionally run `wren memory index`

Conclusion:

- Wren expects arbitrary database onboarding to be agent/script-assisted schema
  discovery plus Wren validation/build.
- Wren provides project structure, type normalization, profile handling,
  validation, build, dry-plan, dry-run, query, and skills.
- The Context Builder should wrap this flow reproducibly, not invent a separate
  semantic layer.

## 6. Connection Info Support

Verified command:

```powershell
.\.venv-wren\Scripts\wren.exe docs connection-info --format json
```

Observed data sources include:

```text
athena, bigquery, canner, clickhouse, datafusion, databricks, doris,
duckdb, gcs_file, local_file, minio_file, mssql, mysql, oracle,
postgres, redshift, s3_file, snowflake, spark, trino, connection_url
```

This should drive Context Builder profile template/report generation. Do not
hardcode credential field names where Wren can introspect them.

## 7. Validate / Build / Dry-Run Smoke

Input Wren project:

```text
data/wren/jaffle_wren_project
```

Wren home:

```text
data/wren/home
```

Command:

```powershell
$env:WREN_HOME = (Resolve-Path 'data\wren\home').Path
$env:PYTHONIOENCODING='utf-8'
.\.venv-wren\Scripts\wren.exe context validate
```

Result:

```text
3 warning(s), 0 errors.
```

Warnings were missing descriptions for:

```text
stg_customers
stg_orders
stg_payments
```

Command:

```powershell
$env:WREN_HOME = (Resolve-Path 'data\wren\home').Path
.\.venv-wren\Scripts\wren.exe context build
```

Result:

```text
Built: 5 models, 0 views -> data/wren/jaffle_wren_project/target/mdl.json
```

Command:

```powershell
$env:WREN_HOME = (Resolve-Path 'data\wren\home').Path
.\.venv-wren\Scripts\wren.exe dry-run --sql "select count(*) as order_count from orders"
```

Result:

```text
OK
```

Pitfall:

- Without `PYTHONIOENCODING=utf-8`, `context validate` can fail on Windows GBK
  consoles while printing warning symbols.
- The command reached warning output, then failed with `UnicodeEncodeError`.
- Set `PYTHONIOENCODING=utf-8` for Wren subprocesses in the builder.

## 8. Existing Repo Script Reuse

Current script:

```text
scripts/prepare_sqlite_wren_project.py
```

Reusable for a generic database fallback path:

- SQLite schema introspection with `PRAGMA table_info`
- SQLite FK introspection with `PRAGMA foreign_key_list`
- SQLite to DuckDB conversion
- DuckDB `sqlite_scanner` bulk import when available
- WAL cleanup / `CHECKPOINT`
- Wren project file generation
- DuckDB profile writing

Status after the 2026-07-10 Wren-native pass:

- Done: SQLite column type normalization now uses
  `wren.type_mapping.parse_type(raw_type, "sqlite")`, with a local fallback only
  for non-Wren developer environments or empty/unparseable types.
- Done: Context Builder SQLite onboarding now scaffolds the target project with
  `wren context init --empty` before writing generated model metadata.
- Done: SQLite relationship generation now skips FK rows with missing child or
  parent columns, preventing bad join conditions such as
  `"yearmonth"."CustomerID" = "customers"."None"`.
- Done: Context Builder `inspect` reports incomplete SQLite FK metadata as
  warnings without generating DuckDB files, Wren project files, or Wren home
  state.
- Still needed: Separate generic schema onboarding from BIRD benchmark
  assumptions.

Benchmark-only / dataset glue:

```text
scripts/setup_bird_mini_dev_eval.py
scripts/prepare_bird_mini_dev_subset.py
```

Reusable ideas:

- local source discovery
- SELECT-only smoke case extraction
- JSONL eval case writing
- next-command reporting

But BIRD-specific logic should not become the generic Context Builder API.

## 9. Feasibility Decision

Feasible MVP paths:

### Path A: dbt-native

Use Wren CLI directly:

```text
wren profile import dbt ...
wren context import dbt ...
wren context validate
wren context build
wren dry-run --sql ...
```

The builder should orchestrate these commands, capture output, and write an
onboarding report.

### Path B: database fallback

For SQLite / DuckDB / other databases where no native Wren import is verified:

```text
inspect schema with driver / SQLAlchemy / DB-specific SQL
normalize types with Wren
wren context init --empty
write Wren model YAML and relationships
wren profile add or write project-local WREN_HOME profile
wren context set-profile
wren context validate
wren context build
wren dry-run smoke SQL
emit report and smoke eval JSONL
```

This is Wren-assisted onboarding, not native Wren automatic DB import.

## 10. Recommended MVP CLI

Package:

```text
src/data_subagent_context_builder/
```

Implemented first cut on 2026-07-09:

```text
src/data_subagent_context_builder/cli.py
src/data_subagent_context_builder/codex_runtime.py
src/data_subagent_context_builder/skill_onboarding.py
src/data_subagent_context_builder/sqlite_onboarding.py
src/data_subagent_context_builder/wren_cli.py
src/data_subagent_context_builder/report.py
src/data_subagent_context_builder/smoke_eval.py
tests/test_context_builder.py
tests/test_context_builder_codex_runtime.py
tests/test_context_builder_skill_onboarding.py
tests/test_context_builder_smoke_eval.py
```

Implemented commands:

```powershell
python -m data_subagent_context_builder.cli inspect ...
python -m data_subagent_context_builder.cli generate-from-db ...
python -m data_subagent_context_builder.cli generate-schema-draft ...
python -m data_subagent_context_builder.cli validate ...
python -m data_subagent_context_builder.cli enrich-with-codex ...
python -m data_subagent_context_builder.cli make-smoke-eval ...
```

`inspect` is the read-only SQLite schema fact path. It prints a JSON schema
report and can write JSON / Markdown artifacts for Wren `generate-mdl`
onboarding, Codex prompts, and human semantic review. It also surfaces
incomplete SQLite FK metadata as warnings.

The current implementation makes `generate-from-db` the skill-first path. For
SQLite it reuses SQLite/DuckDB conversion only as factual substrate preparation,
then writes `onboarding/schema_manifest.json` and a Codex prompt that tells the
agent to inspect Wren's installed `generate-mdl` skill before generating MDL.
It does not write model YAML by default.

When `--execute` is passed, `generate-from-db` now runs a bounded outer Codex
repair loop. Each round invokes `codex exec`, then the builder itself runs Wren
`context validate`, `context build`, and optional `dry-run`. Failed Wren command
outputs are written into the next repair prompt until the project passes or
`--max-repair-rounds` is exhausted. This makes Wren validation a tool-level
acceptance check instead of relying only on Codex's final message.

`generate-schema-draft` is the explicit deterministic fallback. It writes
schema-level Wren YAML from database metadata and validates/builds it with Wren.
Use it for smoke/debug bootstrap only, not as the preferred semantic-layer
generation path.

The implementation does not yet generalize database introspection to
Postgres/MySQL/SQLAlchemy.

`enrich-with-codex` is an optional background/onboarding agent hook. It prepares
a Codex prompt that instructs the agent to read the project docs, inspect Wren's
installed `generate-mdl` skill, improve only the target Wren project, and rerun
Wren validate/build/dry-run. It is prompt-only by default; `--execute` is
required before it invokes `codex exec`.

`make-smoke-eval` emits Data Subagent eval JSONL from Wren model metadata. The
first implementation intentionally generates conservative count-row cases by
default, plus an optional relationship smoke case. These cases check onboarding
health, not full business semantic correctness.

Commands:

```powershell
python -m data_subagent_context_builder.cli inspect `
  --sqlite-path data\source.sqlite `
  --output docs\source_schema_report.md `
  --json-output data\tmp\source_schema_report.json

python -m data_subagent_context_builder.cli import-dbt `
  --dbt-project path\to\dbt_project `
  --profiles-path path\to\profiles.yml `
  --project-dir data\wren\<project> `
  --wren-home data\wren\home

python -m data_subagent_context_builder.cli generate-from-db `
  --sqlite-path data\source.sqlite `
  --project-name <project> `
  --project-dir data\wren\<project> `
  --duckdb-path data\wren\<project>.duckdb `
  --wren-home data\wren\home `
  --prompt-output data\wren\<project>\onboarding\generate_mdl_prompt.md

python -m data_subagent_context_builder.cli generate-schema-draft `
  --sqlite-path data\source.sqlite `
  --project-name <project> `
  --project-dir data\wren\<project>_draft `
  --duckdb-path data\wren\<project>_draft.duckdb `
  --wren-home data\wren\home `
  --smoke-sql "select count(*) from <model>"

python -m data_subagent_context_builder.cli validate `
  --project-dir data\wren\<project> `
  --wren-home data\wren\home `
  --smoke-sql "select count(*) from <model>"

python -m data_subagent_context_builder.cli make-smoke-eval `
  --project-dir data\wren\<project> `
  --output data\evals\cases\<project>_smoke.jsonl
```

The first implementation favors SQLite/DuckDB only for substrate preparation.
The MDL authoring path should stay unified around Wren's `generate-mdl` skill
plus Codex/agent execution.

## 10.1 Implementation Verification

Inspect CLI smoke against BIRD Mini-Dev `debit_card_specializing`:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli `
  --project-root . `
  inspect `
  --sqlite-path data\external\bird_mini_dev\raw\minidev\minidev\MINIDEV\dev_databases\debit_card_specializing\debit_card_specializing.sqlite `
  --project-name bird_debit_card_specializing `
  --output data\tmp\context_builder_inspect_smoke\schema_report.md `
  --json-output data\tmp\context_builder_inspect_smoke\schema_report.json
```

Result:

```text
table_count: 5
relationship_count: 0
warnings: 2 incomplete SQLite FK metadata warnings
```

The previous invalid generated relationship condition is now guarded:

```text
"yearmonth"."CustomerID" = "customers"."None"
```

Unit tests:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest tests.test_context_builder
```

Result:

```text
Ran 2 tests
OK
```

Full test suite:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 22 tests
OK
```

After adding the Codex enrichment scaffold:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest tests.test_context_builder_codex_runtime tests.test_context_builder
```

Result:

```text
Ran 5 tests
OK
```

Prompt-only CLI smoke:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli `
  --project-root . `
  enrich-with-codex `
  --project-dir data\wren\jaffle_wren_project `
  --wren-home data\wren\home `
  --smoke-sql "select count(*) as order_count from orders" `
  --instructions "Add concise model descriptions only if missing." `
  --prompt-output data\tmp\codex_enrichment_prompt_smoke\prompt.md
```

Result:

```text
ok: true
executed: false
prompt_output_path: data/tmp/codex_enrichment_prompt_smoke/prompt.md
```

Smoke eval unit tests:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest tests.test_context_builder_smoke_eval
```

Result:

```text
Ran 2 tests
OK
```

Smoke eval CLI check against the jaffle Wren project:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli `
  --project-root . `
  make-smoke-eval `
  --project-dir data\wren\jaffle_wren_project `
  --output data\tmp\jaffle_context_builder_smoke.jsonl `
  --dataset jaffle_shop `
  --db-id jaffle_shop `
  --max-cases 3
```

Result:

```text
ok: true
emitted: 3
eval_ids:
- jaffle_shop_customers_count
- jaffle_shop_orders_count
- jaffle_shop_stg_customers_count
```

Outer Codex repair loop unit verification:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest tests.test_context_builder_skill_onboarding
```

Result:

```text
Ran 4 tests
OK
```

The repair-loop test simulates a failed outer `context validate`, verifies that
the second Codex prompt includes the structured Wren validation error, and
checks that round prompts / validation artifacts are written under
`<wren_project>/onboarding/`.

Real Wren smoke on a temporary SQLite fixture:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli `
  --project-root . `
  generate-from-db `
  --sqlite-path data\tmp\context_builder_smoke_<id>\sales.sqlite `
  --project-name smoke_sales `
  --project-dir data\tmp\context_builder_smoke_<id>\wren_project `
  --duckdb-path data\tmp\context_builder_smoke_<id>\smoke_sales.duckdb `
  --wren-home data\tmp\context_builder_smoke_<id>\wren_home `
  --smoke-sql "select count(*) as order_count from orders" `
  --report-path data\tmp\context_builder_smoke_<id>\onboarding_report.md
```

Result:

```text
ok: true
models: customers, orders
relationship_count: 1
context_validate: Valid - 2 models, 0 views, 1 relationships.
context_build: Built target/mdl.json
dry_run: OK
```

Re-verified on 2026-07-10 after switching the default path to skill-first:

```text
generate-from-db:
ok: true
mode: skill
context_init: wren context init --empty --force -> OK
schema_manifest_path: wren_project/onboarding/schema_manifest.json
codex.executed: false
models/orders/metadata.yml: not written by default
```

Explicit draft fallback remains available:

```text
type normalization: INTEGER -> INT, REAL -> FLOAT, DATETIME -> DATETIME
context_validate: Valid - 2 models, 0 views, 1 relationships.
context_build: Built 2 models, 0 views
dry_run: OK
```

## 11. Sources Checked

Local commands:

- `wren --version`
- `wren context import --help`
- `wren profile import --help`
- `wren context init --help`
- `wren context validate --help`
- `wren context build --help`
- `wren docs connection-info --format json`
- `wren skills list`
- `wren skills get onboarding`
- `wren skills get generate-mdl`
- `wren skills get usage`

Official references:

- WrenAI GitHub: https://github.com/Canner/WrenAI
- Wren installation docs: https://github.com/Canner/WrenAI/blob/main/docs/core/get_started/installation.md
- Wren connection guide: https://github.com/Canner/WrenAI/blob/main/docs/core/guides/connect.md
- Wren quickstart: https://github.com/Canner/WrenAI/blob/main/docs/core/get_started/quickstart.md
- Wren model guide: https://github.com/Canner/WrenAI/blob/main/docs/core/guides/model.md
- Wren dbt integration guide: https://github.com/Canner/WrenAI/blob/main/docs/core/guides/dbt-integration.md
