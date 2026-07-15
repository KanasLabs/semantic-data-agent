# Context Builder Conversational Revision Plan

Last updated: 2026-07-15

Status: R0-R3 MVP implemented; R4 pending.

## 1. Product Goal

Context review must not require users to understand or manually edit Wren YAML.
The primary interaction should be natural language:

```text
candidate Context Layer
-> Builder presents evidence, assumptions, open questions, and test results
-> user provides business facts or requests changes in natural language
-> Codex follows the Wren generate-mdl skill and revises the candidate
-> Builder independently validates and tests the new version
-> user reviews the semantic change, not the YAML implementation
-> explicit approval is required before publish
```

The intended human role is to provide business truth and approval. Codex should
perform most schema investigation, Wren editing, rule/example authoring, and
repair work. The Builder remains responsible for versioning, safety boundaries,
evidence, deterministic acceptance, and publish control.

## 2. Why This Is Core

A Context Layer cannot become useful business context through schema discovery
alone. Database evidence can establish columns, observed uniqueness, join
coverage, enum values, null rates, and current data patterns. It cannot decide
company-specific truths such as:

- currency and accounting units
- which statuses count toward revenue
- business event meaning of date fields
- late-arriving data and orphan policies
- metric definitions and exclusions
- sensitive-field and access policies

The product should make these questions easy to answer conversationally and use
Codex to turn the answers into validated Context changes.

## 3. Responsibility Split

```text
User / domain expert
= business facts, corrections, priorities, explicit approval

Codex + Wren skill
= interpret feedback, inspect evidence, edit Context, add rules/examples/tests,
  explain assumptions, and repair failed candidates

Context Builder
= immutable base version, scoped workspace, database access policy, provenance,
  semantic diff, Wren acceptance, smoke/regression execution, lifecycle state,
  and publish gate
```

Codex may propose semantics, but it must not silently promote an inference into
business truth. Publish is never decided by Codex alone.

## 4. Target Workflow

```text
candidate version N
-> generate review packet
-> user natural-language instruction
-> persist structured change request
-> classify request and identify clarification needs
-> create revision workspace from version N
-> Codex revises Context with Wren skill
-> optional controlled database investigation
-> Wren validate / build / dry-run
-> smoke eval + regression eval
-> produce semantic diff and revision report
-> candidate version N+1 enters review
-> approve, request another revision, or reject
-> publish only after explicit approval
```

Example user instruction:

```text
total_amount is CNY. Revenue includes completed orders only. Cancelled and
shipped orders must not be counted as realized revenue.
```

Expected Codex work:

- update the field description and currency provenance
- add a grounded realized-revenue rule
- add or update SQL examples
- add a smoke/regression case for the new rule
- detect conflicts with existing rules or examples
- report any remaining ambiguity

Expected Builder work:

- preserve the original candidate
- store the user statement as first-class provenance
- validate all modified artifacts
- run existing and newly added evals
- show a semantic before/after diff
- refuse publish when acceptance fails or approval is absent

## 5. Decision Policy

Every requested semantic change should be classified before editing.

### 5.1 Evidence-resolvable

Codex may investigate and act without another user round when the answer can be
established from the allowlisted database and existing evidence.

Examples:

- whether a candidate relationship has orphan rows
- whether a value is currently unique and non-null
- observed enum values
- whether a SQL example executes

### 5.2 User-declared business truth

Codex may encode an explicit user statement, but the statement must be saved as
provenance rather than presented as database-derived fact.

Examples:

- `total_amount` is CNY
- completed orders define realized revenue
- signup date means account creation date

### 5.3 Ambiguous or high-impact

Codex must ask a focused clarification question before changing the candidate.

Examples:

- "make revenue correct" without a status policy
- a relationship that changes metric cardinality
- access, masking, or sensitive-data rules
- a request that conflicts with another approved rule

## 6. Version And State Model

Revision must create a new candidate version. It must not edit the published or
reviewed base version in place.

```text
DRAFT
-> AUTO_VALIDATING
-> REVIEW_REQUIRED
-> REVISION_REQUESTED
-> REVISING
-> AUTO_VALIDATING
-> REVIEW_REQUIRED
-> APPROVED
-> PUBLISHED
```

Failure and alternate states:

```text
VALIDATION_FAILED
SMOKE_FAILED
CLARIFICATION_REQUIRED
CHANGES_REQUESTED
REJECTED
STALE
```

A published version remains available until a newer approved version is
published. Failed revisions do not damage the previous healthy Context.

## 7. Required Artifacts

Each revision should preserve:

