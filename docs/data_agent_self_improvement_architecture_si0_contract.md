# Data Agent Self-Improvement Architecture & SI0 Contract

Status: SI0-SI1 implemented; SI2 controller implemented, real execution pending; SI3-SI4 proposed
Date: 2026-07-16
Scope: Background controlled self-improvement for the Data Agent system

## 1. Executive Decision

The project should add a third, separate workstream:

```text
data_subagent
  -> online data-question runtime

data_subagent_context_builder
  -> upstream Wren Context onboarding and revision tool

data_agent_improvement
  -> background failure discovery, triage, bounded improvement, and evaluation
```

`data_agent_improvement` is an Improvement Orchestrator. It does not answer
online questions and it does not replace the Context Builder. It consumes
immutable evidence, creates bounded improvement work, invokes existing
candidate/revision workflows, and keeps human approval and publication as
separate gates.

The first phase, SI0, is read-only with respect to Wren Context, prompts, code,
and published state:

```text
versioned trace + eval result + optional business correction pair
  -> normalized failure case
  -> immutable improvement registry
  -> reproducible triage report
```

SI0 must not invoke Codex, create a Context revision, approve or publish a
candidate, or roll back a Context.

## 2. Product Goal

The reference implementation is OpenAI, Thrive Holdings, and Crete's
`Building self-improving tax agents with Codex`:

```text
https://openai.com/index/building-self-improving-tax-agents-with-codex/
```

The transferable pattern is not model-weight training. It is an eval-driven
engineering loop in which practitioner corrections and production traces are
grouped into findings, converted into eval targets, and passed to Codex as
bounded tasks with read-only production evidence and a writable candidate
worktree.

The target loop adapted to Text-to-SQL and WrenAI is:

```text
online question
  -> Data Subagent + WrenAI + DeepSeek
  -> production trace + feedback or scoped business correction pair
  -> normalized failures + singleton or clustered GroupedFinding
  -> frozen EvalTarget
  -> BoundedCodexTask
  -> writable Context candidate or Git worktree
  -> frozen target eval + regression
  -> semantic and engineering review
  -> Context publish or reviewed Git merge/deploy
  -> post-publication health monitoring
```

The goal is not autonomous self-modification. The goal is to turn observed
failures and confirmed business truth into evidence-backed candidate changes
that are independently validated and reviewable.

## 3. Goals And Non-Goals

### 3.1 Goals

- Preserve enough versioned evidence to reproduce a failure.
- Accept general feedback and optional business correction pairs without
  requiring Wren YAML editing.
- Normalize runtime, eval, and feedback signals into one failure-case model.
- Preserve observed output and, when supplied, corrected output and correction
  provenance.
- Require a reviewed, frozen eval target before Codex can modify a candidate.
- Make ingestion idempotent and records auditable.
- Separate observable facts, user-declared business truth, automated
  classification, and Codex inference.
- Reuse the existing Context Builder revision, eval, review, approval,
  publication, and rollback workflows.
- Prefer semantic-asset improvement before prompt or code modification.

### 3.2 SI0 Non-Goals

SI0 does not:

- classify root cause with an LLM
- cluster related failures
- generate an improvement task
- modify Wren Context, examples, eval cases, prompts, guardrails, or code
- invoke Codex CLI or Codex SDK
- run Wren validation or Data Subagent regression
- approve, publish, or roll back a Context
- add a scheduler, daemon, web service, or FastAPI endpoint
- replace the future Main Agent / Orchestrator

## 4. Existing Foundation

The repository already contains the second half of the controlled loop:

- `TraceRecord` and `JsonlTraceStore` preserve online execution evidence.
- `EvalCase`, `EvalRunRecord`, and `EvalRunSummary` preserve acceptance signals.
- `RevisionStore` provides candidate/revision identity, provenance, HITL tasks,
  legal transitions, and publication history.
- `revise_candidate` creates an isolated Wren candidate and runs bounded Codex,
  Wren, smoke, and regression acceptance.
- `SemanticDiff` and `ReviewPacket` make changes reviewable.
- `approve_candidate`, `publish_candidate`, and `rollback_context` keep review,
  release, and rollback explicit.

The missing first half is:

```text
feedback capture
  -> evidence normalization
  -> failure inbox
  -> root-cause triage
  -> repeated-failure grouping
  -> bounded task composition
```

SI0 implements the first three items only.

## 5. Architectural Principles

### 5.1 Offline By Default

Improvement is a background workflow. The online `ask_data_question` path must
not wait for mining, Codex, candidate evaluation, or human review.

### 5.2 Evidence Before Change

Every future task must reference one or more of:

- runtime trace
- eval run record
- explicit user feedback
- user-declared business truth
- authorized database evidence
- existing published Context
- a correction pair supplied by a business contributor or confirmer

### 5.3 Eval Before Repair

A reviewed finding must become a reviewed and frozen `EvalTarget` before Codex
starts candidate work. A finding may contain one high-confidence, authorized
business correction or a cluster of repeated lower-confidence failures. Codex may
propose additional tests, but it must not weaken, delete, or rewrite the target
that defines success for its own task.

### 5.4 Candidate, Not Production Mutation

Improvement execution produces a candidate. Codex must not mutate a published
Wren project, Registry pointer, production prompt, or application code in place.

### 5.5 Deterministic Control, Agentic Execution

State transitions, risk policy, gates, thresholds, and publication permissions
are deterministic. LLMs and Codex may investigate and generate candidates only
inside those boundaries.

### 5.6 Human Ownership Of Business Truth

