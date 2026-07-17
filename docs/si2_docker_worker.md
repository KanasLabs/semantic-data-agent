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

## CLI-First, SDK-Later Decision

The current worker intentionally installs and invokes the pinned Codex CLI:

```text
@openai/codex 0.144.1
codex exec --ephemeral --ignore-user-config --output-schema ...
```

This is the approved MVP execution adapter. The future SDK migration is an
adapter replacement, not an architecture rewrite. `SemanticCandidateExecutor`
remains the boundary, so Docker mounts, proxy restrictions, isolation probes,
signed receipts, frozen eval targets, outer Wren/eval gates, and human review
remain unchanged.

The local host CLI is not authorized as a shortcut for a Docker receipt. Until
the container image and probes pass, real SI2 execution remains blocked even
though `codex.exe` is installed on Windows.

## Build And Start

The images require a reachable OCI registry, Debian mirror, and npm registry.
The default values use upstream services. The verified mainland-China fallback
on 2026-07-17 was:

```powershell
$env:WORKER_BASE_IMAGE='docker.1panel.live/library/node:22-bookworm-slim'
$env:PROXY_BASE_IMAGE='docker.1panel.live/library/debian:bookworm-slim'
$env:DEBIAN_MIRROR_HOST='mirrors.aliyun.com'
$env:NPM_REGISTRY='https://registry.npmmirror.com'

docker compose -f infra\si2_codex_worker\docker-compose.yml --profile build build
docker compose -f infra\si2_codex_worker\docker-compose.yml up -d --no-build egress-proxy
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

Docker Desktop is running Linux containers with cgroup v2. Upstream Docker Hub
remained unreachable, but the verified fallback registries above successfully
built both images on 2026-07-17:

```text
worker: sha256:63339471636cb03da0ff021a5ceb4c842b8f2171bad9c492419215c8a84cdc95
proxy:  sha256:f35b5ebec10bcc4edd08643e8577b48b7624d7818e2d99f1e43ec6d2d59d9782
Codex CLI: 0.144.1
worker UID: 10001
proxy user: proxy
```

The first proxy start failed because Squid's optional ICMP pinger cannot run
with all capabilities dropped. `pinger_enable off` fixed it without adding a
capability. The final proxy stays up on both expected networks.

Live no-model results:

```text
candidate/evidence/rootfs mount probe: passed
Codex reachable-canary tool-network denial: passed
Codex dummy API-key child-environment exclusion: passed
OpenAI-only proxy rejects non-OpenAI destinations: implemented
OpenAI API control-plane reachability: failed
isolation receipt: not issued
real codex exec: not started
```

Docker's default seccomp profile blocks the user namespace required by Codex's
Linux `bwrap` sandbox. The worker currently keeps UID 10001, dropped
capabilities, read-only rootfs, `no-new-privileges`, restricted mounts and the
internal network, while setting `seccomp=unconfined` so the inner Codex sandbox
can start. A narrow custom seccomp profile is a future hardening task.

After clearing an initially stale DNS result, Squid reached the correct
Cloudflare address and returned `TCP_TUNNEL/200`, but the TLS handshake ended in
`SSL_ERROR_SYSCALL`. This host has no WinHTTP, Windows Internet, or common local
VPN proxy configured. The provider probe therefore correctly refused to sign a
receipt. No API key was sent, no authenticated OpenAI request completed, and
the prepared Job remains unexecuted. A working corporate/VPN/CI upstream route
to `api.openai.com` is still required.