```text
revisions/<revision_id>/change_request.json
revisions/<revision_id>/user_instruction.md
revisions/<revision_id>/prompt.md
revisions/<revision_id>/codex_last_message.md
revisions/<revision_id>/semantic_diff.json
revisions/<revision_id>/revision_report.md
revisions/<revision_id>/validation.json
revisions/<revision_id>/smoke_eval.json
revisions/<revision_id>/regression_eval.json
revisions/<revision_id>/open_questions.json
```

`change_request.json` should include at least:

```text
revision_id
base_context_version
candidate_context_version
user_instruction
requested_scope
provenance_type
risk_level
status
created_at
```

Semantic diff should summarize domain-level changes rather than only line-level
YAML changes:

- added/removed/changed Models and fields
- changed descriptions, types, and keys
- added/removed/changed Relationships and cardinality
- changed Rules, metrics, caveats, and SQL Examples
- newly introduced assumptions or unresolved questions
- changed smoke/regression coverage

## 8. CLI Surface

The existing `enrich-with-codex --instructions` is a useful execution primitive,
but it is not the final product surface because it edits without a complete
candidate lifecycle.

Implemented R1/R2 commands:

```powershell
context-builder register-candidate `
  --context-id data_agent_mvp `
  --project-dir data\wren\starrocks_mvp_wren_project

context-builder revise-candidate `
  --candidate <candidate_id> `
  --instruction "total_amount is CNY; completed defines realized revenue" `
  --regression-suite data\evals\cases\starrocks_mvp_smoke.jsonl `
  --regression-suite data\evals\cases\starrocks_semantic_improvement_candidates.jsonl `
  --execute
```

`--execute` runs generated smoke eval by default. Use `--no-evals` only for
isolated debugging. Business acceptance should pass explicit regression suites.

Proposed R3 commands:

```powershell
context-builder review-candidate --candidate <candidate_id>

context-builder answer-review-question `
  --revision <revision_id> `
  --answer "Late-arriving orders may remain orphaned for up to one day"

context-builder approve-candidate --candidate <candidate_id>