Database inspection may establish observable facts. It cannot establish
company policy such as realized revenue, GMV, customer activity, or fiscal
period rules. Those require business provenance. A business confirmer is not
expected to understand SQL, Wren, Codex, or the whole company domain. The role
only means the person can confirm a narrow statement within an explicit scope,
for example the unit of `orders.total_amount`, which order states count as
realized revenue, or the denominator and NULL policy of one metric.

The human-facing interaction may use natural language, but natural language
does not itself require Codex SDK. SI0 may accept text through a CLI, form,
chat UI, or ordinary application API and store it deterministically as
`FeedbackRecord`. Codex SDK enters only in SI2/SI3, where it investigates a
frozen finding, prepares a candidate, and may formulate focused clarification
questions. If the user does not know an answer, the statement remains
unresolved; Codex must not infer company policy from database values or its own
prior output.

The role vocabulary is:

```text
FEEDBACK_PROVIDER
  -> may report dissatisfaction or an observed problem

BUSINESS_CONTRIBUTOR
  -> may propose a business statement; authority is still a claim

AUTHORIZED_BUSINESS_CONFIRMER
  -> project-verified for named Context IDs and narrow business scopes

CONTEXT_APPROVER
  -> performs the separate candidate review/approval action
```

Before SI2 execution, the outer workflow must verify that required business
statements came from an authorized confirmer for the affected Context and
scope. In the MVP, one person may be both confirmer and approver, but supplying
business truth and approving the resulting candidate must remain two explicit,
separately recorded actions. Ordinary ratings and benchmark labels cannot
establish truth.

### 5.7 Read-Only Evidence, Writable Candidate

Every Codex task receives two explicitly separated roots:

```text
read-only evidence bundle
  -> production traces, corrections, grouped finding, frozen eval target,
     base Context/code snapshot, and authorized evidence

writable candidate workspace
  -> copied Wren candidate or isolated Git worktree
```

Production evidence must remain immutable. Candidate output is never deployed
in place. An Evidence Packager must minimize and redact traces before they are
mounted for Codex; the read-only bundle is not automatically the entire raw
trace store.

### 5.8 No Self-Approval

The component that creates or evaluates a candidate cannot provide the human
approval decision. Approval and publication remain separate operations.

### 5.9 Project-Specific Evaluation Policy

Tax-form corrections often provide a single structured expected output. Data
questions allow many semantically equivalent SQL queries and answer phrasings.
Our EvalTargets therefore prefer, in order:

1. result equivalence or approved numeric tolerance
2. business invariants and required filters
3. unit, terminology, and answer-grounding constraints
4. read-only and Wren-path safety constraints
5. SQL fragments only when no semantic-equivalence check can express the rule

Candidate evaluation must distinguish `PASS`, `FAIL`, `INCONCLUSIVE`,
`NEEDS_BUSINESS_REVIEW`, and `EVAL_TARGET_INVALID`. DeepSeek, Wren, database,
or network availability failures are `INCONCLUSIVE`, not candidate regressions.

## 6. Target Architecture

```text
                         Online Plane

User / Main Agent
        |
        v
Data Subagent controlled loop
        |
        +----> WrenAI ----> database
        +----> JSONL trace
        +----> eval run record
        +----> user feedback reference

                      Improvement Plane

Trace Ingestor -----+
Eval Ingestor ------+--> Failure Inbox --> Triage --> GroupedFinding
Correction Recorder +                                |
                                                     v
                                             Frozen EvalTarget
                                                     |
                                                     v
                                            BoundedCodexTask
                                                     |
             +----------------------------------+------------------+
             |                                  |                  |
             v                                  v                  v
    Context Revision Executor        Eval/Example Executor  Engineering Executor
    (existing Builder)               (later phase)          (later phase)
             |                                  |                  |
             +----------------------------------+------------------+
                                                |
                                                v
                               Frozen Target Eval + Regression
                                                |
                                                v
                                      Human Review / Approval
                                                |
                                                v
                         Context Publish or Git PR / Merge / Deploy
```

The Main Agent and Improvement Orchestrator have different responsibilities:

- Main Agent decides which capability handles a current user request.
- Improvement Orchestrator decides how an observed failure becomes bounded
  background work.
- Context Builder creates and validates Wren Context candidates.
- Data Subagent remains the authoritative online query and eval runtime.

The improvement workstream can be implemented before the Main Agent. Future
Main Agent integration should only submit feedback, request improvement status,
surface clarification tasks, and route confirmed improvement requests.

## 7. Improvement Objects And Risk

| Improvement object | Risk | First phase | Required control |
| --- | --- | --- | --- |
| failure report | LOW | SI0 | provenance and immutable record |
| grouped finding | LOW | SI1 | source references and review |
| frozen eval target | LOW | SI1 | authorized correction and immutable acceptance |
| confirmed NL-SQL example | LOW | SI2 | source reference and regression |
| field description / business term | MEDIUM | SI2 | business review and regression |
| business rule / metric definition | MEDIUM | SI2 | business truth and regression |
| Wren relationship / model structure | HIGH | SI2 | engineering and business review |
| prompt template | HIGH | SI3 | isolated Git worktree and full eval |
| SQL guardrail / permissions | HIGH | SI3 | security review and full eval |
| adapter or application code | HIGH | SI3 | engineering review, CI, and PR |

The first executable slice should allow only Wren Context, business rules,
confirmed examples, and eval candidates. Prompt and code improvement require a
separate engineering-candidate workflow.

## 8. Failure Taxonomy

SI0 records observable signals and failure phase. SI1 will assign root-cause
categories from this controlled taxonomy:

