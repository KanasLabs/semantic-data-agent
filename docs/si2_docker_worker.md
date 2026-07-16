# SI2 Docker / CI Isolation Worker

## Purpose

The SI2 worker isolates only the Codex editing process. The outer Python
controller still creates the candidate, verifies frozen evidence, runs Wren
validation, and executes target/smoke/regression evals.

```text
host controller
  -> copied Wren candidate
  -> signed isolation receipt gate
  -> Docker Codex worker
       /workspace  candidate, read/write
       /evidence   minimized evidence, read-only
       /control/output.schema.json, read-only
       no repository/base/Registry/database mounts
  -> host Wren validation and evals
  -> REVIEW_REQUIRED at most
```

Docker avoids the current Windows nested-sandbox limitation because unmounted
host files are outside the container namespace. The worker still uses Codex
`workspace-write` with tool network disabled. The container joins an internal
Docker network and reaches `api.openai.com` only through the bundled Squid ACL
proxy; direct internet and non-OpenAI proxy destinations must fail before a
receipt is signed.

## Build And Start

The images require Docker Hub and npm access during build:

```powershell
docker compose -f infra\si2_codex_worker\docker-compose.yml --profile build build
docker compose -f infra\si2_codex_worker\docker-compose.yml up -d egress-proxy
```

Runtime execution resolves the worker tag to Docker's immutable `sha256` image
ID. The receipt binds that image ID, the internal network name, and a hash of
the proxy endpoint.

Expected runtime values:

```text
worker image: data-agent-si2-codex-worker:0.144.1
internal network: data-agent-si2-internal
proxy: http://data-agent-si2-egress-proxy:3128
```

## Secret Injection

The CI runner or secret manager must inject these only into the controller
process:

```text
OPENAI_API_KEY
DATA_AGENT_ISOLATION_HMAC_KEY
DATA_AGENT_ISOLATION_ENVIRONMENT_ID
```

Use a fresh random environment ID per isolated run and at least 32 random bytes
for the HMAC key. Do not put secret values in command arguments, repository
files, prompts, receipts, or logs. The Docker command passes only
`OPENAI_API_KEY` to the Codex parent. Codex receives
`shell_environment_policy.inherit=none`, so model-generated shell commands do
not inherit it. The two isolation variables are never passed into the
container.

## Probe And Receipt

After preparing an SI2 Job, run the no-model isolation probes:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_agent_improvement.cli prepare-docker-isolation `
  --job job_... `
  --docker-image data-agent-si2-codex-worker:0.144.1 `
  --docker-network data-agent-si2-internal `
  --docker-https-proxy http://data-agent-si2-egress-proxy:3128 `
  --issuer ci-runner `
  --output data\tmp\si2_worker\isolation_receipt.json

.\.venv-wren\python.exe -m data_agent_improvement.cli verify-isolation-receipt `
  --job job_... `
  --receipt data\tmp\si2_worker\isolation_receipt.json
```

The probe refuses to sign unless it verifies:

- candidate write and evidence read
- evidence write denial and read-only container root
- no base snapshot or repository mount
- internal Docker network with no direct internet
- OpenAI API reachability through the proxy
- rejection of a non-OpenAI proxy destination
- Codex sandbox denial of a reachable network canary
- Codex child environment exclusion of a dummy API key

## Execute

Only after the receipt verifies:

```powershell
.\.venv-wren\python.exe -m data_agent_improvement.cli execute-semantic-job `
  --job job_... `
  --context-registry-root data\context_registry `
  --wren-home data\wren\home `
  --wren-bin .venv-wren\Scripts\wren.exe `
  --executor docker `
  --docker-image data-agent-si2-codex-worker:0.144.1 `
  --docker-network data-agent-si2-internal `
  --docker-https-proxy http://data-agent-si2-egress-proxy:3128 `
  --isolation-receipt data\tmp\si2_worker\isolation_receipt.json `
  --execute
```

The image ID, network, proxy hash, Job contract, EvalTarget, evidence manifest,
schema fingerprint, environment ID, signature, expiry, and all probe results
must still match. Otherwise the Job remains `PREPARED` and Codex is not called.

## Current Local Status

Docker Desktop is running Linux containers with cgroup v2. The first worker
image build on 2026-07-16 failed before any image layer ran because this host
could not reach `registry-1.docker.io:443`; retrying outside the workspace
sandbox produced the same timeout. No Codex process or OpenAI request was
started. Build and live probes therefore remain pending on a network-enabled CI
runner or restored Docker registry access.