context-builder publish-candidate --candidate <candidate_id>
```

Approval and publish should remain separate operations. Approval confirms
semantic review; publish changes the Registry version available to downstream
agents.

## 9. Safety And Acceptance Rules

- Never modify a published Context in place.
- Never expose database credentials to Codex prompts or revision artifacts.
- Reuse controlled read-only database tools such as `starrocks-query`.
- Restrict Codex writes to the revision workspace.
- Run Wren validate/build/dry-run after every revision.
- Run candidate smoke cases and previously passing regression cases.
- Reject a revision when mandatory artifacts or provenance are missing.
- Do not let Codex self-approve or self-publish.
- Require explicit user approval for high-impact semantic, relationship,
  metric, currency, time, access, and privacy changes.

## 10. Implementation Phases

### R0: Contract

- [x] define candidate/revision/HITL IDs and directory layout
- [x] define candidate and revision state transitions
- [x] define change request, semantic diff, and review packet schemas
- [x] define evidence and user-statement provenance
- [x] persist clarification and approval tasks separately
- [x] require answered clarification before revision resumes
- [x] require completed approval HITL before revision approval
- [x] use atomic JSON writes and expected-version/status checks

### R1: Revision Engine

- [x] implement `register-candidate` for existing Wren candidates
- [x] implement `revise-candidate`
- [x] copy a base candidate into an isolated new version
- [x] run Codex with the candidate project as its writable working directory
- [x] reuse the bounded Codex repair and independent Wren acceptance loop
- [x] preserve prompts, Codex messages, validation, instruction, and result artifacts
- [x] move successful revisions to `REVIEW_REQUIRED`
- [x] retain failed candidates as `VALIDATION_FAILED` without changing the base

### R2: Test And Diff

- [x] require and validate structured `revision_outcome.json` from Codex
- [x] convert `clarification_required` outcomes into persistent HITL tasks
- [x] reject stale outcome files copied from an earlier candidate
- [x] generate conservative candidate smoke cases
- [x] run candidate smoke and configured regression suites through Data Subagent
- [x] move failed eval acceptance to `SMOKE_FAILED`
- [x] produce semantic before/after diff for Models, fields, Relationships,
  rules, SQL Examples, assumptions, questions, and test coverage

### R3: Review And Publish

- [x] generate review packet after Wren and eval acceptance
- [x] persist natural-language clarification answers with business provenance
- [x] resume the same revision in a new Codex execution after answers
- [x] preserve separate artifacts for every resume execution
- [x] implement review, approve, reject, and request-changes behavior
- [x] distinguish business-truth answers from review-decision provenance
- [x] keep approval and publish as separate operations
- [x] introduce an atomic published Context pointer and publication history
- [x] support rollback to a previous published candidate

### R4: Main Agent Integration

- route natural-language review requests to the revision engine
- surface clarification questions and revision status
- allow Data Subagent use only for `PUBLISHED + HEALTHY` Context versions

## 11. First Acceptance Scenario

Use the current local StarRocks candidate:

```text
base candidate: data_agent_mvp Context
user instruction: total_amount is CNY; only completed orders are realized revenue
```

The first end-to-end revision is complete when:

1. the original candidate remains unchanged
2. a new candidate version is created
3. the user instruction is stored as business provenance
4. Codex updates descriptions/rules/examples without guessing extra semantics
5. Wren validate/build/dry-run pass
6. a CNY realized-revenue smoke case passes
7. previous StarRocks smoke cases still pass
8. semantic diff and open questions are reviewable
9. the candidate remains unpublished until explicit approval

Acceptance completed on 2026-07-15:

```text
revision: revision_e4af8208c51040f38b6a6877a58607ff
candidate: candidate_1e1f8ebee1484aad8530cee1d773dfc0
state: REVIEW_REQUIRED
generated smoke: 3/3 passed
existing StarRocks regression: 3/3 passed
completed-only CNY regression: 1/1 passed
result: 721.80 CNY
publication: not performed
```

The user subsequently reviewed and approved this candidate through the HITL
gate. Candidate and revision state are now `APPROVED`; approval provenance is
`user_review_decision`. The user then separately confirmed publication. The
candidate is now `PUBLISHED`, and publication
`publication_35185565607f4d0f9c4f4d5b268a11f6` is the active atomic pointer for
Context `data_agent_mvp_revision_acceptance`.

The generated relationship smoke uses a joined row count. Detail-row prompts
were rejected because they can induce duplicate output columns, and explicit
row-limit prompts can conflict with Wren CLI's own query limit. Business
semantics continue to require explicit regression suites.

## 12. Current Boundary

Already available:

- skill-first Context generation for SQLite and StarRocks
- controlled StarRocks investigation with evidence
- Codex enrichment prompt primitive
- outer Wren validation and bounded repair
- smoke-eval generation and Data Subagent eval runner
- filesystem-backed candidate, revision, and HITL records
- legal lifecycle transitions with stale-state checks
- persisted user-declared business provenance
- clarification and approval task gates
- semantic-diff and review-packet artifact contracts
- bootstrap registration for existing Wren candidates
- isolated candidate workspace creation through `revise-candidate`
- Codex + Wren skill execution with bounded outer repair
- independent Wren validate/build/optional dry-run acceptance
- revision prompts, messages, validation, and final-result artifacts
- structured Codex revision outcome validation
- automatic clarification-to-HITL task creation
- generated semantic before/after diff content
- automatic smoke eval after CLI revision execution
- configured regression-suite execution through the existing Data Subagent CLI
- generated review packet containing diff, provenance, validation, and eval results
- clarification answer and same-revision resume workflow
- explicit human approval/rejection commands
- automatic `CHANGES_REQUESTED` when revising a candidate under review
- separate candidate publish and Context rollback commands
- atomic `contexts/<context_id>/published.json` pointer with history
- explicit per-execution controlled StarRocks re-investigation authorization
- Builder validation and archival of revision query evidence

Not yet available:

- downstream Main Agent routing through the published Context pointer
- automatic health monitoring of an already published Context

R0 implementation:

```text
src/data_subagent_context_builder/revision_store.py
tests/test_context_builder_revision_store.py
```

R1 implementation:

```text
src/data_subagent_context_builder/revision_engine.py
tests/test_context_builder_revision_engine.py
```

R2 implementation:

```text
src/data_subagent_context_builder/semantic_diff.py
src/data_subagent_context_builder/revision_eval.py
tests/test_context_builder_semantic_diff.py
tests/test_context_builder_revision_eval.py
```

The generated smoke suite is intentionally conservative and schema-oriented.
Business-semantic acceptance cases must be supplied as regression suites until
a later change-request-aware test generator is designed.

R3 implementation:

```text
src/data_subagent_context_builder/review_workflow.py
tests/test_context_builder_review_workflow.py
```

Approval confirms review and changes candidate/revision state to `APPROVED`.
It does not change the published pointer. `publish-candidate` is a separate
explicit operation. Rollback changes only the active pointer to another already
published candidate and records a new publication-history event.

Controlled StarRocks re-investigation is available for `revise-candidate` and
`resume-revision`. Authorization must be provided explicitly for every
execution and is never inherited from an older artifact. Codex receives the
Builder `starrocks-query` command with Catalog/Database, row, timeout, and SQL
restrictions. Evidence is validated without returned rows and archived with the
execution.

The StarRocks account remains the hard security boundary and must independently
enforce read-only, database-scoped permissions. Builder allowlists are defense
in depth and do not replace database grants.

The state store is deliberately not exposed to Codex. Future execution code
must ask the Builder to perform transitions and writes; Codex may only modify
the isolated candidate workspace and return proposed artifacts.