```text
BUSINESS_SEMANTIC_GAP
CONTEXT_SCHEMA_GAP
RELATIONSHIP_GAP
EXAMPLE_GAP
SQL_GENERATION
SQL_DIALECT_OR_WREN
SUMMARY_GROUNDING
CLARIFICATION_POLICY
INFRASTRUCTURE
EVAL_DATA_QUALITY
SECURITY_POLICY
UNKNOWN
```

Failure phase and root cause are different. An answer missing `CNY` is observed
in summarization or eval, but its cause may be missing Context semantics,
summary grounding, or an incorrect eval expectation. SI0 records the
observation without choosing among those explanations.

## 9. Target Lifecycle

The eventual `ImprovementTask` lifecycle is:

```text
DISCOVERED
  -> TRIAGE_REQUIRED
  -> WAITING_FOR_BUSINESS_TRUTH | GROUPED
  -> EVAL_TARGET_REVIEW
  -> READY
  -> CANDIDATE_RUNNING
  -> VALIDATING
  -> REVIEW_REQUIRED
  -> APPROVED
  -> PUBLISHED
```

Side or terminal states are:

```text
DISMISSED
REJECTED
VALIDATION_FAILED
REGRESSION_FAILED
INCONCLUSIVE
EVAL_TARGET_INVALID
STALE
```

This lifecycle must not duplicate detailed Context revision state. An
improvement task references `revision_id` and `candidate_id`; Context Builder
remains authoritative for revision and candidate state.

SI0 creates only `FailureCase` records in `UNTRIAGED` state.

## 10. SI0 Deliverables

SI0 consists of:

1. Versioned trace metadata identifying the runtime and Context version.
2. Immutable business correction pairs linked to traces.
3. Normalized failure cases for runtime, eval, and feedback signals.
4. A filesystem Improvement Store with atomic writes and idempotent ingestion.
5. Read-only CLI commands and reports for inspecting the failure inbox.

Proposed package:

```text
src/data_agent_improvement/
  __init__.py
  models.py
  store.py
  feedback.py
  ingestion.py
  report.py
  cli.py
```

Proposed tests:

```text
tests/test_improvement_models.py
tests/test_improvement_store.py
tests/test_improvement_feedback.py
tests/test_improvement_ingestion.py
tests/test_improvement_report.py
```

## 11. Common Record Rules

Every SI0 JSON record must follow these rules:

- UTF-8 JSON with a trailing newline.
- Integer `schema_version`, starting at `1`.
- Lowercase prefix plus lowercase hexadecimal identifier.
- UTC ISO 8601 timestamps.
- Atomic writes through a temporary file and `replace`.
- Idempotent creation for deterministic source identities.
- Identifier validation before path construction.
- No credentials, authorization headers, environment values, or passwords.
- No database result rows copied into Improvement Store records.

ID formats:

```text
feedback_<32 lowercase hex>
case_<24 lowercase hex derived from source identity>
finding_<32 lowercase hex>
evaltarget_<32 lowercase hex>
job_<32 lowercase hex>
event_<32 lowercase hex>
```

`feedback_id` is random. `case_id` is deterministic so re-ingestion does not
create duplicates.

## 12. Trace Contract Extension

### 12.1 Compatibility

Existing trace JSONL is append-only and must not be rewritten. A trace without
`schema_version` is legacy trace version `1`.

The enriched trace schema is version `2`. New fields are optional at the Python
dataclass boundary during migration, but new real runtime traces should populate
them once SI0 is enabled.

### 12.2 Version Identity

The new trace fields are:

```json
{
  "schema_version": 2,
  "runtime_identity": {
    "runtime_name": "data_subagent",
    "runtime_version": "git:8e9b22d",
    "entrypoint": "cli.ask"
  },
  "context_identity": {
    "context_id": "data_agent_mvp_revision_acceptance",
    "candidate_id": "candidate_...",
    "context_version": 2,
    "publication_id": "publication_...",
    "wren_project_fingerprint": "sha256:..."
  },
  "data_identity": {
    "datasource_id": "starrocks:data_agent_mvp",
    "schema_fingerprint": "sha256:...",
    "query_started_at": "2026-07-16T00:00:00+00:00",
    "result_sha256": "sha256:...",
    "snapshot_id": null
  },
  "llm_identity": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "sql_prompt_version": "sql-v1",
    "repair_prompt_version": "repair-v1",
    "summary_prompt_version": "summary-v1"
  },
  "eval_identity": {
    "run_id": null,
    "eval_id": null,
    "suite_name": null
  },
  "timings_ms": {
    "context": null,
    "generate_sql": null,
    "dry_plan": null,
    "dry_run": null,
    "execute": null,
    "summarize": null,
    "total": null
  }
}
```

Existing trace fields are omitted from the example.

`data_identity` does not promise that a mutable production database can be
replayed exactly. It records enough identity to detect schema or result drift
and to mark a later comparison `INCONCLUSIVE` when no stable snapshot exists.

### 12.3 Wren Project Fingerprint

The fingerprint must include semantic runtime inputs such as:

```text
wren_project.yml
models/
relationships/
rules/
knowledge/sql/
```

It must exclude generated or local state:

```text
.wren/
target/
__pycache__/
*.pyc
onboarding prompts/messages that do not affect runtime semantics
```

The implementation must use a tested allowlist. A project path alone is not a
sufficient version identity.

Feedback is not appended to an existing trace. `FeedbackRecord` points to
`trace_id`, preserving append-only trace behavior.

### 12.4 Evidence Packaging

SI0 defines a future-safe evidence boundary even though it does not invoke
Codex. A later Evidence Packager must use field allowlists, secret scanning,
length limits, and row minimization. It should prefer hashes, schema summaries,
error excerpts, and approved evidence references over copying `result_preview`
or full Wren Context payloads.

## 13. FeedbackRecord Contract

Feedback types:

```text
RATING
CORRECTION
BUSINESS_TRUTH
EXPECTED_ANSWER
EXPECTED_SQL
OTHER
```

A negative rating is a signal, not business truth. `FeedbackRecord` is the
general envelope; `correction_pair` is optional and represents the stronger Tax
AI-style input. The immutable production trace identifies observed behavior,
while a business contributor may supply expected behavior and provenance in
natural language. This is initially a claim, not automatically approved truth.
A statement such as “only completed orders are realized revenue” must be
explicitly recorded as user-declared business truth and verified against the
actor's narrow authority scope before it can authorize SI2 execution.

Schema:

```json
{
  "schema_version": 1,
  "feedback_id": "feedback_...",
  "trace_id": "trace_...",
  "feedback_type": "BUSINESS_TRUTH",
  "sentiment": "NEGATIVE",
  "comment": "The old answer included shipped orders.",
  "correction_pair": {
    "observed": {
      "trace_id": "trace_...",
      "answer_sha256": "sha256:...",
      "sql_sha256": "sha256:..."
    },
    "expected": {
      "answer": "721.80 CNY",
      "sql": null,
      "business_statements": [
        "total_amount is denominated in CNY",
        "only completed orders count as realized revenue"
      ]
    }
  },
  "provenance": {
    "provenance_type": "user_declared_business_truth",
    "source_id": "user-session-reference",
    "statement": "only completed orders count as realized revenue"
  },
  "actor": {
    "actor_id": "domain-user-reference",
    "actor_type": "BUSINESS_CONTRIBUTOR",
    "authority_status": "UNVERIFIED",
    "authorized_context_ids": [],
    "authorized_scopes": []
  },
  "created_at": "2026-07-16T00:00:00+00:00",
  "supersedes_feedback_id": null
}
```

Validation rules:

- `trace_id` is required and must exist unless an explicit debug/import option
  permits a missing trace.
- `BUSINESS_TRUTH` requires at least one non-empty business statement.
- `EXPECTED_SQL` requires non-empty SQL, but SI0 never executes it.
- `RATING` and `OTHER` may omit `correction_pair`; omission keeps the feedback
  unverified and prevents it from establishing an EvalTarget by itself.
- A correction pair must reference the observed trace and freeze hashes of the
  observed answer and SQL so later ingestion can detect evidence drift.
- Expected behavior is human-supplied business input. It must not be copied
  from the agent's own output and promoted to truth.
- Retraction creates a new record with `supersedes_feedback_id`; prior feedback
  remains immutable.
- `authority_status` is one of `UNVERIFIED`, `PROJECT_CONFIRMED`, or `REVOKED`.
  A self-declared actor type or scope remains `UNVERIFIED`; only an outer
  project-controlled authority record may set `PROJECT_CONFIRMED`.
- SI0 records authority claims but does not grant authority. SI1 may prepare a
  draft target from unverified feedback; SI2 must reject execution unless the
  required business statements come from an actor authorized for the affected
  `context_id` and scope.
- Clarification questions must be narrow and answerable in business language.
  “Unknown” is a valid answer and keeps the corresponding target or candidate
  unresolved rather than allowing Codex to guess.

## 14. FailureCase Contract

`FailureCase` is the normalized inbox item consumed by SI1. It records what was
observed and where. It does not assert root cause.

Source types:

```text
RUNTIME_TRACE
EVAL_RECORD
USER_FEEDBACK
```

Observable phases:

```text
CLARITY
CONTEXT
SQL_GENERATION
SQL_GUARDRAIL
WREN_DRY_PLAN
WREN_DRY_RUN
EXECUTION
SUMMARIZATION
EVAL_ASSERTION
USER_FEEDBACK
UNKNOWN
```

Schema:

```json
{
  "schema_version": 1,
  "case_id": "case_...",
  "source_type": "EVAL_RECORD",
  "source_identity": {
    "trace_id": "trace_...",
    "eval_run_id": "20260714-093727-starrocks_semantic_improvement_baseline",
    "eval_id": "starrocks_realized_revenue_currency",
    "feedback_id": null
  },
  "context_identity": {
    "context_id": "data_agent_mvp",
    "candidate_id": null,
    "context_version": null,
    "publication_id": null,
    "wren_project_fingerprint": "sha256:..."
  },
  "question": "What is the total realized revenue?",
  "observed_status": "success",
  "failure_phase": "EVAL_ASSERTION",
  "signals": [
    {
      "signal_type": "ANSWER_MISSING_EXPECTED_FRAGMENT",
      "message": "answer missing expected fragment: CNY",
      "value": "CNY"
    }
  ],
  "evidence_refs": [
    {
      "evidence_type": "TRACE",
      "evidence_id": "trace_...",
      "path": "data/traces/data_subagent.jsonl"
    },
    {
      "evidence_type": "EVAL_RUN",
      "evidence_id": "20260714-093727-starrocks_semantic_improvement_baseline",
      "path": "data/evals/runs/...jsonl"
    }
  ],
  "triage_status": "UNTRIAGED",
  "root_cause": null,
  "created_at": "2026-07-16T00:00:00+00:00",
  "updated_at": "2026-07-16T00:00:00+00:00"
}
```

Creation rules:

- A runtime trace creates a case for `failed`, `need_clarification`, or a
  configured improvement-relevant error/warning.
- An eval record creates a case for `fail`, `needs_triage`, or Gold SQL triage.
- Feedback creates a case for negative sentiment or correction/truth/expected
  answer/expected SQL types.
- A successful trace without feedback or eval failure creates no case.

Canonical source identities:

```text
RUNTIME_TRACE:<trace_id>:<failure_phase>
EVAL_RECORD:<eval_run_id>:<eval_id>
USER_FEEDBACK:<feedback_id>
```

