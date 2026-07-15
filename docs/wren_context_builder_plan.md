# WrenAI Context Builder / MDL Onboarding Tool Plan

Last updated: 2026-07-15

This document defines a separate upstream workstream from the Data Subagent MVP.

Latest feasibility notes are in:

```text
docs/wren_context_builder_feasibility.md
```

The next core product goal is the conversational candidate revision loop:

```text
candidate Context
-> user natural-language business feedback
-> Codex revises Context with Wren skill
-> Builder versions, validates, tests, and produces semantic diff
-> user approves semantic changes
-> explicit publish through Context Registry
```

This goal is specified in:

```text
docs/context_builder_conversational_revision_plan.md
```

Human review should mean confirming business truth and approving semantic
changes, not manually implementing Wren YAML. `enrich-with-codex` is only the
the lower-level execution precursor. R0 implements versioned candidate/revision
records, persistent clarification and approval HITL, provenance, transition
guards, and semantic-diff/review-packet contracts. R1 implements
`register-candidate` and Codex-driven `revise-candidate` over isolated copied
workspaces with outer Wren acceptance. R2 adds structured clarification output,
automatic HITL task creation, semantic diff, generated smoke eval, and configured
regression execution. R3 adds answer/resume, review packets, explicit
approve/reject, separate publish, publication history, and rollback. Main Agent
consumption of the published pointer remains pending.

## 0. Current Implementation Snapshot

This plan is no longer only a proposal. The SQLite/DuckDB skill-first MVP is
implemented and verified.

Primary path:

```text
SQLite database
-> inspect schema and record warnings
-> convert SQLite data to a DuckDB runtime substrate
-> initialize an empty Wren project and write a DuckDB profile
-> write onboarding/schema_manifest.json as seed evidence
-> run Codex with Wren's installed generate-mdl skill
-> run outer Wren validate / build / optional dry-run
-> feed structured Wren errors back to Codex for bounded repair
-> write final onboarding report and per-round artifacts
```

Implemented CLI commands:

```text
inspect
generate-from-db
generate-schema-draft
validate
enrich-with-codex
make-smoke-eval
starrocks-query
generate-from-starrocks
```

Important decisions:

- `generate-from-db` is the first-line path and defaults to `mode=skill`.
- Wren's installed `generate-mdl` skill is the authority for MDL authoring.
- The generated prompt is subordinate to the Wren skill. The manifest is seed
  evidence, and Codex may inspect DuckDB directly when the skill requires it.
- The outer builder owns the final pass/fail result even if Codex also runs
  validate/build/dry-run internally.
- Deterministic YAML generation remains available only through
  `generate-schema-draft` or `generate-from-db --mode draft`.
- The current component is a bounded agentic workflow tool, not a full
  Context Builder subagent. It does not independently choose strategy, ask
  semantic clarification questions, prioritize enrichment, or score readiness.

Real verification on BIRD Mini-Dev `debit_card_specializing`:

```text
Codex round 0: success
Wren validate: 5 models, 4 relationships
Wren build: target/mdl.json generated
Wren dry-run: OK
repair rounds used: 0
full unit suite at that stage: 34 tests passed
```

StarRocks controlled-query foundation verified on 2026-07-14:

```text
Codex-callable primitive: starrocks-query
protocol: MySQL through mysqlclient / MySQLdb
allowed SQL: scoped SHOW / DESCRIBE / SELECT / WITH / EXPLAIN
controls: catalog/database allowlist, timeout, max rows, single statement
evidence: JSONL records without result values by default
secret handling: password from environment only
real local fixture: discovery and limited sample queries passed
write attempt: rejected before execution
latest full unit suite: 50 tests passed
```

This is intentionally a safe tool primitive, not a deterministic StarRocks
schema crawler. Codex should decide which discovery queries to run while
following Wren's `generate-mdl` skill. The outer Builder owns policy enforcement
and evidence recording. The existing StarRocks fixture has already verified
Wren's `doris` datasource as the runtime compatibility path.

