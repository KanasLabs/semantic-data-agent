# StarRocks 3.5 MVP Setup

This project uses the StarRocks shared-nothing all-in-one Docker image for local
MVP testing. The container runs one FE and one BE and must not be used as a
production deployment.

Reference: <https://docs.starrocks.io/zh/docs/3.5/quick_start/shared-nothing/>

## Files

```text
infra/starrocks/docker-compose.yml
infra/starrocks/init.sql
infra/starrocks/wren-connection.yml
scripts/starrocks_mvp.ps1
data/wren/starrocks_mvp_wren_project/
```

The Wren CLI does not expose a datasource named `starrocks`. StarRocks retains
the Doris-compatible MySQL query protocol and listens on port `9030`, so this
fixture uses Wren's `doris` datasource and validates the compatibility through
real `profile`, `dry-run`, and query commands.

## Start And Initialize

Install the Wren MySQL protocol dependency once:

```powershell
.\.venv-wren\python.exe -m pip install "wrenai[mysql]==0.12.0"
```

Start Docker Desktop, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\starrocks_mvp.ps1 -Action Up
```

This command:

1. starts `starrocks/allin1-ubuntu:3.5.18`
2. waits for the SQL endpoint to become healthy
3. creates the `data_agent_mvp` database
4. loads deterministic `customers` and `orders` fixtures
5. creates the local Wren `starrocks_mvp` profile
6. validates and builds the Wren project
7. runs a Wren dry-run

The initialization SQL is idempotent. Re-running `Up` reloads the fixture rows.

## Ports

| Port | Purpose |
| --- | --- |
| `18030` | Host port for the StarRocks FE HTTP UI (`8030` in the container) |
| `18040` | Host port for the StarRocks BE HTTP service (`8040` in the container) |
| `19030` | Host port for the MySQL-compatible SQL endpoint (`9030` in the container) |

The non-default host ports avoid collisions with other local StarRocks
containers. Override them with `STARROCKS_FE_HTTP_PORT`,
`STARROCKS_BE_HTTP_PORT`, and `STARROCKS_SQL_PORT` before starting the fixture.

The local root account has an empty password because this is an isolated MVP
fixture. Do not reuse this configuration outside local development.

## Check StarRocks

```powershell
powershell -ExecutionPolicy Bypass -File scripts\starrocks_mvp.ps1 -Action Status
```

Direct SQL smoke test:

```powershell
docker exec data-agent-starrocks mysql -h 127.0.0.1 -P 9030 -u root `
  -D data_agent_mvp `
  -e "SELECT status, COUNT(*) AS orders FROM orders GROUP BY status ORDER BY status"
```

## Run The Data Subagent

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
.\.venv-wren\python.exe -m data_subagent.cli ask `
  "How many orders are there?" `
  --wren-project-dir data\wren\starrocks_mvp_wren_project `
  --wren-home data\wren\home
```

The online path remains:

```text
Data Subagent
-> Wren Context Layer
-> Wren Doris-compatible semantic plan
-> StarRocks SQL endpoint
-> real query result
```

Run the reusable StarRocks smoke eval:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
.\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\starrocks_mvp_smoke.jsonl `
  --suite-name starrocks_mvp_smoke `
  --wren-project-dir data\wren\starrocks_mvp_wren_project `
  --wren-home data\wren\home `
  --limit 3
```

## Stop Or Reset

Stop the container while preserving FE/BE data:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\starrocks_mvp.ps1 -Action Down
```

Delete the local StarRocks volumes and recreate the fixture:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\starrocks_mvp.ps1 -Action Reset
```

`Reset` deletes only the named volumes owned by this Compose project.

## Docker Hub Network Pitfall

If Docker Hub is unavailable but a mirrored image is present, tag it with the
official name expected by Compose:

```powershell
docker tag docker.1panel.live/starrocks/allin1-ubuntu:3.5.18 `
  starrocks/allin1-ubuntu:3.5.18
```

The local machine used for the first verification already had the official tag
cached, so no mirror download was required.

## First Verified Result

Verified locally on 2026-07-13:

```text
StarRocks image: starrocks/allin1-ubuntu:3.5.18
container: data-agent-starrocks (healthy)
customers: 5
orders: 8
Wren profile datasource: doris
Wren context validate: 2 models, 1 relationship
Wren context build: OK
Wren dry-run: OK
Wren real grouped query: OK
Data Subagent answer: There are 8 orders.
trace: trace_450e96f7bdeb4373b91fc8a6649a6fe0
smoke eval: 3/3 passed
eval run: 20260713-175049-starrocks_mvp_smoke
```

The three eval cases verified order count, grouping by status, and realized
revenue against executable Gold SQL. Representative traces:

```text
trace_3d4980e2fc5449c492483598c7c26ee6
trace_7068983e71b9401995988147d17bda65
trace_295ceda0754b4129b09f8259835f8d82
```

The realized-revenue result value was correct, but the LLM summary rendered it
with a dollar sign even though the Context Layer describes the amount as CNY.
This is a useful future semantic-improvement case: result-equivalence evals need
an additional answer-unit/currency assertion before presentation quality can be
considered fully verified.

The issue is preserved as an intentionally failing improvement suite:

```text
data/evals/cases/starrocks_semantic_improvement_candidates.jsonl
data/evals/cases/starrocks_semantic_improvement_candidates.md
```

The first explicit baseline run on 2026-07-14 produced `0/1` passed with trace
`trace_c29d876e14db44fcb5f9efdeb34ce2ee`: SQL/result equivalence passed, but the
answer omitted `CNY`. This is the expected unresolved state.