`case_id` is `case_` plus the first 24 lowercase hexadecimal characters of
SHA-256 over the UTF-8 canonical identity. Repeated ingestion returns the
existing case and `created=false`.

SI0 writes only `UNTRIAGED`. The forward-compatible SI1 states are:

```text
UNTRIAGED
  -> TRIAGE_REQUIRED
  -> WAITING_FOR_BUSINESS_TRUTH | READY_FOR_TASK
  -> DISMISSED
```

SI0 must not populate `root_cause`.

### 14.1 GroupedFinding Contract

SI1 organizes one or more related `FailureCase` records into a reviewed
`GroupedFinding`. `grouping_mode=SINGLETON` is allowed for a high-confidence,
authorized business correction or a structural/security failure; ordinary
ratings and ambiguous benchmark cases require clustering or human triage.

```json
{
  "schema_version": 1,
  "finding_id": "finding_...",
  "context_id": "data_agent_mvp",
  "grouping_mode": "SINGLETON",
  "case_ids": ["case_..."],
  "representative_trace_ids": ["trace_..."],
  "root_cause_candidate": "BUSINESS_SEMANTIC_GAP",
  "confirmed_business_truth_feedback_ids": ["feedback_..."],
  "authority_decision_ids": ["authority_..."],
  "business_scopes": ["realized_revenue"],
  "status": "EVAL_TARGET_REQUIRED",
  "created_at": "2026-07-16T00:00:00+00:00"
}
```

Grouping is evidence organization, not proof of root cause. Infrastructure and
benchmark-quality findings must remain separate from semantic improvement.

### 14.2 EvalTarget Contract

Before Codex executes, SI1 converts a reviewed finding into a versioned target.
The target lifecycle is `DRAFT -> NEEDS_BUSINESS_REVIEW -> APPROVED -> FROZEN`.
`SUPERSEDED` and `INVALID` are terminal replacement states; a corrected target
is a new version rather than an in-place rewrite.

```json
{
  "schema_version": 1,
  "eval_target_id": "evaltarget_...",
  "version": 1,
  "finding_id": "finding_...",
  "question": "What is the total realized revenue?",
  "result_contract": {
    "expected_value": 721.80,
    "numeric_tolerance": 0.001
  },
  "semantic_constraints": {
    "required_filters": ["orders.status = completed"],
    "required_units": ["CNY"],
    "forbidden_units": ["$"]
  },
  "sql_hints": [],
  "evidence_refs": ["feedback_...", "trace_..."],
  "frozen_sha256": "sha256:...",
  "status": "FROZEN",
  "created_at": "2026-07-16T00:00:00+00:00"
}
```

The frozen hash is recorded in the later `BoundedCodexTask`. Candidate
evaluation must fail if the target changes during execution. If investigation
shows the target is wrong or unreplayable, Codex reports
`EVAL_TARGET_INVALID`; it cannot edit the target. Equivalent SQL is accepted
when it satisfies the result contract and semantic constraints.

### 14.3 BoundedCodexTask Contract

SI2/SI3 gives Codex an explicit job rather than an open-ended instruction:

```json
{
  "schema_version": 1,
  "job_id": "job_...",
  "finding_id": "finding_...",
  "eval_target_id": "evaltarget_...",
  "eval_target_sha256": "sha256:...",
  "target_type": "WREN_CONTEXT",
  "risk_level": "MEDIUM",
  "read_only_roots": ["sanitized_evidence_bundle", "base_snapshot"],
  "evidence_manifest_sha256": "sha256:...",
  "data_identity": {
    "schema_fingerprint": "sha256:...",
    "snapshot_id": null
  },
  "writable_root": "candidate_workspace",
  "allowed_paths": ["models/**", "relationships.yml", "knowledge/**"],
  "forbidden_paths": ["data/context_registry/**", "src/**", ".git/**"],
  "required_suites": ["target", "context_smoke", "regression"],
  "target_eval_repetitions": 3,
  "timeout_seconds": 900,
  "max_repair_rounds": 2,
  "database_access": false,
  "network_access": false
}
```

The task controller, not Codex, owns workspace creation, permissions, frozen
target integrity, evidence redaction, outer validation, lifecycle transitions,
and release gates. A run result is one of `PASS`, `FAIL`, `INCONCLUSIVE`,
`NEEDS_BUSINESS_REVIEW`, or `EVAL_TARGET_INVALID`. Repetition count may be one
for deterministic Wren-only checks and greater than one for DeepSeek-dependent
behavior.

The implemented SI2 executor boundary is a replaceable Python `Protocol`.
`ContextBuilderSemanticExecutor` is currently backed by the installed
`codex exec` CLI and the existing Context Builder `revise_candidate` workflow;
a future Codex SDK adapter can implement the same protocol without changing the
job controller.

The installed CLI was directly verified to support `workspace-write`,
`--ephemeral`, `--ignore-user-config`, `--output-schema`, JSONL output, and
non-interactive execution. The OpenAI Codex manual helper was attempted inside
and outside the sandbox on 2026-07-16 but the official endpoint returned HTTP
403, and Docs MCP was unavailable in this session. No undocumented SDK
parameters were invented.

### 14.4 Dual Release Channels

Semantic and engineering candidates have different release mechanics:

```text
Wren Context candidate
  -> semantic diff + Wren/eval gates + business approval
  -> Context Registry publish

prompt/code candidate
  -> Git diff + unit/integration/eval gates + engineering review
  -> pull request, merge, and normal deployment
```

Neither channel permits Codex to merge, approve, publish, or deploy its own
candidate.

## 15. Improvement Store Contract