Implemented StarRocks skill-first path:

```text
Builder initializes empty Wren project
-> Builder imports/binds environment-backed Wren doris profile
-> Codex reads generate-mdl skill
-> Codex calls starrocks-query for discovery and relationship checks
-> Codex writes discovery_snapshot and schema_manifest
-> Codex writes candidate Wren Context Layer
-> Builder validates Wren validate/build/dry-run and discovery artifacts
-> failed acceptance can enter the bounded repair loop
```

Real local fixture result: 24 controlled queries, 2 models, 1 evidence-backed
`orders.customer_id -> customers.customer_id` relationship, valid build, and
successful dry-runs. The first process wrapper timed out after Codex completed
because a Wren memory subprocess retained captured pipes; the prompt now forbids
memory indexing and `CodexCliRunner` uses file-backed output with structured
process-tree timeout handling.

Real TPC-H SF 0.01 result: 69 controlled queries, 8 models, 8 validated
relationships, valid build, successful single-table/three-table/composite-key
queries, and a 5/5 Data Subagent smoke eval. The candidate remains reviewable
rather than business-ready because currencies, units, code meanings, and date
policies were not inferred.

Still not implemented:

- dbt-native import orchestration as a Context Builder CLI command
- automatic smoke-eval execution after successful onboarding
- a strategy/decision layer that would make this a true subagent
- generic Postgres/MySQL onboarding
- automatic business-semantic completeness or quality scoring
- automatic smoke-eval generation/execution inside `generate-from-starrocks`
- change-request-aware business-semantic smoke generation
- Main Agent routing through the published Context Registry pointer
- published-candidate health monitoring and automated rollback policy

Implemented R0 lifecycle foundation:

```text
src/data_subagent_context_builder/revision_store.py
tests/test_context_builder_revision_store.py
```

The filesystem store defines candidate/revision states, atomic records,
expected-version/status checks, natural-language change requests, provenance,
separate clarification and approval tasks, and approval/resume gates. It is a
Builder-owned control plane; Codex does not write these records directly.

Implemented R1 revision engine:

```text
src/data_subagent_context_builder/revision_engine.py
tests/test_context_builder_revision_engine.py
```

`register-candidate` imports an existing Wren project as a draft Registry
candidate. `revise-candidate` creates a new version under the Registry, copies
the base without generated caches, runs Codex with only the candidate project as
its writable working directory, reuses bounded repair plus independent Wren
validate/build/dry-run, and records `REVIEW_REQUIRED` or `VALIDATION_FAILED`
without modifying the base.

Implemented R2 acceptance layer:

```text
src/data_subagent_context_builder/semantic_diff.py
src/data_subagent_context_builder/revision_eval.py
tests/test_context_builder_semantic_diff.py
tests/test_context_builder_revision_eval.py
```

Codex now emits a validated structured revision outcome. Ambiguity creates a
persistent clarification task instead of relying on prose parsing. Completed
revisions receive a semantic Wren diff and, by default through the CLI, a
generated smoke run plus any configured regression suites. Eval execution uses
the existing Data Subagent CLI against the candidate Wren project. Only Wren and
eval acceptance may enter `REVIEW_REQUIRED`; eval failures enter `SMOKE_FAILED`.

Implemented R3 review and publication workflow:

```text
src/data_subagent_context_builder/review_workflow.py
tests/test_context_builder_review_workflow.py
```

Natural-language clarification answers can resume the same revision through a
new Codex execution. Accepted candidates receive a structured review packet.
Approval uses a separate human review-decision provenance and does not publish.
Publishing atomically updates the Context pointer and records history; rollback
points to an already published candidate through another recorded event.

Controlled StarRocks re-investigation is implemented for revision and resume
executions. Every authorization is explicit and bounded by `starrocks-query`.
Query evidence is independently validated and archived; returned rows are not
accepted in evidence. The database account must still enforce read-only,
database-scoped grants.

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

## 3.1 First Feasibility Answers

Verified locally on 2026-07-09 with WrenAI CLI `0.12.0`:

