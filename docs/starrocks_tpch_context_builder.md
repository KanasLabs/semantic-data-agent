# StarRocks TPC-H Skill-First Context Builder

This is the first full multi-table StarRocks onboarding case for the Context
Builder. It replaces the abandoned NYPD/weather proposal as Phase 1.

## Goal

```text
TPC-H data
-> StarRocks
-> controlled starrocks-query discovery
-> Codex follows Wren generate-mdl skill
-> candidate Wren Context Layer
-> outer validate / build / dry-run
-> Data Subagent eval
```

Codex decides which discovery queries to run. The outer Builder supplies the
read-only query boundary, evidence store, project/profile setup, stopping
conditions, and acceptance gates.

## Dataset

The local fixture uses DuckDB's official `tpch` extension to generate scale
factor `0.01`, then loads the rows into StarRocks through its MySQL protocol.

```text
region: 5
nation: 25
supplier: 100
customer: 1,500
part: 2,000
partsupp: 8,000
orders: 15,000
lineitem: 60,175
```

Prepare or reset the fixture:

```powershell
.\.venv-wren\python.exe scripts\setup_starrocks_tpch.py `
  --host 127.0.0.1 `
  --port 19030 `
  --database tpch_sf001 `
  --scale-factor 0.01 `
  --allow-empty-password `
  --force
```

`--force` drops only the named TPC-H fixture database before recreating it.
Empty passwords are allowed only for the isolated local Docker fixture.

## Generate Context

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli `
  --project-root . `
  generate-from-starrocks `
  --project-name tpch_starrocks `
  --project-dir data\wren\tpch_starrocks_wren_project `
  --host 127.0.0.1 `
  --port 19030 `
  --database tpch_sf001 `
  --user root `
  --allow-empty-password `
  --allowed-catalog default_catalog `
  --allowed-database tpch_sf001 `
  --smoke-sql "SELECT COUNT(*) AS order_count FROM orders" `
  --execute `
  --max-repair-rounds 1 `
  --force
```

For a real password, omit `--allow-empty-password`, set
`CONTEXT_BUILDER_STARROCKS_PASSWORD`, and use a read-only StarRocks account.

## Generated Candidate

The first run produced:

```text
controlled discovery queries: 69
models: 8
relationships: 8
truncated discovery results: 0
relationship orphan counts: 0
```

Accepted relationships cover region/nation, nation/supplier, nation/customer,
customer/orders, part/partsupp, supplier/partsupp, orders/lineitem, and the
composite part+supplier relationship between `lineitem` and `partsupp`.
Redundant direct lineitem-to-part and lineitem-to-supplier paths were inspected
but not emitted.

Important artifacts:

```text
data/wren/tpch_starrocks_wren_project/onboarding/discovery_snapshot.json
data/wren/tpch_starrocks_wren_project/onboarding/schema_manifest.json
data/wren/tpch_starrocks_wren_project/onboarding/starrocks_query_evidence.jsonl
data/wren/tpch_starrocks_wren_project/models/*/metadata.yml
data/wren/tpch_starrocks_wren_project/relationships.yml
```

## Verification

Wren acceptance:

```text
context validate: 8 models, 0 views, 8 relationships
context build: OK
order-count dry-run/query: 15,000
three-table orders/customer/nation query: OK
composite lineitem/partsupp query: 60,175
```

Data Subagent eval:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\tpch_starrocks_smoke.jsonl `
  --suite-name tpch_starrocks_smoke `
  --wren-project-dir data\wren\tpch_starrocks_wren_project `
  --wren-home data\wren\home `
  --limit 5 `
  --query-limit 100
```

Verified rerun:

```text
run_id: 20260714-124142-tpch_starrocks_smoke_rerun
passed: 5/5
```

## Known Boundaries

- The generated Context is a reviewable candidate, not production truth.
- StarRocks `DUPLICATE KEY` is a storage key, not an enforced relational key.
- Composite logical keys are documented but not misrepresented as one-column
  Wren primary keys.
- Currency, quantity units, discounts, taxes, status codes, and default dates
  still require business confirmation.
- `wren memory index/fetch/recall` is outside the bounded onboarding gate on
  Windows because first-time embedding initialization can hang.
- A timed-out Codex process is accepted only when all required artifacts and
  independent Wren validation gates pass; the accepted state is explicitly
  recorded as `accepted_after_timeout`.