Default layout:

```text
data/improvement_registry/
  feedback/
    feedback_<id>.json
  cases/
    case_<id>/
      case.json
  authority/
    authority_<id>.json
  findings/
    finding_<id>.json
  eval_targets/
    evaltarget_<id>.json
  jobs/
    job_<id>/
      job.json
      evidence/
      control/
      result.json
  reports/
    <report_id>.md
  events/
    event_<id>.json
```

The directory is local runtime state and is Git-ignored. SI0 creates
`feedback`, `cases`, `reports`, and optional `events`. SI1 adds immutable
authority decisions and findings plus lifecycle-controlled EvalTargets. Stable
schemas, fixtures, and curated eval cases belong in source control; real
feedback and runtime records do not.

Proposed Python boundary:

```python
class ImprovementStore:
    def create_feedback(self, feedback: FeedbackRecord) -> Path: ...
    def get_feedback(self, feedback_id: str) -> FeedbackRecord: ...
    def list_feedback(self, trace_id: str | None = None) -> list[FeedbackRecord]: ...

    def create_case(self, case: FailureCase) -> tuple[Path, bool]: ...
    def get_case(self, case_id: str) -> FailureCase: ...
    def list_cases(self, triage_status: str | None = None) -> list[FailureCase]: ...
```

The store validates identifiers, prevents path traversal, and uses atomic JSON
writes consistent with `RevisionStore`.

An optional ingestion event contains only IDs and status, never full trace
payloads or result rows.

## 16. SI0 Ingestion Policy

### Runtime Traces

- Ignore blank JSONL lines.
- Report file and line number for invalid JSON.
- Treat missing `schema_version` as legacy version `1`.
- Normalize missing version metadata to `null`.
- Create only configured failure cases.
- Never rewrite trace JSONL.

### Eval Runs

- Read existing eval run JSONL.
- Require explicit `run_id` when it cannot be derived safely.
- Preserve `needs_triage` as an observation, not a product-bug decision.

### Feedback

Write the correction-bearing `FeedbackRecord` first, verify the observed trace
hashes, then create its `FailureCase`. If case creation fails, feedback remains
valid and the CLI returns a retryable partial result.

SI0 ingestion never calls an LLM, database, Wren, Data Subagent, Context
Builder revision command, or eval-suite writer.

## 17. SI0 And SI1 CLI

Record feedback:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_agent_improvement.cli record-feedback `
  --trace-id trace_... `
  --type BUSINESS_TRUTH `
  --sentiment NEGATIVE `
  --comment "The old answer included shipped orders." `
  --expected-answer "721.80 CNY" `
  --business-statement "total_amount is denominated in CNY" `
  --business-statement "only completed orders count as realized revenue"
```

Ingest runtime failures:

```powershell
.\.venv-wren\python.exe -m data_agent_improvement.cli ingest-traces `
  --trace-path data\traces\data_subagent.jsonl
```

Ingest one eval run:

```powershell
.\.venv-wren\python.exe -m data_agent_improvement.cli ingest-eval `
  --run-path data\evals\runs\<run>.jsonl `
  --run-id <run-id>
```

Inspect and report:

```powershell
.\.venv-wren\python.exe -m data_agent_improvement.cli list-cases --status UNTRIAGED --pretty
.\.venv-wren\python.exe -m data_agent_improvement.cli show-case --case case_... --pretty
.\.venv-wren\python.exe -m data_agent_improvement.cli report --status UNTRIAGED
```

All commands support `--project-root` and `--registry-root`. The default
registry is `data/improvement_registry` under the resolved project root.

SI1 authority, grouping, and target lifecycle:

```powershell
.\.venv-wren\python.exe -m data_agent_improvement.cli record-authority `
  --feedback-id feedback_... --decision CONFIRM `
  --context-id data_agent_mvp --scope realized_revenue `
  --decided-by project-owner --reason "Scoped business owner confirmed" `
  --project-authority-confirmed

.\.venv-wren\python.exe -m data_agent_improvement.cli suggest-groups

.\.venv-wren\python.exe -m data_agent_improvement.cli create-finding `
  --context-id data_agent_mvp --grouping-mode SINGLETON `
  --case case_... --root-cause BUSINESS_SEMANTIC_GAP `
  --business-feedback feedback_... --business-scope realized_revenue

.\.venv-wren\python.exe -m data_agent_improvement.cli create-eval-target `
  --finding finding_... --question "What is realized revenue?" `
  --expected-value 721.8 --numeric-tolerance 0.001 `
  --required-filter "orders.status = completed" --required-unit CNY

.\.venv-wren\python.exe -m data_agent_improvement.cli submit-eval-target `
  --eval-target evaltarget_...
.\.venv-wren\python.exe -m data_agent_improvement.cli approve-eval-target `
  --eval-target evaltarget_... --reviewer-id business-reviewer
.\.venv-wren\python.exe -m data_agent_improvement.cli freeze-eval-target `
  --eval-target evaltarget_...
```

`record-authority` is a trusted local administrator action. The acknowledgement
flag prevents accidental use but is not authentication. A deployed service
must authenticate and authorize the operator before calling the same control
service.

Prepare and explicitly execute an SI2 semantic candidate job:

```powershell
.\.venv-wren\python.exe -m data_agent_improvement.cli prepare-semantic-job `
  --eval-target evaltarget_... --base-candidate-id candidate_... `
  --base-snapshot-path data\wren\base_project

.\.venv-wren\python.exe -m data_agent_improvement.cli verify-isolation-receipt `
  --job job_... --receipt data\tmp\si2_worker\isolation_receipt.json