- `wren context import --help` says the import source is currently `dbt`.
- `wren profile import --help` says the import source is currently `dbt`.
- `wren context init`, `validate`, and `build` also expose OSI/MDL inputs via
  `--from-osi` / `--from-mdl`, but that is not arbitrary database
  introspection.
- `wren skills get generate-mdl` defines the generic database onboarding path:
  agent/script discovers schema, Wren normalizes types and validates/builds the
  resulting YAML project.
- `wren docs connection-info --format json` exposes datasource profile fields
  and should be used instead of hardcoding credential templates.
- `wren context validate` can fail on Windows GBK consoles while printing
  warning symbols; set `PYTHONIOENCODING=utf-8`.

Feasibility decision:

```text
dbt project
-> use Wren native dbt import

arbitrary database
-> use Wren generate-mdl style workflow:
   inspect schema with driver / SQLAlchemy / SQL
   normalize types through Wren
   write Wren YAML project
   run Wren validate/build/dry-run
```

Existing reusable code:

- `scripts/prepare_sqlite_wren_project.py` is the best fallback seed for
  SQLite/DuckDB onboarding.
- BIRD dataset discovery and eval conversion in `setup_bird_mini_dev_eval.py`
  and `prepare_bird_mini_dev_subset.py` should stay benchmark glue, though the
  JSONL smoke-case writing pattern is reusable.

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

Implemented first package on 2026-07-09:

```text
src/data_subagent_context_builder/__init__.py
src/data_subagent_context_builder/codex_runtime.py
src/data_subagent_context_builder/cli.py
src/data_subagent_context_builder/skill_onboarding.py
src/data_subagent_context_builder/report.py
src/data_subagent_context_builder/sqlite_onboarding.py
src/data_subagent_context_builder/smoke_eval.py
src/data_subagent_context_builder/wren_cli.py
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

`inspect` reads SQLite schema facts without creating DuckDB files, Wren project
files, or Wren home state. It prints JSON and can write JSON / Markdown reports
for Wren `generate-mdl` onboarding, Codex prompts, and human semantic review.
It also reports incomplete SQLite FK metadata so generated relationships can be
reviewed before MDL generation.

`generate-from-db` is now the recommended skill-first path. For SQLite input it
prepares the factual substrate only: Wren native project scaffolding via
`wren context init --empty`, SQLite-to-DuckDB runtime conversion, Wren type
normalization via `wren.type_mapping.parse_type(..., "sqlite")`, a DuckDB
profile, a `schema_manifest.json`, and a Codex prompt that instructs the agent
to read Wren's installed `generate-mdl` skill before writing MDL YAML. By
default it is prompt-only; `--execute` is required before it invokes
`codex exec`.

The generated prompt treats `schema_manifest.json` as seed evidence, not as the
complete semantic model or a replacement for Wren's skill. It explicitly tells
Codex to prefer the installed `generate-mdl` skill if there is any conflict, and
to inspect the DuckDB runtime directly when the skill calls for schema checks,
sample queries, relationship validation, or orphan checks.

When `--execute` is used, the Context Builder now wraps Codex with a bounded
outer repair loop:

```text
codex exec round 0
-> outer Wren validate/build/dry-run
-> if failed, write repair prompt with Wren command outputs
-> codex exec repair round
-> repeat up to --max-repair-rounds
-> final pass/fail report
```

This complements Codex's own in-process skill-following loop. Codex can still
run Wren commands while editing, but the outer builder owns the final structured
pass/fail check and report. The default is `--max-repair-rounds 2`; pass
`--no-post-validate` only when prompt execution should not be followed by outer
Wren verification.

This is still not a native Wren automatic database import. SQLite schema
inspection and SQLite-to-DuckDB conversion are repo glue because WrenAI CLI
`0.12.0` does not expose a generic `context import database` command. MDL YAML
generation is deliberately handed to Codex following Wren's `generate-mdl`
skill, not hidden behind deterministic SQLite-specific generation.

`generate-schema-draft` is the explicit fallback/debug path. It writes
mechanical schema-level Wren YAML from database metadata, then runs Wren
`context validate`, `context build`, and optional `dry-run`. Treat this as a
bootstrap draft, not the recommended semantic-layer generation path.

`validate` runs Wren `context validate`, `context build`, optional `dry-run`,
and can write the same report format for an existing Wren project.

`enrich-with-codex` prepares a Codex agent prompt for improving a Wren project
inside the Context Builder boundary. By default it does not execute Codex; it
writes/prints the prompt only. Passing `--execute` runs `codex exec` with
workspace-write sandboxing. This keeps Codex agent work in the upstream
onboarding/enrichment flow, not in the online Data Subagent ask runtime.

`make-smoke-eval` reads Wren model metadata and writes conservative JSONL eval
cases for the existing Data Subagent eval runner. The default cases are row-count
questions per model because they are robust for schema-level draft MDL. A
relationship join smoke can be added with `--include-relationship-case`, but it
is intentionally opt-in because relationship quality may be weak on generated
draft projects.

Possible commands:

```powershell
python -m data_subagent_context_builder.cli inspect --sqlite-path ...
python -m data_subagent_context_builder.cli import-dbt --dbt-project ...
python -m data_subagent_context_builder.cli generate-from-db --db ...
python -m data_subagent_context_builder.cli generate-schema-draft --sqlite-path ...
python -m data_subagent_context_builder.cli validate --wren-project-dir ...
python -m data_subagent_context_builder.cli make-smoke-eval --wren-project-dir ...
```

Recommended first concrete surface after feasibility checks:

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
  --prompt-output data\wren\<project>\onboarding\generate_mdl_prompt.md `
  --execute `
  --max-repair-rounds 2 `
  --report-path docs\<project>_wren_onboarding_report.md

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