.\.venv-wren\python.exe -m data_agent_improvement.cli execute-semantic-job `
  --job job_... --context-registry-root data\context_registry `
  --wren-home data\wren\home --wren-bin .venv-wren\Scripts\wren.exe `
  --isolation-receipt data\tmp\si2_worker\isolation_receipt.json --execute
```

Preparation never invokes Codex. The external worker must inject
`DATA_AGENT_ISOLATION_HMAC_KEY` and `DATA_AGENT_ISOLATION_ENVIRONMENT_ID`; an
operator must not paste either value into a prompt or persist the HMAC key. The
receipt is short-lived, HMAC-authenticated, and bound to the Job contract,
frozen EvalTarget, evidence manifest, schema fingerprint, logical writable
root, and active external environment ID.

The receipt is not a checkbox. Its signed probe map must confirm process-tree
isolation, child-policy inheritance, candidate-only writes, read-only evidence
and base snapshot mounts, denied reads/writes outside the workspace, denied
tool network, and minimized credentials. The Codex provider control plane may
remain reachable, but model-generated tools receive no network access. The
controller verifies and stores the immutable receipt before changing the Job
from `PREPARED` to `RUNNING`; the HMAC key and environment ID are excluded from
the sanitized Codex child environment.

The current Windows host cannot itself issue this receipt. Local
`codex-cli 0.144.1` exposes `--sandbox-state-readable-root` and
`--sandbox-state-disable-network`, but a strict read-allowlist probe reports
that restricted read-only access requires the elevated Windows sandbox backend.
Until a CI/container/VM or elevated backend performs the probes and signs the
receipt, real SI2 Codex execution remains blocked by design.

## 18. Report Contract

The read-only SI0 report includes:

- generation timestamp
- totals by source type and observable phase
- count of legacy traces missing runtime or Context identity
- case ID, question, source IDs, Context identity, signals, and evidence paths
- an explicit warning that root cause has not been classified

It excludes API keys, environment variables, passwords, result previews, full
Wren Context payloads, and arbitrary trace dumps. User text is length-bounded
and escaped for Markdown.

## 19. Security, Privacy, And Retention

- SI0 must never read `deepseek_apikey.txt`.
- Store records must not persist database passwords or connection environment
  values.
- Evidence paths must remain within project root unless a future import mode is
  explicitly designed.
- Raw trace access does not imply Codex access. The Evidence Packager must
  produce a minimized bundle and manifest before any later task execution.
- User IDs are optional and potentially sensitive.
- Result rows remain in existing traces and are referenced, not copied.
- Production retention is unresolved; real feedback and cases remain local
  runtime state and must not be committed.

## 20. Backward Compatibility

1. Missing trace `schema_version` means version `1`.
2. Missing Context, runtime, LLM, eval, or timing identity becomes `null`.
3. A legacy trace can still create a failure case.
4. Reports count incomplete identity so gaps remain visible.
5. New trace metadata starts as optional dataclass fields.
6. The existing unit-test suite must continue to pass before SI0 tests are
   added; do not hardcode a historical test count in acceptance logic.

## 21. Testing Contract

SI0 tests cover:

- model validation, enum validation, JSON round trip, and invalid IDs
- required fields for business truth and expected SQL
- generic feedback without a correction pair remains unverified
- correction-pair trace linkage and observed-output hash checks
- actor authority is recorded and cannot be self-granted
- data identity and mutable-data drift normalization
- atomic writes and immutable feedback
- deterministic case idempotency
- path traversal rejection
- failed and clarification trace ingestion
- successful trace exclusion
- failed and `needs_triage` eval ingestion
- negative feedback and business correction-pair ingestion
- legacy trace compatibility
- invalid JSON file/line reporting
- no network, database, Wren, DeepSeek, or Codex process
- invalid, expired, tampered, or wrong-environment isolation receipts cannot
  start an executor
- the isolation HMAC key and environment ID are not inherited by Codex
- feedback SQL is never executed
- result rows are not copied into cases
- evidence bundles redact/minimize raw trace payloads
- known secret field names are rejected or removed

## 22. SI0 Acceptance Scenarios

### Runtime Failure

A failed Wren dry-run creates one deterministic `RUNTIME_TRACE` case with phase
`WREN_DRY_RUN`, state `UNTRIAGED`, no root cause, and idempotent re-ingestion.

### Semantic Eval Failure

The StarRocks baseline where result equivalence passes but the answer omits
`CNY` creates one `EVAL_RECORD` case with an answer-missing-fragment signal and
trace/eval evidence references. It creates no Context revision.

### User-Declared Business Truth

The statements:

```text
total_amount is denominated in CNY
only completed orders count as realized revenue
```

create immutable feedback with a correction pair,
`user_declared_business_truth` provenance, observed trace hashes, expected
behavior, an authority claim, and a linked `USER_FEEDBACK` case. SI0 does not
grant the authority claim or create a grouped finding, eval target, Codex task,
or candidate.

### General Feedback Without Ground Truth

A negative rating with no expected behavior creates unverified feedback and a
`USER_FEEDBACK` case. It cannot independently create an approved EvalTarget.

### Benchmark Triage Safety

A BIRD record with `review_status=needs_triage` enters the inbox without
claiming the Data Subagent is wrong and without generating a modification.

## 23. SI0 Exit Criteria

SI0 is complete when:

1. new traces identify runtime, Wren Context, data, prompt, and eval versions
2. legacy traces remain readable
3. general feedback and optional correction pairs can be recorded against
   traces with explicit provenance and authority claims
4. runtime, eval, and feedback signals create idempotent failure cases
5. the failure inbox can be listed and reported without external services
6. no SI0 command can invoke Codex, Wren, a database, or publication
7. all existing and new unit tests pass
8. StarRocks semantic and BIRD triage scenarios have deterministic fixtures
9. project progress documentation records verification commands and results

## 24. Follow-Up Phases

### SI1: Grouped Findings And Frozen Eval Targets (Implemented)

- assign root-cause candidates
- create singleton findings for authorized high-confidence corrections
- cluster lower-confidence failures by Context, phase, entities, and signal
- support dismissal and business-truth requests
- verify actor authority before approving business truth for task execution
- create reviewed `GroupedFinding` records
- derive versioned result/semantic EvalTargets from approved evidence
- support `INVALID` and `SUPERSEDED` target versions
- keep target evals immutable during later candidate execution
- do not modify Context

### SI2: Semantic Bounded Codex Tasks (Controller Implemented)

- compose tasks from a reviewed finding and frozen eval target
- mount only a sanitized, manifested evidence bundle read-only
- create a writable isolated Wren candidate
- invoke existing `revise_candidate`
- run the frozen target with configured repetitions, smoke, and regression
- preserve `INCONCLUSIVE` separately from candidate failure
- stop at `REVIEW_REQUIRED`

### SI3: Engineering Worktree And Pull Request

- create an isolated writable Git worktree for prompt/code tasks
- provide production traces and accepted eval targets as read-only evidence
- allow bounded Codex changes to schema, mapper, prompt, adapter, or tests
- require unit tests, frozen target eval, full regression, and engineering review
- output a patch or pull request candidate, never a direct deployment

### SI4: Release Health And Rollback

- compare baseline and candidate scorecards
- require zero critical regressions
- keep Context publication and Git merge/deploy as separate release channels
- monitor recurrence and released Context/runtime health
- recommend, but do not autonomously execute, rollback

## 25. First End-To-End Acceptance

The first complete SI2/SI3 scenario reuses the StarRocks case:

```text
baseline:
  realized revenue includes shipped orders or the answer omits CNY

confirmed business truth:
  total_amount is CNY
  only completed orders are realized revenue

expected candidate answer:
  721.80 CNY
```

The future loop passes only when a correction pair links to the original trace,
the actor is authorized for the Context and business scope, the case becomes a
reviewed singleton or clustered finding, a result/semantic EvalTarget is frozen
before Codex starts, a bounded task creates a new immutable Context candidate,
repeated target and regression evals pass without inconclusive infrastructure
results, semantic diff and provenance are reviewable, and the candidate remains
unpublished until separate approval and publication.

SI0 provides the evidence foundation only. It intentionally does not create or
execute the improvement task.

## 26. Implementation Decision And Status

The first coding milestone implements SI0 exactly as a read-only evidence and
failure-inbox layer. This prevents the most dangerous failure mode in a
self-improving system: generating changes before the system can state which
version failed, why it was flagged, who supplied business truth, and which
evidence must be preserved.

Implemented on `feature/self-improvement-si0`:

```text
src/data_agent_improvement/
  models.py       typed FeedbackRecord and FailureCase contracts
  store.py        immutable atomic filesystem registry
  evidence.py     project-scoped JSONL evidence reading
  feedback.py     correction hash verification and feedback ingestion
  ingestion.py    trace/eval normalization and deterministic case IDs
  report.py       bounded Markdown failure-inbox reports
  cli.py          record, ingest, list, show, and report commands
```

The online `TraceRecord` now emits schema version 2 through the real
`DataSubagent` path. It records runtime, Context, data, LLM, eval, and timing
identity; Wren project fingerprints use a semantic-file allowlist; result and
schema evidence is hashed. Existing version-1 JSONL remains readable and is
never rewritten.

SI0 commands create no finding, EvalTarget, Codex task, candidate, approval,
publication, or rollback. SI1 adds only authority decisions, deterministic
grouping, reviewed findings, and frozen EvalTargets. Neither phase imports
Codex, DeepSeek, Wren, network, database, or subprocess runtime.

SI1 is implemented in `triage.py` and the extended store/CLI. It records
project authority confirmation separately from user feedback, rejects
unauthorized semantic singleton findings, separates benchmark triage by
signature, supports explicit finding dismissal, and enforces:

```text
DRAFT -> NEEDS_BUSINESS_REVIEW -> APPROVED -> FROZEN
```

Frozen target hashes cover the finding identity, question, result contract,
semantic constraints, SQL hints, and evidence references. Content cannot be
changed in place; corrected targets receive a new version and the old target
becomes `SUPERSEDED`. Authority is checked again at approval and freeze, so a
revocation blocks later execution readiness.

SI0 and SI1 now establish evidence, authority, finding, and frozen acceptance
contracts. The SI2 controller now packages a sanitized evidence bundle, creates
a tamper-evident job, and can invoke the existing Context revision engine only
from a frozen target. A real Codex candidate execution is still pending.

SI2 implementation details:

- `si2.py` owns evidence packaging, target/manifest integrity checks, job state,
  signed isolation-receipt enforcement, and result mapping.
- `isolation.py` owns Job binding, required probe policy, HMAC verification,
  environment matching, and receipt expiry.
- `codex_executor.py` adapts the bounded task to `revise_candidate`.
- the Codex process uses an ephemeral session, ignores user config, requests no
  approvals, omits web search, uses a JSON output schema, and receives a
  sanitized environment without DeepSeek, database, or isolation credentials.
- the outer Context Builder creates the candidate, runs Wren validation,
  generated smoke, repeated frozen target evals, and configured regressions.
- frozen numeric result contracts are enforced by the EvalRunner with their
  explicit tolerance; semantic filters currently use SQL-fragment fallback.
- `PASS` stops at `REVIEW_REQUIRED`; no SI2 path approves or publishes.