Start with SQLite/DuckDB because the repo already has verified conversion and
profile setup. Keep the command names generic enough to add Postgres/MySQL via
SQLAlchemy or datasource-specific inspection later.

Current implemented example:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli `
  --project-root . `
  inspect `
  --sqlite-path data\external\bird_mini_dev\raw\...\debit_card_specializing.sqlite `
  --project-name bird_debit_card_specializing `
  --output data\tmp\context_builder_inspect_smoke\schema_report.md `
  --json-output data\tmp\context_builder_inspect_smoke\schema_report.json
```

Verified result:

```text
table_count: 5
relationship_count: 0
warnings: 2 incomplete SQLite FK metadata warnings
```

SQLite fallback generation now skips incomplete FK metadata instead of writing
invalid join conditions such as `"customers"."None"`.

Current implemented generation example:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli `
  --project-root . `
  generate-from-db `
  --sqlite-path data\tmp\<run>\sales.sqlite `
  --project-name smoke_sales `
  --project-dir data\tmp\<run>\wren_project `
  --duckdb-path data\tmp\<run>\smoke_sales.duckdb `
  --wren-home data\tmp\<run>\wren_home `
  --smoke-sql "select count(*) as order_count from orders" `
  --prompt-output data\tmp\<run>\generate_mdl_prompt.md
```

Verified result on a temporary SQLite fixture:

```text
ok: true
mode: skill
models: customers, orders
relationships: 1
context init: Wren project initialized
schema_manifest_path: wren_project/onboarding/schema_manifest.json
codex.executed: false
models/*/metadata.yml: not written by default
```

The explicit fallback draft path was also verified on 2026-07-10:

```text
generate-schema-draft:
context validate: Valid - 2 models, 0 views, 1 relationships.
context build: Built 2 models, 0 views
dry-run "select count(*) as order_count from orders": OK
```

Codex enrichment prompt example:

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

This returns `executed: false` unless `--execute` is provided.

Smoke eval generation example:

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

Verified output:

```text
emitted: 3
eval_ids:
- jaffle_shop_customers_count
- jaffle_shop_orders_count
- jaffle_shop_stg_customers_count
```

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
