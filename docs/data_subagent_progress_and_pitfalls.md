# Data Subagent Progress And Pitfalls

Last updated: 2026-07-27

This document is the project memory for future Codex sessions. Keep it concise
but current.

## 1. Current Status

The project has a runnable Data Subagent MVP and a runnable first WrenAI Context
Builder implementation.

### Public repository release preparation

Prepared the cleaned-history candidate for a fresh public repository on
2026-07-27. Added an MIT license for original project code and documentation,
plus `THIRD_PARTY_NOTICES.md` to keep BIRD Mini-Dev adaptations under CC BY-SA
4.0 and identify the jaffle_shop and TPC-H demo sources. Updated the public
documentation index and eval-case README to make those boundaries explicit.

The existing repository remains the private archive because GitHub-managed
merged-PR references retain pre-rewrite commits. The public repository is
created from the cleaned `master` history rather than by changing the archive's
visibility.

Public-candidate verification:

```text
full unit suite: 175 passed
current privacy-pattern scan: 0 matching files
current high-confidence credential scan: 0 matching files
required license/notice files: present
git diff --check: passed
```

The first Gitleaks run in the fresh public repository reported two
`generic-api-key` false positives in the BIRD discovery snapshot. Both values
are 64-character hexadecimal integrity hashes under
`single_key_check_hash` and `composite_key_check_hash`; no credential was
present. `.gitleaks.toml` keeps the default rules and adds one line-level regex
allowlist limited to those two field names and the exact 64-hex hash format. It
does not exclude the snapshot file or weaken scanning for other values.

Publication verification:

```text
public repository: https://github.com/appodd/semantic-data-agent
anonymous GitHub API access: HTTP 200
anonymous single-branch clone: passed
public heads: master only
GitHub license detection: MIT
Gitleaks rerun with precise hash allowlist: passed
anonymous-clone privacy-pattern scan: 0 matching files
private pre-public archive: retained and read-only
```

### Public-history privacy preparation

Prepared a privacy-safe Git history on 2026-07-22 before any repository
visibility change. The rewrite normalized commit author and committer identity
to the GitHub noreply address and removed user-specific workspace paths from
all 19 commits. A complete pre-rewrite mirror is retained only under the local,
Git-ignored `data/tmp/` backup area.

Removed generated Context Builder last-message and validation-output files that
captured local execution paths. `.gitignore` now excludes those onboarding
artifact directories so future local runs do not stage them accidentally.

Verification in the isolated rewritten clone:

```text
commit identity scan: GitHub noreply only
current privacy-pattern scan: 0 matching files
full-history privacy-pattern scan: 0 matching files
full-history high-confidence credential scan: 0 matching files
full unit suite: 175 passed
git diff --check: passed
```

GitHub caveat: force-pushing branches does not rewrite GitHub-managed
`refs/pull/*` for already merged pull requests. The old PR head references are
not writable through normal Git pushes. Do not treat the existing repository as
fully scrubbed for a visibility change until GitHub Support removes those
references, or a fresh repository is created from the cleaned history.

### Repository documentation and secret-scan hygiene

Prepared a repository hygiene update on 2026-07-22. Added a root `README.md`
for the three workstreams and a curated `docs/README.md` index that separates
reviewable architecture/setup documentation from internal engineering memory.
The repository keeps both categories under version control. The engineering
memory was reviewed for privacy before public release and remains subject to
the documentation safety rules in `docs/README.md`.

Removed user-specific absolute Windows paths from tracked documentation and the
TPC-H onboarding report. Added a GitHub Actions Gitleaks workflow for pushes to
`master`, pull requests, and manual runs. Local API-key files, `.env`, runtime
traces, eval outputs, local Wren state, and improvement registry data remain
excluded by `.gitignore`.

Production onboarding/discovery snapshots must be reviewed separately because
schema samples or observed values may contain real business data even when no
credential is present. The committed TPC-H snapshot contains synthetic demo
data only.

Verification:

```text
full unit suite: 175 passed
tracked user-specific absolute-path scan: no matches
high-confidence credential-pattern scan: no real secrets found
GitHub PR Gitleaks check: passed
git diff --check: passed
```

The first pull-request run exposed a workflow-permission pitfall rather than a
secret finding: `gitleaks-action` needs `pull-requests: read` to inspect PR
commits. The workflow grants that read-only permission in addition to
`contents: read`; it does not receive write access.

### First GitHub milestone preparation

Prepared the first remote-ready project milestone on 2026-07-22. The selected
change set covers the controlled SI3 source-candidate and routing workflow,
shared candidate evaluation, development-only release guards, semantic-unit
summarization, related tests, and the current architecture notes. Local API-key
files and COMP7706 draft logbooks are excluded by `.gitignore`; presentation
artifacts are reviewed and committed separately from runtime code.

Verification before the local milestone commit:

```text
full unit suite: 175 passed
git diff --cached --check: passed
named API-key files: ignored and not staged
```

No GitHub remote was configured and no push was performed during this
preparation step.

### Project presentation content script

Added `docs/presentation/data_agent_presentation_script.md` on 2026-07-20 as
the reviewed-content source for a future project presentation deck. The default
deck is a 12-15 minute Chinese internship presentation for a mixed technical
and business audience.

The script defines a 12-slide narrative from the Text-to-SQL reliability gap
through the three separated workstreams, controlled online workflow, real ReAct
repair, Context Builder onboarding, and the development-only SI2 improvement
case. It also includes speaker notes, timing, visual guidance, a fact-check
table, asset and security constraints, backup slides, likely Q&A, and a PPT
generation checklist.

Added `docs/presentation/data_agent_presentation_script_en.md` as the primary
source for the actual English PPT and spoken presentation. Its on-slide text,
speaker notes, transitions, terminology, pronunciation guidance, and Q&A are in
natural presentation English rather than literal translation. Each main slide
also includes a short Chinese comprehension note. The original Chinese script
is retained as the presenter's reference rather than the PPT generation source.

The presentation constraint was later tightened to a strict five minutes.
Added `docs/presentation/data_agent_presentation_script_en_5min.md` as the new
primary PPT source and reclassified the 12-slide English script as the backup
content bank. The final five-minute version has seven main slides and `561`
spoken English words after the Slide 3 workflow correction. That is
approximately `4:41` at 120 words per minute or `4:29` at 125 words per
minute, leaving only a controlled slide-transition buffer under the hard
limit. It retains the overall architecture, controlled online workflow, real
ReAct repair, Context Builder, development-only improvement case, verification,
personal contribution placeholder, limitation, and final takeaway. Detailed
SI0-SI4, isolation, dataset, and workflow material moves to backup slides.

The presenter's contribution statement was confirmed as implementing a
runnable end-to-end MVP loop: the controlled data-questioning runtime, Wren and
DeepSeek integration, and the connection from traces and evaluations to a
reviewable improvement workflow.

Corrected Slide 3 in the five-minute Markdown source to match the implemented
runtime exactly: clarity checking precedes context retrieval; both Wren
`dry-plan` and `dry-run` failures can enter bounded LLM repair; repaired SQL
passes the read-only guardrail again; execution failure is terminal; and trace
finalization covers success, failure, and clarification outcomes.

Split the former combined Context Builder and self-improvement page into two
focused slides without increasing the spoken word count. Slide 5 now explains
how the upstream Context Builder creates and validates a Wren candidate, while
Slide 6 explains the development-only evidence-to-candidate improvement flow
and its `REVIEW_REQUIRED` human gate. The results and contribution page moves
to Slide 7. The existing generated PPTX, PDF, previews, and PowerPoint generator
still represent the earlier six-slide layout and must be regenerated before
they are treated as final artifacts.

Generated the final editable presentation artifacts with native PowerPoint
vector shapes and six English Speaker Notes:

```text
docs/presentation/data_agent_project_presentation_en_5min.pptx
docs/presentation/data_agent_project_presentation_en_5min.pdf
docs/presentation/data_agent_project_presentation_en_5min_preview/
scripts/generate_data_agent_presentation.ps1
```

The generator reads the six Speaker Scripts from the five-minute Markdown,
creates a 16:9 dark-theme deck, writes the notes into PowerPoint Notes pages,
and exports PDF plus 1600x900 PNG previews. The deck was visually reviewed
slide by slide; one incorrect error-loop arrow was corrected so the database
error now originates from Wren `dry-run` rather than the SQL Guardrail.

Verification:

```text
PowerPoint generation: passed, 6 slides
PPTX notes XML: 6/6 present
opening and contribution/takeaway notes: present
PDF export: passed
PNG export: 6/6 at 1600x900
visual overflow/alignment review: passed
git diff --check: passed
```

The cover intentionally retains editable `[Your Name]` and
`[University / Department]` placeholders because those values have not yet
been provided. No runtime code, Wren state, trace, eval artifact, registry, or
secret was changed.

The presentation facts use the latest recorded results: full unit suite
`146/146`, BIRD Verified10 `10/10` with `7 auto_pass` and `3 needs_triage`, and
the realized-revenue development candidate's smoke `3/3` plus frozen target
`3/3`. The script explicitly prevents presenting that development-only
candidate as formally isolated, approved, publishable, or production-ready.
Personal contribution fields remain placeholders until the presenter confirms
the actual work split. No runtime code, Wren state, trace, eval artifact, or
registry data was changed.

### BIRD Mini-Dev StarRocks Context Builder integration test

Completed a realistic five-table Skill-first integration test on 2026-07-16
using BIRD Mini-Dev `debit_card_specializing`. The old mechanical SQLite Wren
project was not reused.

Added a reproducible loader:

```text
scripts/setup_starrocks_bird.py
tests/test_setup_starrocks_bird.py
```

Loaded and source/target row-count verified:

```text
database: bird_debit_card_specializing
customers: 32,461
gasstations: 5,716
products: 591
transactions_1k: 1,000
yearmonth: 383,282
```

Real `generate-from-starrocks` result from an empty Wren project:

```text
project: data/wren/starrocks_bird_debit_card_specializing_wren_project
duration: 1,169.4 seconds
controlled queries: 37 executed
models: 5
relationships: 4
repair rounds: 0
wren validate/build/dry-run: passed
artifact validation: passed
```

The candidate accepted four complete, zero-orphan snapshot relationships:
transactions-to-customers, transactions-to-gasstations,
transactions-to-products, and yearmonth-to-customers. It did not reproduce the
old broken `customers.None` relationship. It rejected unsupported `CardID`,
`ChainID`, and direct transactions-to-yearmonth joins.

The original 30 BIRD cases were manually classified instead of trusted as
absolute truth:

```text
audit: data/evals/audits/bird_mini_dev_debit_card_specializing_audit.jsonl
verified: 9
corrected: 2
ambiguous: 3
invalid_gold: 9
dialect_issue: 7
```

The initial reviewed subset covers all five tables and four relationships:

```text
suite: data/evals/cases/bird_mini_dev_debit_card_specializing_verified10.jsonl
first run: 20260716-112148-bird_starrocks_debit_card_verified10, 4/10
rerun: 20260716-112855-bird_starrocks_debit_card_verified10_rerun, 10/10
review status: 7 auto_pass, 3 needs_triage
```

The three triage cases passed the explicit business expectations but returned
an additional explanatory aggregate column or a numerically equivalent ratio
at different precision. Keep them as triage rather than forcing SQL-string or
projection identity.

Representative rerun traces:

```text
currency ratio: trace_f732255a68a644df9da509dacbe2c890
least LAM consumption: trace_ea6b106a0c8946c88dc392003c895708
CZE product descriptions: trace_5672ef2186d445b29e681bf627fe604d
customer currency: trace_5286d3d9f6f44a5b9266693b5177dee8
CZE time-window count: trace_489b912b08654148acb62887562cb4f2
```

Test-chain hardening discovered by the first run:

- Wren CLI `query --limit` appended another LIMIT when semantic SQL already
  ended in `LIMIT`, causing valid top-1 queries to fail during execution.
  `WrenCliAdapter` now omits the CLI limit for an existing trailing LIMIT and
  clamps an excessive existing limit to the configured safety bound.
- Czech product descriptions caused the Windows GBK console to fail after the
  eval artifacts were already written. The Data Subagent CLI now configures
  UTF-8 stdout explicitly.
- Gold result comparison now normalizes insignificant floating execution noise.
- SQL-fragment assertions no longer require one specific conditional-aggregate
  form when equivalent COUNT subqueries are valid.

Detailed notes are in `docs/bird_starrocks_context_builder_test.md`. Latest
full verification: `90` unit tests passed.

### BIRD real clarification and resume HITL test

Completed a real ambiguity-gate test on 2026-07-16 using original BIRD case
0012. The initial request intentionally omitted the customer qualification
grain, denominator, and NULL policy.

```text
registry: data/tmp/bird_hitl_clarification/registry
base candidate: candidate_c60febb64e924156876184a9242f8a00
revision: revision_38103177ef9249b18c889190275f065f
candidate: candidate_6b53e453eab54042b91e70e8c3e61e1c
clarification task: task_548105cdcfd34159abcd2809d73e9616
```

Codex did not guess. It returned `clarification_required`; Builder persisted two
focused questions and left the candidate `DRAFT`. The user then declared:

- a LAM customer qualifies when any `yearmonth` row has `Consumption > 46.73`
- the denominator is all distinct LAM customers with a `yearmonth` record
- NULL Consumption keeps the customer in the denominator but does not qualify

Both answers were stored as `user_declared_business_truth`. `resume-revision`
updated two field descriptions, one rule, and added one confirmed SQL example.
It changed no Models or Relationships and recorded zero assumptions and zero
unresolved questions.

Deterministic target result:

```text
denominator customers: 3,611
qualifying customers: 3,594
percentage: 99.5292163%
```

The first resumed acceptance entered `SMOKE_FAILED` even though the answer was
correct because the new test required the literal `DISTINCT` syntax and compared
a Wren decimal string to a float. The eval normalizer now handles numeric strings
and stable floating precision; the business suite accepts equivalent per-customer
`GROUP BY + MAX` SQL. `retry-revision-evals` reused the same Context without
another Codex call.

Final review-gate result:

```text
candidate/revision after review: APPROVED / APPROVED
wren validate/build: passed
generated smoke: 3/3
BIRD Verified10 regression: 10/10
clarified semantic regression: 1/1
semantic trace: trace_84a76a03435d4c2d8c022dd96ccf9652
review packet: generated
approval task: task_bc1cd9b98d3243d2abc2401c39b0bba2
approval answer: answer_14f441c661d64e0eb707634308ad87e0
approval provenance: user_review_decision
publication: not performed
```

This verifies the real clarification pause, resume, review, and explicit human
approval path. Approval did not create a published pointer; publication still
requires a separate explicit user confirmation. Codex did not approve or
publish automatically.

### Controlled self-improvement architecture and SI0 contract

Added `docs/data_agent_self_improvement_architecture_si0_contract.md` to define
the separate background `data_agent_improvement` workstream. The confirmed
reference is OpenAI, Thrive Holdings, and Crete's engineering case:

```text
https://openai.com/index/building-self-improving-tax-agents-with-codex/
```

The transferable Tax AI pattern is production correction and eval driven, not
model-weight training: business correction pairs and production traces become
grouped findings; a reviewed EvalTarget is frozen before Codex starts; Codex
receives read-only evidence and a writable candidate workspace; outer eval and
regression gates produce either a Context review packet or a Git PR candidate.
Codex never self-approves, publishes, merges, or deploys.

The agreed SI0 boundary is intentionally read-only:

```text
versioned trace + eval result + optional business correction pair
-> normalized failure case
-> immutable improvement registry
-> reproducible triage report
```

SI0 adds version identity, correction-bearing `FeedbackRecord`, `FailureCase`,
an atomic and idempotent Improvement Store, read-only ingestion/report CLI
contracts, backward compatibility for current trace JSONL, and deterministic
acceptance scenarios. It must not invoke Codex, Wren, a database, Context
revision, approval, publication, or rollback.

The revised phase boundary is:

```text
SI0: correction pairs, versioned traces, FailureCase inbox
SI1: deterministic triage, GroupedFinding, frozen EvalTarget
SI2: bounded Codex task over an isolated Wren candidate
SI3: bounded Codex task over a Git worktree and PR candidate
SI4: release health, recurrence monitoring, and rollback recommendation
```

Context Registry publication and Git merge/deploy are separate release
channels. In both channels the target eval is controlled by the outer workflow
and cannot be weakened by the Codex candidate executor.

A project-fit review then narrowed the Tax AI transfer instead of copying its
tax-form assumptions directly:

- `FeedbackRecord` is the general envelope; a business correction pair is
  optional and ordinary ratings remain unverified.
- an authorized high-confidence correction may create a singleton finding;
  lower-confidence feedback still requires clustering or human triage.
- EvalTargets prefer result equivalence, business invariants, units, and safety
  constraints over exact SQL-string identity.
- EvalTargets are versioned through draft/review/approved/frozen and may be
  superseded or invalidated only by a new outer-workflow decision.
- Trace v2 includes data identity and result/schema hashes because production
  databases are mutable.
- candidate results distinguish `INCONCLUSIVE` and `EVAL_TARGET_INVALID` from
  real regressions.
- a minimized Evidence Packager sits between raw traces and later Codex tasks;
  raw `result_preview` rows are not automatically exposed.
- actor authority must be verified before SI2 can encode business truth into a
  Wren candidate.

The SI0 terminology was narrowed for the project's real users. “Expert” does
not mean a SQL, Wren, Codex, or company-wide domain expert. A
`BUSINESS_CONTRIBUTOR` may state expected behavior in natural language, while
an `AUTHORIZED_BUSINESS_CONFIRMER` is verified only for named Context IDs and
narrow scopes such as a field unit, status policy, or metric denominator. An
authority claim is separate from project-confirmed authority. The same person
may confirm business truth and approve a candidate in the MVP, but these remain
two explicit recorded actions; “unknown” remains unresolved rather than being
guessed by Codex.

Natural-language feedback does not by itself require Codex SDK. SI0 can store
text deterministically through a CLI, form, chat UI, or ordinary API. Codex SDK
belongs to SI2/SI3 candidate investigation and repair, where it may also turn
unresolved evidence into focused business questions. It does not grant
authority, decide business truth, or approve its own candidate.

These adjustments preserve the Tax AI correction/eval/bounded-worktree pattern
while fitting Wren semantic SQL, equivalent-query evaluation, noisy BIRD labels,
low-volume MVP operation, DeepSeek variability, and existing HITL publication.

Documentation verification:

```text
UTF-8/title/code-fence structure check:
OK sections=26 code_fences=72 roles=4 sdk_boundary=SI0_vs_SI2

Tax AI contract term check across the SI0 Markdown and both architecture HTML pages:
OK correction pair / GroupedFinding / EvalTarget / Bounded Codex Task / dual release

Project-fit contract check:
OK singleton / data_identity / scoped business confirmer / authority claim vs.
verified authority / natural-language SI0 vs. Codex SDK SI2 boundary / semantic
result contract / Evidence Packager / INCONCLUSIVE / EVAL_TARGET_INVALID

git diff --check -- runtime_codex_hybrid_self_improving.html intelligent_text2sql_agent_architecture.html docs/data_subagent_progress_and_pitfalls.md
OK
```

No runtime code, local Context Registry, Wren state, trace, or eval artifact was
changed during this design-only milestone.

### Controlled self-improvement SI0 implementation

Implemented the SI0 evidence foundation on 2026-07-16 in the separate
`data_agent_improvement` package:

```text
src/data_agent_improvement/models.py
src/data_agent_improvement/store.py
src/data_agent_improvement/evidence.py
src/data_agent_improvement/feedback.py
src/data_agent_improvement/ingestion.py
src/data_agent_improvement/report.py
src/data_agent_improvement/cli.py
```

The implementation provides:

- typed and validated `FeedbackRecord`, optional correction pairs, scoped actor
  authority claims, and `FailureCase` records
- immutable atomic feedback writes and deterministic, idempotent case creation
- legacy/version-2 trace ingestion and failed/`needs_triage` eval ingestion
- negative/correction feedback case creation while positive ordinary ratings
  remain feedback-only
- observed answer/SQL hash verification without copying result rows
- project-root evidence path enforcement and credential-pattern rejection or
  redaction
- read-only list/show operations and bounded Markdown inbox reports
- a CLI that records feedback, ingests traces/evals, lists/shows cases, and
  writes reports under the Git-ignored `data/improvement_registry/`

The real Data Subagent trace path now emits schema version 2 with runtime,
Context, data, LLM, eval, and timing identity. Wren fingerprints use an explicit
semantic-file allowlist; schema and full result evidence are represented by
SHA-256 hashes. Eval runs attach `run_id`, `eval_id`, and `suite_name` to their
traces. Existing trace JSONL is not rewritten and missing version metadata is
normalized as legacy version 1 during ingestion.

Verification:

```text
SI0 targeted tests: 24 passed
full unit suite at SI0 milestone: 114 passed
CLI help/list smoke: passed
git diff --check: passed
forbidden SI0 imports: no Codex / DeepSeek / Wren / subprocess / urllib
```

No real trace file, eval run, Wren state, Context Registry, or Improvement
Registry record was created during verification; tests use temporary
directories. SI1 was implemented in the following milestone.

### Controlled self-improvement SI1 implementation

Implemented deterministic SI1 triage and frozen acceptance contracts on
2026-07-16. `src/data_agent_improvement/triage.py` and the extended models,
store, and CLI now provide:

- immutable `AuthorityDecision` records, including explicit revocation
- a trusted-local-admin acknowledgement gate for authority CLI actions
- deterministic group suggestions by Context, failure phase, and signal type
- authorized semantic singleton findings and clustered lower-confidence cases
- separation of `EVAL_NEEDS_TRIAGE` findings from product semantic findings
- explicit Finding dismissal with reviewer, timestamp, and reason
- versioned EvalTargets with result and semantic constraints
- `DRAFT -> NEEDS_BUSINESS_REVIEW -> APPROVED -> FROZEN` lifecycle enforcement
- authority re-checks at approval and freeze
- content hashes that cannot be weakened or rewritten in place
- `INVALID` and `SUPERSEDED` target terminal paths

Business truth, authority confirmation, target approval, and freezing are
separate recorded actions. The same MVP user may perform business confirmation
and approval, but the records remain distinct. The local CLI does not
authenticate `decided_by`; a deployed API must authenticate and authorize that
administrator before calling the control service.

Verification:

```text
SI0/SI1 targeted tests: 32 passed
full unit suite: 122 passed
SI1 CLI help and authority acknowledgement smoke: passed
git diff --check: passed
forbidden improvement imports: no Codex / DeepSeek / Wren / subprocess / urllib
```

At the SI1 milestone, no Codex task, candidate workspace, Wren revision,
database access, approval, publication, merge, or deployment was triggered.
The following milestone adds the bounded SI2 controller.

### Controlled self-improvement SI2 controller implementation

Implemented the SI2 bounded semantic-candidate controller on 2026-07-16. The
implementation prepares and verifies jobs without executing by default:

```text
src/data_agent_improvement/si2.py
src/data_agent_improvement/codex_executor.py
```

SI2 now provides:

- `BoundedCodexTask` and `ImprovementJobResult` contracts
- minimized evidence bundles containing findings, frozen targets, cases,
  correction feedback, authority decisions, and a generated target eval
- no copied raw trace payloads or result preview rows
- per-file evidence hashes plus a frozen manifest hash
- frozen target hash verification before and after candidate execution
- separate `EVAL_TARGET_INVALID` and evidence/infrastructure `INCONCLUSIVE`
  outcomes
- a signed, short-lived external isolation receipt gate before any executor call
- a replaceable `SemanticCandidateExecutor` protocol
- a Context Builder adapter that creates a new candidate through
  `revise_candidate`, repeats the frozen target suite, runs smoke/regression,
  and stops at `REVIEW_REQUIRED`

The current real adapter uses the locally installed `codex exec` CLI rather
than hard-coding an SDK dependency. The installed CLI help verified
`workspace-write`, `--ephemeral`, `--ignore-user-config`, `--output-schema`,
JSONL, and non-interactive execution. The OpenAI `openai-docs` manual helper was
attempted inside and outside the sandbox, but the official manual endpoint
returned HTTP 403; Docs MCP was unavailable. The executor therefore uses only
locally verified flags and remains replaceable by a future official SDK
adapter.

Codex execution hardening:

- candidate workspace is the only Codex writable root owned by the revision
  workflow
- evidence and base snapshot are referenced as read-only roots and re-hashed
  after execution
- Codex runs ephemerally, ignores user config, receives a JSON output schema,
  omits `--search`, and uses `approval_policy=never`
- the child environment is allowlisted and excludes DeepSeek keys and database
  passwords
- CLI execution requires `--execute`, a verified `--isolation-receipt`, and
  external runner-injected HMAC/environment identity
- the registered base candidate path must match the prepared SI2 base snapshot
- target result tolerance is enforced by the EvalRunner; required semantic
  filters use the existing SQL-fragment fallback in the generated target suite

The external isolation receipt is not merely informational. The host sandbox
must prevent Codex from reading unrelated repository secrets and must enforce
tool network policy; `workspace-write` and omission of `--search` do not by
themselves prove filesystem read allowlisting or host-level network denial.

Automated execution verification uses only fake executors; no real Codex task
was launched:

```text
SI0/SI1 targeted tests: 32 passed
SI2 targeted tests: 7 passed
full unit suite: 130 passed
Context Builder Codex/revision regressions: passed
git diff --check: passed
```

A real prompt-only SI2 acceptance was then completed without `--execute`. The
fixture used a real failed revenue answer and a scoped business correction:

```text
trace: trace_295ceda0754b4129b09f8259835f8d82
observed answer: $1,131.70
observed filter: status != 'cancelled'
business truth: only completed orders count as realized revenue
expected result: 721.80 CNY
```

The frozen control records were:

```text
base candidate: candidate_2d8fa11494c24f5785f0a8e33739a598
feedback: feedback_8f043b062f9c4ce7ace4821cf043ff19
case: case_769252a510786f9091ef1adb
authority: authority_b7956645731f47d99b4379edf0a064ac
finding: finding_81aef970aa8f4856a1791fb568df7f67
eval target: evaltarget_359988cb167348e4a04eb25903ff1872
frozen hash: sha256:013bb12ca979b207d5c10177b1fb832ffb6b2cefbe783e0da23b1c5d5b469077
```

The first prepared Job exposed that an omitted caller-supplied
`schema_fingerprint` remained null. `prepare_semantic_job` now derives the
fingerprint from the allowlisted Wren semantic files in the registered base
snapshot. The CLI also provides a read-only `verify-job` command. The final
prompt-only Job was:

```text
job: job_ecc460cc20614938991b9c2c15698d14
status: PREPARED
schema fingerprint: sha256:4eaf1703d3ff3b73e135f2e9255f4b3babc468a2ac21a32731c05d579a25abbc
evidence manifest: sha256:65b9bec587524e819873be1576c35d6b5bac29b0276d1ab328dc43780ec10ff2
verify-job: ok
```

The generated target eval preserves expected value `721.8`, tolerance `0.001`,
required unit `CNY`, forbidden unit `$`, and required completed-status filter.
The evidence contains no raw trace payload, result preview, or result-row field.
The Job stayed `PREPARED`, created no Job result, and the Context Registry still
contained only the registered base candidate with zero revisions. Targeted SI2
tests remained `7/7`; the full suite remained `130/130`.

### SI2 external isolation receipt gate

The old `--external-isolation-confirmed` boolean was removed after local
capability testing showed that an operator acknowledgement cannot prove the
process boundary. SI2 now requires an `IsolationReceipt` that is:

- bound to the immutable Job execution contract, frozen target hash, evidence
  manifest hash, Wren schema fingerprint, and logical writable root
- bound to the active `DATA_AGENT_ISOLATION_ENVIRONMENT_ID`
- HMAC-SHA256 authenticated with a key that is never persisted or inherited by
  the Codex child
- valid for no more than 30 minutes
- explicit that all required filesystem, child-process, network, and credential
  probes passed

`verify-isolation-receipt` provides a read-only preflight. On accepted
execution, the controller stores the receipt immutably under the Job control
directory before entering `RUNNING`. Invalid signatures, expired receipts,
wrong environment IDs, failed probes, or changed Job/evidence/schema hashes
leave the Job `PREPARED` and never call the executor.

Local capability verification used `codex-cli 0.144.1`. The CLI supports
`codex sandbox`, `--sandbox-state-json`, `--sandbox-state-readable-root`, and
`--sandbox-state-disable-network`. However, a strict read-allowlist probe on the
current Windows host returned:

```text
Restricted read-only access requires the elevated Windows sandbox backend
```

Therefore this machine cannot honestly issue a passing receipt yet. A future
external CI/container/VM worker or elevated Windows backend must run the probes,
sign the receipt, and inject its environment ID. No real Docker-isolated SI2
candidate execution was attempted. Verification after this change: SI2
`10/10`, full suite `133/133`, and `git diff --check` passed.

### SI2 Docker / CI isolated worker

Implemented the preferred Docker/CI workaround for the Windows strict-read
backend limitation. Only the Codex editing process enters the container; the
outer controller still owns candidate creation, frozen evidence verification,
Wren validation, target/smoke/regression evals, and the `REVIEW_REQUIRED` gate.

```text
src/data_agent_improvement/docker_worker.py
infra/si2_codex_worker/Dockerfile
infra/si2_codex_worker/Dockerfile.proxy
infra/si2_codex_worker/worker-entrypoint.sh
infra/si2_codex_worker/squid.conf
infra/si2_codex_worker/docker-compose.yml
docs/si2_docker_worker.md
```

The worker resolves a tag to Docker's immutable image ID and binds the receipt
to that ID, the internal network, and the proxy endpoint hash. Runtime mounts
only the copied candidate read/write, minimized evidence read-only, and the
final-response schema read-only. It does not mount the repository, base
snapshot, Registry controls, database, Wren home, or host credentials.

The execution-surface decision is now explicit: SI2 uses the pinned
`codex exec` CLI inside the Docker/CI worker for the MVP. A future verified
Codex SDK adapter may replace only the invocation/streaming layer behind
`SemanticCandidateExecutor`. The Docker boundary, signed receipt, frozen target,
outer evals, review state, and publication controls do not change. The installed
Windows CLI is not allowed to bypass a missing Docker receipt.

The container uses a read-only root filesystem, UID 10001, dropped Linux
capabilities, `no-new-privileges`, PID/memory/CPU limits, an ephemeral tmpfs,
Codex `workspace-write`, `sandbox_workspace_write.network_access=false`,
`shell_environment_policy.inherit=none`, ignored user config/rules, and no
approval path. The HMAC/environment secrets never enter the container.

Provider access uses two networks: the Codex worker joins only the internal
`data-agent-si2-internal` network; the Squid proxy joins that network and a
provider-egress network. Its ACL permits CONNECT only to `api.openai.com`. The
no-model probe must prove OpenAI reachability through the proxy, rejection of
`example.com`, direct-internet denial, denial of a reachable network canary by
`codex sandbox`, candidate/evidence mount modes, and dummy API-key exclusion
before signing a receipt.

Offline verification completed:

```text
Docker/SI2 targeted tests: 18 passed
full unit suite: 141 passed
docker compose config: passed
CLI prepare-docker-isolation help: passed
git diff --check: passed
```

Docker Desktop is available with Linux containers and cgroup v2. Direct Docker
Hub access remained unavailable, but the following build fallback succeeded on
2026-07-17:

```text
base images: docker.1panel.live/library/node and /debian
Debian packages: mirrors.aliyun.com
npm: registry.npmmirror.com
worker image: sha256:63339471636cb03da0ff021a5ceb4c842b8f2171bad9c492419215c8a84cdc95
proxy image: sha256:f35b5ebec10bcc4edd08643e8577b48b7624d7818e2d99f1e43ec6d2d59d9782
Codex CLI: 0.144.1
```

The proxy initially exited because Squid's optional ICMP pinger is incompatible
with `cap_drop: ALL`; disabling the pinger preserved the capability boundary and
produced a stable proxy. Docker's default seccomp profile also blocked the user
namespace required by Codex's Linux `bwrap` sandbox. The current compatibility
setting is `seccomp=unconfined` around a non-root, capability-free, read-only,
mount-restricted container; the inner Codex sandbox then started successfully.
A narrow custom seccomp profile remains a hardening follow-up.

Real no-model probes passed candidate/evidence filesystem policy, reachable
canary network denial by `codex sandbox`, and dummy API-key exclusion from the
child environment. The provider probe still failed: after DNS cache reset Squid
established `TCP_TUNNEL/200` to the correct Cloudflare address, but TLS ended in
`SSL_ERROR_SYSCALL`. This host has no configured system or common local VPN
proxy. The receipt was correctly not issued, `codex exec` was not started, no
API key was sent, and the real Job remains `PREPARED`. A corporate/VPN/CI route
to `api.openai.com` is still required.

Real Codex execution still requires built worker/proxy images, a configured
Wren/eval environment, the `--execute` gate, and a valid Docker isolation
receipt. SI2 still cannot
approve or publish. SI3 engineering worktrees and SI4 release monitoring remain
unimplemented.

### SI2 development-only Host Session executor

Added an explicit local-development path on 2026-07-20 so prompt and executor
work can continue using the current host Codex CLI session while isolated
provider credentials remain unavailable:

```text
execute-semantic-job-dev
--execute
--acknowledge-host-session-development-only
```

This is not a receipt bypass. The development function verifies the frozen Job
and evidence before and after execution, but it creates no formal SI2
`ImprovementJobResult`, stores no isolation receipt, leaves the Job `PREPARED`,
and reports `development_only=true` plus `release_eligible=false`. The prompt
also labels every candidate disposable and development-only.

The development executor deliberately loads the current host Codex config and
authentication. A minimal host-session probe succeeded with the configured
mirror provider and `gpt-5.6-sol`, confirming that local iteration can proceed.
The same run also encountered an unrelated host MCP `403`, demonstrating why
personal config is not an isolation boundary.

Release, CI, and Docker packaging must never copy a developer's `auth.json` or
silently reuse a personal login. They require a dedicated API key or CI secret,
the externally isolated worker, passing probes, and a signed receipt. The formal
`execute-semantic-job` contract remains unchanged.

Verification:

```text
host-session development probe: passed with gpt-5.6-sol
SI2/CLI targeted tests: 14 passed
full unit suite: 144 passed
execute-semantic-job-dev help: passed
git diff --check: passed
```

The first real development-only Job execution completed on 2026-07-20 using
the current host session:

```text
job: job_ecc460cc20614938991b9c2c15698d14
revision: revision_0b0ac7bc002e4b8cad4d70af77d262dc
candidate: candidate_1ba12b26adb741f2a31f2015d5eabcb0
Codex CLI: 0.144.6
provider/model: mirror / gpt-5.6-sol
Codex execution: passed
Wren validate/build: passed
outer evaluation: SMOKE_FAILED
```

Codex aligned the confirmed SQL example question with the frozen target and
preserved the evidence-backed SQL:

```sql
SELECT SUM(total_amount) AS realized_revenue
FROM orders
WHERE status = 'completed'
```

It made no Model or Relationship change and reported no assumption or
unresolved question. All smoke and three frozen-target repetitions then failed
because the local StarRocks test server at `127.0.0.1:19030` was not running;
the generated SQL still contained the required completed-status filter. Treat
this as an infrastructure-blocked acceptance run, not proof that the semantic
candidate regressed or passed.

The fail-closed properties held after the real model call: the Improvement Job
remained `PREPARED`, `verify-job` still passed, the Job directory contained no
formal result or isolation receipt, and the development report returned
`formal_result_recorded=false`, `isolation_receipt_used=false`, and
`release_eligible=false`. The Context candidate initially remained
`SMOKE_FAILED`; it was not approved or published.

After Docker Desktop was opened interactively, `starrocks_mvp.ps1 -Action Init`
restored the fixed fixture (`customers=5`, `orders=8`) and Wren
validate/build/dry-run passed. The existing revision was then retried without
another Codex call:

```powershell
.\scripts\starrocks_mvp.ps1 -Action Init
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli retry-revision-evals `
  --registry-root data\tmp\si2_realized_revenue_prompt_only\context_registry `
  --revision revision_0b0ac7bc002e4b8cad4d70af77d262dc `
  --regression-suite data\tmp\si2_realized_revenue_prompt_only\improvement_registry\jobs\job_ecc460cc20614938991b9c2c15698d14\evidence\target_eval.jsonl `
  --regression-suite data\tmp\si2_realized_revenue_prompt_only\improvement_registry\jobs\job_ecc460cc20614938991b9c2c15698d14\evidence\target_eval.jsonl `
  --regression-suite data\tmp\si2_realized_revenue_prompt_only\improvement_registry\jobs\job_ecc460cc20614938991b9c2c15698d14\evidence\target_eval.jsonl `
  --wren-home data\wren\home `
  --wren-bin .venv-wren\Scripts\wren.exe
```

The first database-backed retry passed smoke `3/3` and produced the correct SQL
and numeric result in all three frozen-target runs, but DeepSeek summarized the
result as `$721.80`, `721.80`, and `$721.80`. The Wren candidate already stated
that `orders.total_amount` is denominated in CNY. The actual defect was the
online runtime interface: SQL generation and repair received `WrenContext`, but
`summarize_result` received only question, SQL, and rows.

The runtime now has a backward-compatible `summarize_result_with_context`
adapter method. Existing adapters fall back to their old summarizer; the
DeepSeek adapter receives bounded Wren semantic context and is instructed to
preserve explicit unit names and never replace an ISO currency code with a
symbol. The second retry passed smoke `3/3` and frozen target `3/3`:

```text
trace_b31d5e059c2449e2899cd892945ffeae: 721.80 CNY
trace_143309f2f53b46cd8db0b4b29ff04f73: 721.80 CNY
trace_0de8047490d24222be7b12048253d47d: 721.80 CNY
candidate/revision: REVIEW_REQUIRED / REVIEW_REQUIRED
review packet: generated
```

Development-only release eligibility is now persisted on Context candidates.
Both candidate and revision transitions fail closed before `APPROVED`, and
candidate publication also remains unreachable. Older development candidates
without the structured field are recognized through their `DEVELOPMENT_ONLY`
provenance. The real candidate loads as `release_eligible=false`; the
Improvement Job still remains `PREPARED` with no formal result or isolation
receipt. No approval or publication was performed.

Verification after the fix:

```text
focused Context/SI2/runtime tests: 53 passed
full unit suite: 146 passed
real StarRocks smoke: 3/3 passed
real frozen target repetitions: 3/3 passed
```

### Unified outer candidate evaluation contract

Added a deterministic outer evaluation contract on 2026-07-21 for SI2 and the
future SI3 candidate executors:

```text
PASS    / ACCEPTANCE_PASSED
FAIL    / ASSERTION_FAILED
BLOCKED / INFRASTRUCTURE_UNAVAILABLE
BLOCKED / EVAL_TARGET_INVALID
```

The classifier consumes the Context Builder's smoke and regression artifacts;
Codex does not decide whether its own candidate passed. A completed frozen
assertion mismatch is `FAIL`, while a database connection failure, timeout, or
evaluation process failure without a summary is `BLOCKED`. A missing or invalid
frozen regression suite is also `BLOCKED`, with the distinct
`EVAL_TARGET_INVALID` reason.

SI2 retains its existing persisted result and Job statuses for compatibility:

```text
PASS                          -> PASS / REVIEW_REQUIRED
FAIL                          -> FAIL / FAILED
BLOCKED + invalid EvalTarget  -> EVAL_TARGET_INVALID
BLOCKED + infrastructure      -> INCONCLUSIVE
```

The normalized `candidate_evaluation` is included in development reports and
formal `ImprovementJobResult.evaluation_summary`. Clarification remains a
separate `NEEDS_BUSINESS_REVIEW` gate and does not claim that evaluation ran.
Context Builder may still use its internal `SMOKE_FAILED` state; the outer SI
contract provides the cross-executor meaning. This change does not add
automatic SI2-to-SI3 routing or source-code diagnosis.

Verification:

```text
focused evaluation/SI2 tests: 21 passed
full unit suite: 155 passed
git diff --check: passed
```

### Real outer evaluation contract integration test

Replayed the realized-revenue candidate through the normalized outer evaluator
on 2026-07-21. All Data Subagent traces, eval runs, reports, and deliberately
invalid suites were isolated under:

```text
data/tmp/si2_outer_eval_integration/
```

The healthy StarRocks run used the existing frozen EvalTarget and development
candidate. It returned the evidence-backed SQL and answer, passed every frozen
assertion, and normalized to `PASS / ACCEPTANCE_PASSED`:

```text
run: 20260721-144551-si2_outer_real_pass
trace: trace_f19e8be7c5384527b37426ccd0556340
SQL: SELECT SUM(total_amount) AS realized_revenue
     FROM orders WHERE status = 'completed'
answer: The total realized revenue is 721.80 CNY.
result: 1/1 passed
```

The same frozen case was then run while only the `data-agent-starrocks`
container was stopped. SQL generation still produced the correct completed
filter, but Wren exhausted two repairs with connection error `10061`. The raw
eval record said `fail`; the outer evaluator correctly distinguished the
environmental cause and returned `BLOCKED / INFRASTRUCTURE_UNAVAILABLE`:

```text
run: 20260721-144721-si2_outer_real_blocked
trace: trace_d7336c0bf46549a3b926e354aefb5e43
result: 0/1 passed
outer reason: StarRocks connection unavailable
```

The command restored the container in a `finally` block, reinitialized the
fixed fixture, reran Wren validate/build/dry-run, and ended with Docker status
`running healthy`, `customers=5`, and `orders=8`.

A real database-backed negative acceptance case retained the correct SQL and
numeric value but deliberately required `USD` and forbade `CNY`. The returned
answer was `721.80 CNY`, so the outer evaluator returned
`FAIL / ASSERTION_FAILED`, not `BLOCKED`:

```text
run: 20260721-144915-si2_outer_real_fail
trace: trace_28f4935978fa410db5a9efb82e5d1096
failure: expected USD; CNY was forbidden
```

Finally, the real Context Builder `run_revision_evals` orchestration received a
nonexistent frozen regression path. Generated smoke construction succeeded,
the missing suite was recorded as `Regression suite not found.`, and the outer
result was `BLOCKED / EVAL_TARGET_INVALID`.

These tests did not rerun Codex or modify the candidate. Improvement Job
`job_ecc460cc20614938991b9c2c15698d14` remains `PREPARED`; candidate
`candidate_1ba12b26adb741f2a31f2015d5eabcb0` remains `REVIEW_REQUIRED`; the Job
directory still has no formal result or isolation receipt. No approval,
publication, merge, or deployment was performed.

### Controlled self-improvement SI3 development controller

Implemented the first development-only SI3 source-code candidate controller on
2026-07-21:

```text
FROZEN EvalTarget + verified business authority
-> fixed Git base commit and tree fingerprint
-> linked Git worktree on local branch si3/job_<id>
-> bounded Codex CLI source edit
-> outer evaluation
-> local patch and PR candidate packet
-> human engineering review
```

The implementation is deliberately narrower than a production source release
system. It adds `SOURCE_CODE` Jobs, allowed/forbidden path enforcement, Git
history checks, a structured Codex final response, sanitized command execution,
and normalized outer evaluation. A passing candidate produces
`artifacts/pr_candidate.patch` and `artifacts/pr_candidate.json`, but remains
`development_only=true` and `release_eligible=false`. The Improvement Job stays
`PREPARED`; no formal isolation receipt or JobResult is created. The controller
does not commit, push, open a remote PR, approve, merge, deploy, diagnose root
cause, or automatically route SI2 failures into SI3.

The source evaluation commands are now part of the frozen Job contract rather
than execution-time CLI input. `prepare-source-job` writes
`control/source_evaluation_plan.json`, stores its canonical SHA-256 in
`job.data_identity.evaluation_plan_sha256`, and derives `required_suites` from
the plan. `execute-source-job-dev` accepts no replacement suite commands; it
loads the frozen plan and fails closed if the file, hash, schema, or suite names
change. A regression test verifies that even replacing a command with another
successful command invalidates the Job before Codex or outer evaluation can be
trusted.

Current development command surface:

```text
prepare-source-job
  --eval-target <frozen target>
  --repository-root .
  --base-ref HEAD
  --allowed-path "src/**"
  --suite-command-json '<name/args/timeout/non-secret-environment JSON>'

execute-source-job-dev
  --job <job id>
  --execute
  --acknowledge-host-session-development-only
```

Development execution may reuse the current host Codex CLI session. This is
explicitly not the release path. Docker/CI packaging must use a separately
configured API key or CI secret, stronger read/write mounts, a signed isolation
receipt, and the formal result state machine before any source candidate can be
release eligible.

Verification:

```text
focused SI3/evaluator/CLI tests: 18 passed
full unit suite: 165 passed
prepare-source-job and execute-source-job-dev help smoke: passed
git diff --check: passed
```

At that controller-only milestone, no real source-changing Codex candidate had
yet been executed. The following integration test records the first real run.

### Real minimal SI3 source candidate integration test

Ran the first real source-changing SI3 development case on 2026-07-21 using the
current host Codex CLI session. The isolated fixture is under:

```text
data/tmp/si3_minimal_real/
```

The committed baseline repository intentionally implemented realized revenue
by summing every order. Its frozen business truth required only `completed`
orders and the CNY unit. Before Codex execution, both deterministic tests failed:

```text
no completed orders: expected 0, observed 13.00
mixed statuses: expected 200.75, observed 1229.75
baseline result: 0/2 passed
```

The real control chain created a correction-bearing FeedbackRecord, scoped
authority confirmation, singleton semantic Finding, reviewed and frozen
EvalTarget, fixed Git base commit, frozen evaluation plan, and SOURCE_CODE Job:

```text
trace: trace_1be9bda3d13347368b02f7773d09fb18
feedback: feedback_db791199478c4cb097ab245ba95db6d4
finding: finding_5cad5348e00645ef8b104f1d30f3f185
eval target: evaltarget_2f734bb7c9f3480a8c54ceb333e6f486
job: job_08dfc05e631f4dc09c65cef7f8c221fd
base commit: a338e1bb4373429c205308b67c22396671c1857c
evaluation plan: sha256:acfe938c7e471856235e7fd65eb687e34022ae770df60fb9e4e0078b9481c992
```

Codex ran for about 120 seconds in the linked worktree. It changed only
`src/revenue.py`, preserving the function signature and adding the missing
`order.get("status") == "completed"` filter. It did not modify tests or Git
history. The controller reran the frozen outer command with a sanitized
environment and normalized the result to:

```text
candidate: sourcecandidate_7ae42557d7304ddca843e835574bea8c
changed paths: src/revenue.py
outer evaluation: PASS / ACCEPTANCE_PASSED
candidate result: 2/2 passed
patch: artifacts/pr_candidate.patch
patch SHA-256: sha256:5aa572493c9fa328f750c772d1ee0688b45123dae33d8e60626385cf2e30eb49
```

Independent post-run verification confirmed that the worktree still passes
`2/2`, the frozen Job integrity check returns `ok=true`, the worktree HEAD still
equals the base commit, and the original repository remains clean and still
fails `2/2`. This proves the pass came from the isolated source edit rather than
test weakening or baseline mutation.

The candidate remains development-only:

```text
Job status: PREPARED
formal result: absent
isolation receipt: absent
release_eligible: false
commit/push/remote PR/approval/merge/deploy: not performed
```

Windows pitfall: files created through the workspace sandbox may be owned by a
different local security principal from the process running Git, causing Git's
`dubious ownership` check. The demo used a process-local `safe.directory`
environment override scoped to the exact fixture repository. It did not change
the user's global Git configuration. A Docker/CI worker should avoid this host
ownership mismatch by creating and operating the repository inside one worker
identity.

### SI3 RoutingDecision preflight gate

Added an explicit repair-layer gate on 2026-07-22 after the real minimal SI3
case showed that a source edit can pass frozen tests even when the underlying
rule would normally belong in Wren Context.

Outer evaluation and routing now have separate contracts:

```text
RoutingDecision: is SOURCE_CODE the reviewed and evidenced repair layer?
outer evaluation: does the resulting candidate pass the frozen acceptance contract?
```

`RoutingDecision` is an immutable Improvement Store record bound to one Finding,
one frozen EvalTarget, one target type, a reviewer and rationale, and typed
evidence. Every SOURCE_CODE route requires at least one of:

```text
SOURCE_REPRODUCTION
POST_CONTEXT_FAILURE
STRUCTURAL_SOURCE_DEFECT
```

If the Finding is semantic or ambiguous (`BUSINESS_SEMANTIC_GAP`, `CONTEXT_GAP`,
`SQL_GENERATION_DEFECT`, `SUMMARIZATION_GAP`, or `UNKNOWN`), it must additionally
provide `CONTEXT_RULE_VERIFIED` or `GENERATED_SQL_VERIFIED`. An
explicitly source-owned behavior may instead provide
`SOURCE_CONTRACT_OWNERSHIP_VERIFIED`, but it still also requires source failure
evidence. An `EVAL_TARGET_QUALITY` Finding cannot route to SI3 and must revise
the target.

`prepare-source-job` now requires `--routing-decision`. It packages
`routing_decision.json` into the read-only manifested evidence bundle, stores
its canonical SHA-256 in the Job, and records the decision ID on the Job. Job
integrity fails closed if the record is missing, changed, points to a different
Finding/EvalTarget, selects WREN_CONTEXT, or no longer satisfies the source
evidence rules. The CLI requires `--project-routing-confirmed` when creating a
decision because the local process records but does not authenticate the
reviewer.

Current commands:

```text
create-routing-decision
list-routing-decisions
show-routing-decision
prepare-source-job --routing-decision <routing_id>
```

The earlier real minimal Job predates this gate. Its patch remains valid as
historical development evidence, but the old Job intentionally fails the new
integrity contract because it has no RoutingDecision. A fresh execution must
create a reviewed decision rather than silently grandfathering the old route.

Verification:

```text
focused routing/SI3/evaluator/CLI tests: 23 passed
full unit suite: 170 passed
RoutingDecision and prepare-source-job CLI help smoke: passed
git diff --check: passed
```

### Two-stage RoutingProposal and human confirmation gate

Implemented the proposal/review split on 2026-07-22 so Codex diagnostic output
cannot become executable SI2/SI3 authority directly:

```text
Codex or caller -> immutable RoutingProposal
deterministic controller -> READY_FOR_REVIEW or DIAGNOSIS_REQUIRED
explicit human confirmation -> hash-bound RoutingDecision
RoutingDecision -> SI2 WREN_CONTEXT Job or SI3 SOURCE_CODE Job
```

`RoutingProposal` records one Finding and frozen EvalTarget, the proposed target
type, typed evidence, proposer, rationale, validation policy, validation errors,
and timestamp. Evidence-insufficient proposals remain useful audit records with
`DIAGNOSIS_REQUIRED`, but confirmation fails closed. Confirmation re-runs the
deterministic routing policy and creates a separate `RoutingDecision` containing
the confirmer and confirmation rationale plus the canonical proposal SHA-256.
Job integrity rechecks the proposal hash and decision/proposal identity, target,
type, and evidence. A manually modified confirmed proposal therefore invalidates
the route.

New CLI surface:

```text
create-routing-proposal
list-routing-proposals
show-routing-proposal
confirm-routing-proposal --project-routing-confirmed
```

The existing `create-routing-decision` command remains an explicitly documented
trusted-local-admin compatibility shortcut. It should not be used by normal
automated workflows. The local CLI records actor strings but does not
authenticate them; a deployed API/CI controller must authenticate and authorize
the human confirmer.

SI2 Job preparation now also requires `routing_decision_id`, packages
`routing_decision.json` into its manifested evidence, records the canonical
decision hash, and fails closed on a missing, changed, wrong-target, or
proposal-invalid route. This closes the previous mismatch where the CLI passed
`--routing-decision` but the Python SI2 controller did not accept it. The common
evidence-manifest check remains target-neutral; SI2 and SI3 apply their own
WREN_CONTEXT and SOURCE_CODE routing rules respectively.

The controller currently validates evidence structure and allowed type
combinations, not the truth of every evidence summary. For example, the
presence of `GENERATED_SQL_VERIFIED` is checked, but Wren is not yet rerun by a
deterministic evidence probe. The next hardening step is to add signed or
reproducible probes for Context fingerprints, generated SQL, source
reproduction, and post-Context failure. Source-contract ownership must remain
an engineering-reviewer assertion rather than a Codex self-issued fact.

Verification:

```text
focused SI2/SI3/routing/CLI tests: 33 passed
full unit suite: 175 passed
RoutingProposal create/confirm CLI help smoke: passed
git diff --check: passed
```

### Main Agent orchestration architecture note

Added `docs/data_agent_main_orchestrator_architecture.md` to clarify the missing
top-level orchestration layer. The current Data Subagent and Context Builder are
separate runnable capabilities; a future Main Data Agent should identify the
data source, check a Context Registry and Wren readiness state, then route to
initial onboarding, online questioning, or semantic improvement. The note also
defines a proposed Context lifecycle and keeps Wren mandatory in the query path.

### Conversational Context revision goal

Agreed on 2026-07-14: Context review and enrichment should be primarily driven
by user natural language plus Codex, not by requiring users to manually edit
Wren YAML.

```text
candidate Context
-> Builder presents evidence, assumptions, questions, and tests
-> user states business truth or requests changes in natural language
-> Codex follows Wren generate-mdl skill and revises a new candidate version
-> Builder independently validates, runs smoke/regression, and shows semantic diff
-> user approves, requests another revision, or rejects
-> explicit publish updates the Context Registry
```

The scoped business confirmer owns business truth and the human owns approval.
Codex owns most investigation and implementation. Builder owns immutable versions, safety,
provenance, deterministic acceptance, and publish control. Codex must not
self-approve or self-publish.

Current `enrich-with-codex --instructions` is only an execution precursor. The
R0 filesystem contract is now implemented in
`src/data_subagent_context_builder/revision_store.py` with tests in
`tests/test_context_builder_revision_store.py`.

R0 provides:

- immutable candidate identity and new candidate versions per revision
- separate candidate and revision state machines with legal transition checks
- atomic JSON records and expected base-version/status checks
- structured natural-language change requests
- user-declared business-truth provenance
- persistent clarification and approval HITL tasks, questions, and answers
- a gate that prevents resume while required clarification remains unanswered
- a gate that prevents revision approval without completed human approval
- semantic-diff and review-packet storage contracts

This is persistent and resumable rather than a blocking `codex exec`
conversation. Codex must not write Registry state directly.

R1 is now implemented in `src/data_subagent_context_builder/revision_engine.py`
with tests in `tests/test_context_builder_revision_engine.py`:

- `register-candidate` creates a bootstrap Registry record for an existing Wren project
- `revise-candidate` creates a new candidate ID and copies the base Wren project
- generated `.wren`, `target`, Python cache files are excluded from the copy
- the original candidate project remains unchanged
- Codex runs with the copied candidate project as its writable working directory
- the revision prompt makes Wren `generate-mdl` skill authoritative
- Codex cannot approve, publish, or write Registry lifecycle records
- outer Wren validate/build/optional dry-run and bounded repair are reused
- prompts, last messages, validation JSON, instruction, and result are revision artifacts
- successful execution enters `REVIEW_REQUIRED`; failed acceptance enters
  `VALIDATION_FAILED` while preserving the candidate for inspection

Real prompt-only CLI verification against the local StarRocks candidate:

```text
base candidate: candidate_94c1e96afc06442dbadce2d068798770
revision: revision_732dc5a652a04c52b1da8e1d114aaa6a
new candidate: candidate_4ed134e3f5164faf8d4b0103e49b57cb
instruction: total_amount is CNY; only completed orders are realized revenue
result: REVISION_REQUESTED / DRAFT, Codex not executed
base/candidate orders metadata SHA256: identical
workspace: data/tmp/context_revision_r1_smoke/registry
```

At the R1 milestone, clarification classification, semantic diff, evals, and
fresh StarRocks investigation were intentionally deferred; later sections
record their implemented state.

R2 is now implemented:

- Codex must write `onboarding/revision_outcome.json` with status
  `completed` or `clarification_required`
- the outer Builder validates the outcome schema during every Codex/repair round
- stale outcomes copied from a previous candidate are removed before execution
- clarification outcomes create persistent `HumanTaskType.CLARIFICATION` tasks
- semantic diff compares Models, fields, Relationships, rules, SQL Examples,
  assumptions, unresolved questions, and eval coverage
- `revise-candidate --execute` runs generated smoke eval by default
- `--regression-suite` may be repeated to run previously passing business suites
- eval execution reuses `python -m data_subagent.cli eval` against the candidate
  Wren project instead of duplicating the online Data Subagent construction
- eval failure moves both revision and candidate to `SMOKE_FAILED`
- `--no-evals` is the explicit debug/isolated-environment escape hatch

The generated smoke cases are conservative row-count/optional relationship
checks. They establish basic usability, not that a requested currency, metric,
or accounting rule is correct. Business-semantic suites such as
`data/evals/cases/starrocks_semantic_improvement_candidates.jsonl` must be
passed through `--regression-suite`. A real eval requires the existing local
DeepSeek key and provider connectivity; no key is copied into revision artifacts.

At the R2 milestone, follow-up review and publication behavior remained
deferred; the R3 section records their implemented state.

R3 is now implemented:

- every accepted revision writes `review_packet.json` with semantic diff,
  provenance, outer validation, smoke result, and regression result
- `answer-review-question` records a natural-language answer as
  `user_declared_business_truth`
- `resume-revision` runs a new Codex execution over the same candidate and
  revision after all required clarification questions are answered
- resume prompts and repair rounds retain the persisted human answers
- resume artifacts are isolated under `revisions/<id>/resumes/resume_<n>/`
- `review-candidate` returns candidate state, revision state, review packet,
  semantic diff, and human tasks
- `approve-candidate` creates and answers a separate approval task with
  `user_review_decision` provenance
- `reject-candidate` records the explicit rejection reason
- calling `revise-candidate` on a candidate under review marks the previous
  revision `CHANGES_REQUESTED` and creates another immutable candidate version
- `publish-candidate` requires `APPROVED` and atomically updates
  `contexts/<context_id>/published.json`
- publication history is append-only by event file; `rollback-context` writes a
  new rollback event and points to a previously published candidate
- approval and publish remain separate operations; Codex performs neither

The published pointer is now usable by a future Main Agent, but the current
online Data Subagent does not yet route through it.

### Controlled StarRocks revision re-investigation

Added `src/data_subagent_context_builder/revision_starrocks.py` and integrated
it with `revise-candidate` and `resume-revision`.

- access is opt-in for every execution and is never inherited
- host, database, and user must be supplied together
- Catalog/Database allowlists, maximum rows, and timeout are explicit
- password values are never written to prompts, access artifacts, or evidence
- fresh data may establish observable facts but not business policy
- missing evidence means access was authorized but not needed
- existing evidence must include an executed controlled query
- evidence containing returned result rows fails outer acceptance
- valid evidence is archived with the revision or resume execution

Real prompt-only verification against the local StarRocks candidate:

```text
revision: revision_fe5e7d48897641d380dbed9a1113e8f4
candidate: candidate_d16cd66a1efb4bc393f2d92ebb92a1b1
scope: default_catalog.data_agent_mvp
max rows: 20
query timeout: 5 seconds
Codex/database execution: not run
password_value_persisted: false
```

Security boundary: the StarRocks account must itself be read-only and scoped to
the allowed database. Builder SQL allowlists are defense in depth and cannot
replace database grants.

Detailed design:

```text
docs/context_builder_conversational_revision_plan.md
```

### StarRocks 3.5 local MVP fixture

Added a reproducible local StarRocks shared-nothing all-in-one fixture under
`infra/starrocks/`, with lifecycle automation in `scripts/starrocks_mvp.ps1`
and a small Wren project at `data/wren/starrocks_mvp_wren_project`. The fixture
uses Wren's `doris` datasource against StarRocks's MySQL-compatible port `9030`,
loads deterministic customer/order data, and is intended only for local MVP
validation. Setup and verification commands are documented in
`docs/starrocks_mvp_setup.md`.

First real verification on 2026-07-13:

```text
container: data-agent-starrocks (healthy)
image: starrocks/allin1-ubuntu:3.5.18
host ports: 18030 / 18040 / 19030
fixture rows: 5 customers, 8 orders
Wren datasource: doris
Wren context validate: 2 models, 0 views, 1 relationship
Wren context build: OK
Wren dry-run: OK
Wren real grouped query: OK
Data Subagent: success, "There are 8 orders."
trace_id: trace_450e96f7bdeb4373b91fc8a6649a6fe0
smoke eval: 3/3 passed
eval run_id: 20260713-175049-starrocks_mvp_smoke
```

StarRocks smoke eval traces:

```text
order count: trace_3d4980e2fc5449c492483598c7c26ee6
orders by status: trace_7068983e71b9401995988147d17bda65
realized revenue: trace_295ceda0754b4129b09f8259835f8d82
```

StarRocks/Wren pitfalls found during setup:

- Wren's `doris` connector uses the MySQL protocol driver. Install
  `wrenai[mysql]==0.12.0`; otherwise profile validation/dry-run fails with
  `No module named 'MySQLdb'`.
- Local ports `8030`, `8040`, and `9030` may already belong to another
  StarRocks container. This fixture defaults to host ports `18030`, `18040`,
  and `19030` while retaining the standard container ports.
- Docker Hub was unreachable from Docker Desktop during the first run, but
  `starrocks/allin1-ubuntu:3.5.18` was already cached locally. The setup doc
  records the mirror-tag fallback.
- The realized-revenue eval matched the Gold SQL result (`1131.70`), but the
  result summarizer displayed `$1,131.70` even though the Wren column description
  says CNY. Eval cases now support `expected_answer_contains` and
  `expected_answer_not_contains`, and the unresolved case is preserved in
  `data/evals/cases/starrocks_semantic_improvement_candidates.jsonl`. Keep this
  suite failing until a future Semantic Improvement Loop fixes the behavior and
  passes both the candidate suite and normal regressions.

Explicit semantic-improvement baseline on 2026-07-14:

```text
run_id: 20260714-093727-starrocks_semantic_improvement_baseline
trace_id: trace_c29d876e14db44fcb5f9efdeb34ce2ee
result: 0/1 passed
SQL/result equivalence: passed
answer: "The total realized revenue is 1131.70."
failure: answer missing expected fragment(s): ['CNY']
```

The original trace invented `$`; the new baseline omitted the unit. Treat both
as the same root issue: the summarization stage does not reliably carry currency
semantics from Wren Context into the final answer.

### Context Builder status snapshot

The upstream Wren Context Builder is also runnable. Its first-line path is now:

```text
database / existing context
-> deterministic schema and runtime preparation
-> Codex follows Wren's installed generate-mdl skill
-> Codex creates or edits Wren MDL
-> outer Wren validate / build / dry-run
-> bounded Codex repair rounds on failure
-> onboarding report and smoke-eval artifacts
```

Current implementation:

- Package: `src/data_subagent_context_builder/`
- Commands: `inspect`, `generate-from-db`, `generate-schema-draft`, `validate`,
  `enrich-with-codex`, `make-smoke-eval`, `starrocks-query`,
  `generate-from-starrocks`, `register-candidate`, `revise-candidate`,
  `retry-revision-evals`, `review-candidate`, `answer-review-question`, `resume-revision`,
  `approve-candidate`, `reject-candidate`, `publish-candidate`, and
  `rollback-context`.
- `generate-from-db` defaults to the skill-first Codex + Wren path. It prepares
  facts and runtime state but does not deterministically author MDL YAML.
- `generate-schema-draft` is the explicit schema-level fallback/debug path.
- `generate-from-db --execute` runs Codex, then independently runs Wren
  validate/build/dry-run. Failed checks are returned to Codex for at most
  `--max-repair-rounds` repair rounds.
- Every round preserves its prompt, Codex last message, and structured Wren
  validation output under the target project's `onboarding/` directory.
- A real BIRD Mini-Dev `debit_card_specializing` run completed with 5 models,
  4 relationships, successful Wren validate/build/dry-run, and no repair round.
- Latest full verification: `90` unit tests passed.

Current architectural classification: this is a bounded agentic workflow tool,
not yet a standalone subagent. The workflow stages and stopping conditions are
chosen by deterministic code. A future subagent would need a strategy layer
that selects onboarding paths, classifies semantic gaps and failures, asks for
business clarification, schedules enrichment, and decides when quality is
sufficient.

### First real natural-language revision acceptance

Completed on 2026-07-15 against a clean StarRocks Context baseline:

```text
base candidate: candidate_8903bce7af8c4b99bc51bec06514de6a
revision: revision_e4af8208c51040f38b6a6877a58607ff
candidate: candidate_1e1f8ebee1484aad8530cee1d773dfc0
instruction: total_amount is CNY; only completed orders are realized revenue
final state: REVIEW_REQUIRED / REVIEW_REQUIRED
publication: not performed
```

The real Codex execution followed the installed Wren `generate-mdl` skill and
changed only the isolated candidate. It updated `orders.status` and
`orders.total_amount` descriptions, changed the general business rule, added a
completed-only realized-revenue SQL example, and wrote a valid structured
revision outcome. Wren validate/build/dry-run passed with zero Codex repair
rounds. The original clean candidate remains unchanged.

Final acceptance results:

```text
generated schema/relationship smoke: 3/3 passed
existing StarRocks regression: 3/3 passed
completed-only CNY semantic regression: 1/1 passed
semantic result: 721.80 CNY
semantic trace: trace_260065c826c54db4ac635798959fd9e2
relationship trace: trace_cd5475b7fd354b998ba38a720e70a0af
unit tests: 81 passed at the original HITL acceptance milestone; latest full suite is 90 passed
```

`semantic_diff.json` records the two field-description changes, rule change,
new SQL example, assumptions, and test coverage. `review_packet.json` records
the user-declared business truth, independent validation, eval results, and no
unresolved questions. The candidate then completed a real HITL approval on
2026-07-15 after the review summary and validation results were presented to
the user:

```text
candidate/revision state: APPROVED / APPROVED
approval task: task_7442feb5d367426b8cff4534f8e6b996
approval answer: answer_1775ab8bc0ee410dbaa8aab1383247e5
approval provenance: user_review_decision
publication: performed after separate explicit user confirmation
```

This verifies the human approval gate rather than only reaching
`REVIEW_REQUIRED`. Codex did not self-approve, and approval did not implicitly
publish the candidate. The user then separately confirmed publication:

```text
publication: publication_35185565607f4d0f9c4f4d5b268a11f6
context: data_agent_mvp_revision_acceptance
published candidate/version: candidate_1e1f8ebee1484aad8530cee1d773dfc0 / 2
previous candidate: none
candidate state: PUBLISHED
published pointer: contexts/data_agent_mvp_revision_acceptance/published.json
```

The pointer and append-only publication-history event contain the same
publication ID and candidate. This completes the first real natural-language
revision, automated acceptance, HITL approval, and explicit publish lifecycle.

Two generated relationship-smoke pitfalls were found during acceptance. A
question that requests a fixed number of rows can cause the LLM to emit
`LIMIT`, while Wren CLI also applies its own query limit. A detail query can
also produce `left.*, right.*`, which Wren CLI 0.12 cannot serialize to JSON
when output column names repeat. Relationship smoke now asks for a relationship
row count and requires `count` plus both model names. This still exercises the
relationship while producing one uniquely named result column. Business truth
remains covered by explicit regression suites rather than generated smoke.

### Context Builder StarRocks controlled-query foundation

Added on 2026-07-14:

```text
src/data_subagent_context_builder/starrocks_query.py
tests/test_context_builder_starrocks_query.py
```

`starrocks-query` is the safe database primitive used by the implemented
`generate-from-starrocks` Codex workflow. It intentionally does not implement a
fixed StarRocks schema crawler.

Implemented controls:

- Connects through StarRocks's MySQL protocol using the installed
  `mysqlclient` / `MySQLdb` driver.
- Allows only scoped `SHOW`, `DESCRIBE`, `SELECT`, `WITH`, and `EXPLAIN` forms.
- Rejects mutation, multiple statements, unsafe `SHOW` commands, blocked
  functions, and cross-catalog/database references.
- Enforces Catalog/Database allowlists, query timeout, and maximum returned
  rows. `SHOW CATALOGS` and `SHOW DATABASES` results are filtered to the
  allowlist.
- Reads passwords from an environment variable only. The explicit
  `--allow-empty-password` option exists only for the isolated local fixture.
- Writes JSONL evidence for executed, rejected, and failed queries. Evidence
  omits returned values by default and records columns, counts, truncation,
  duration, and a result hash.
- Disables arbitrary `information_schema` queries by default; Codex can use the
  allowlisted `SHOW` / `DESCRIBE` surface for the first discovery pass.

Real verification against the existing local StarRocks 3.5 fixture:

```text
endpoint: 127.0.0.1:19030
catalog allowlist: default_catalog
database allowlist: data_agent_mvp
SHOW CATALOGS: OK, filtered to default_catalog
SHOW DATABASES: OK, filtered to data_agent_mvp
SHOW TABLES: OK, customers and orders
DESCRIBE orders: OK, 5 columns
limited SELECT sample: OK, 3 rows
DELETE attempt: rejected before database execution
evidence: 6 JSONL records, 0 records containing rows, no password field
```

WrenAI CLI `0.12.0` still has no datasource named `starrocks`. The existing
fixture has already verified Wren's `doris` datasource against StarRocks, so
future onboarding should use that proven compatibility path rather than assume
an unverified native StarRocks profile.

`generate-from-starrocks` now initializes an empty Wren project, imports a Wren
`doris` profile with an environment-variable password reference, binds the
profile to the project, and gives Codex only the controlled query command. Codex
produces `discovery_snapshot.json`, `schema_manifest.json`, Wren Models,
Relationships, rules, and examples. The outer Builder validates Wren
validate/build/dry-run plus the existence and JSON validity of discovery,
manifest, and executed query evidence before accepting a round.

### Real StarRocks Context Builder candidate onboarding

Completed a real skill-first onboarding pass on 2026-07-14 against the local
allowlisted StarRocks fixture through the Builder-owned `starrocks-query`
command only.

Workspace:

```text
project: data/tmp/starrocks_context_builder_real/wren_project
wren home: data/tmp/starrocks_context_builder_real/wren_home
evidence: onboarding/query_evidence.jsonl
snapshot: onboarding/discovery_snapshot.json
manifest: onboarding/schema_manifest.json
```

Discovery result:

```text
scope: default_catalog.data_agent_mvp
tables: customers, orders
evidence records: 24 executed read-only queries
rows at snapshot: 5 customers, 8 orders
physical keys: StarRocks DUPLICATE KEY, not enforced unique constraints
secondary indexes: none reported by SHOW INDEX
partitions: one unpartitioned physical partition per table
type normalization: wren utils parse-type --dialect mysql
```

The current snapshot supports logical Wren keys for `customers.customer_id`
and `orders.order_id`: each was non-null and unique across the inspected rows.
This is explicitly documented as a snapshot assumption because StarRocks DDL
does not enforce uniqueness for these `DUPLICATE KEY` tables.

One relationship was accepted for the reviewable candidate:

```text
orders.customer_id -> customers.customer_id
join type: MANY_TO_ONE
coverage: 8/8 order rows matched
orphans: 0
customer identifiers with multiple orders: 3 of 5
maximum observed orders per customer identifier: 2
database foreign key: none declared
```

Generated candidate assets:

```text
models/customers/metadata.yml
models/orders/metadata.yml
relationships.yml
knowledge/rules/general.md
knowledge/sql/order_count.md
knowledge/sql/orders_by_status.md
knowledge/sql/customer_order_counts.md
```

The Wren project internal namespace was set to the skill-recommended defaults
`catalog: wren` and `schema: public`; physical StarRocks coordinates remain in
each model's `table_reference`. No cubes, calculated metrics, currency labels,
status-based revenue rules, or inferred time semantics were added.

Verification:

```text
wren context validate: Valid - 2 models, 0 views, 1 relationships.
wren context build: Built target/mdl.json
wren dry-run order count: OK
wren dry-run all 3 generated SQL examples: OK
outer artifact validation: 24 executed evidence records, valid snapshot and manifest
```

Pitfall: Codex ran optional `wren memory index`, which produced no output and
timed out on Windows. Although Codex finished the candidate and wrote its final
message, the old `capture_output` implementation continued waiting on inherited
stdout/stderr handles until the outer 15-minute timeout. The prompt now forbids
Wren memory index/fetch/recall and edits outside the target Wren project.
`CodexCliRunner` now captures output through temporary files, returns structured
timeout code `124`, and terminates only its own process tree on timeout. Windows
fake-process tests cover normal output collection and timeout cleanup.

The first real run therefore required a manual invocation of the same outer
acceptance commands after the transport timeout. All Wren and artifact checks
passed. The repaired runner and fully automatic StarRocks outer acceptance path
are covered by unit tests; repeat the real fixture run when changing process or
prompt behavior.

The candidate remains non-production and requires scoped business confirmation
for key enforcement/deduplication, `total_amount` unit and accounting semantics,
`order_date` / `signup_date` event meaning, status and region taxonomies, and
whether customer references are guaranteed for late-arriving data.

### TPC-H StarRocks Context Builder candidate onboarding

Completed a full skill-first onboarding pass on 2026-07-14 for all eight TPC-H
tables in the local allowlisted `default_catalog.tpch_sf001` database. Database
discovery and relationship validation used only the Builder-owned
`starrocks-query` command.

Workspace:

```text
project: data/wren/tpch_starrocks_wren_project
evidence: onboarding/starrocks_query_evidence.jsonl
snapshot: onboarding/discovery_snapshot.json
manifest: onboarding/schema_manifest.json
report: onboarding_report.md
```

Discovery result:

```text
controlled queries: 69 executed, 0 truncated
tables: customer, lineitem, nation, orders, part, partsupp, region, supplier
columns: 61
row counts: 5 / 25 / 100 / 1,500 / 2,000 / 8,000 / 15,000 / 60,175
physical design: StarRocks DUPLICATE KEY, one unpartitioned partition each
distribution: one HASH bucket each
secondary indexes: none reported by SHOW INDEX
type normalization: wren utils parse-type --dialect mysql
```

Six snapshot-unique single-column logical keys were emitted as Wren primary
keys. The `partsupp (ps_partkey, ps_suppkey)` and
`lineitem (l_orderkey, l_linenumber)` composite keys were non-null and unique
but were left as documented logical keys rather than misrepresented as
single-column Wren primary keys. StarRocks `DUPLICATE KEY` is a storage/sort
model and does not enforce relational uniqueness.

Eight `MANY_TO_ONE` relationships were accepted after complete join coverage
and zero-orphan checks: nation-region, supplier-nation, customer-nation,
orders-customer, partsupp-part, partsupp-supplier, lineitem-orders, and the
composite lineitem-partsupp relationship. Direct lineitem-part and
lineitem-supplier candidates also had full coverage but were rejected as
redundant paths through partsupp.

Generated candidate assets:

```text
models/*/metadata.yml: 8 models
relationships.yml: 8 relationships
knowledge/rules/general.md: conservative semantic guardrails
knowledge/sql/*.md: 4 schema-level examples
target/mdl.json: compiled candidate
```

Verification:

```text
wren context validate: Valid - 8 models, 0 views, 8 relationships.
wren context build: Built target/mdl.json
wren dry-run order count: OK
wren dry-run all 4 generated SQL examples: OK
wren memory index: incomplete; model initialization failed, then timed out
```

No cubes, calculated business metrics, currencies, revenue formulas, default
time fields, or company-specific policies were inferred. Scoped business review
remains required for key enforcement, units/currencies, discount/tax representation,
status/code meanings, date selection, late-arriving data, composite-key
representation, and whether redundant direct lineitem joins should be exposed.

Memory-index pitfall re-confirmed: the first `wren memory index` attempt failed
inside Hugging Face embedding-model initialization under restricted networking.
An approved retry produced no output and timed out after 60 seconds. Its two
orphaned Wren/Python indexing processes were stopped without touching the
separate long-running Context Builder Python process. This does not affect the
successful Wren validate/build/dry-run acceptance checks.

Data Subagent TPC-H smoke verification:

```text
first run: 20260714-123911-tpch_starrocks_smoke, 4/5
first-run failure cause: eval expected physical alias n_name, while equivalent SQL used alias nation
gold execution equivalence for the case: passed
corrected eval: compare business values rather than a non-semantic alias
rerun: 20260714-124142-tpch_starrocks_smoke_rerun, 5/5
```

Rerun trace IDs:

```text
order count: trace_d65d1ef6019a403b86d2ad0602cbfb65
lineitem count: trace_c5c6860cd5bd439295382f54b4dce393
orders by status: trace_5a6aace4f29d434aaa185c7ae688ccc3
orders by customer nation: trace_c4610ca357734c3d93f55a44fdef7042
lineitem-partsupp composite join: trace_97976c46fe5e4f05b18583a7b47e84e9
```

The 30-minute Codex transport timeout happened after the candidate and final
message were written. The Builder now supports an auditable
`accepted_after_timeout` state only when models, snapshot, manifest, executed
query evidence, Wren validate/build, and optional dry-run all pass independently.
Timeout alone never accepts a candidate.

### New Session Reading Order

Always start with:

```text
AGENTS.md
docs/data_subagent_progress_and_pitfalls.md
```

For the online Data Subagent runtime, continue with:

```text
docs/data_subagent_architecture_workflow_react.html
docs/data_subagent_mvp_real_case.html
src/data_subagent/
```

For WrenAI context / MDL onboarding, continue with:

```text
new_session_prompt_for_wren_context_builder.md
docs/wren_context_builder_plan.md
docs/wren_context_builder_feasibility.md
docs/wren_context_builder_methods.html
src/data_subagent_context_builder/
```

Before editing, run `git status --short`. The Context Builder implementation,
tests, docs, and generated presentation/logbook artifacts may be uncommitted.
Preserve all existing changes and never reset or discard them.

Implemented runtime:

```text
question
-> local clarity check
-> Wren get_context
-> Wren recall_examples
-> DeepSeek generate_sql
-> local read-only SQL guardrail
-> Wren dry-plan
-> Wren dry-run
-> optional DeepSeek repair_sql loop
-> Wren execute
-> DeepSeek summarize_result
-> JSONL trace
```

Current real data source:

```text
Wren quickstart jaffle_shop
DuckDB database built from dbt
BIRD Mini-Dev debit_card_specializing
SQLite converted to DuckDB and generated Wren project
```

Current real integration:

- WrenAI CLI is installed and used through `WrenCliAdapter`.
- DeepSeek is used through `DeepSeekLLMAdapter`.
- DeepSeek calls now retry transient failures and malformed/empty JSON responses
  before surfacing an error.
- The CLI entry point supports `doctor-wren` and `ask`.
- A debug/eval-only repair demo can be triggered with `--inject-initial-sql`.
- The CLI entry point also supports `eval` for JSONL eval suites.
- The eval CLI supports Wren project overrides for external benchmark projects.

## 2. Architecture Decisions

WrenAI is not reimplemented in this repo. It is used as the semantic and
execution layer.

The boundary is:

```text
src/data_subagent/adapters/wren_base.py
src/data_subagent/adapters/wren_cli.py
```

`DataSubagent` owns the controlled loop. It decides when to call Wren, when to
call DeepSeek, when to repair, and when to save trace.

DeepSeek owns:

- SQL generation
- SQL repair after Wren errors
- result summarization and chart spec generation

Wren owns:

- model/context visibility
- semantic SQL expansion through dry-plan
- database executable validation through dry-run
- query execution

Codex SDK is not part of the online question-answering runtime. The intended
future use is:

```text
traces / evals / failure cases
-> Codex SDK background improvement runtime
-> candidate code, prompt, Wren context, or eval changes
-> tests and human review
```

## 3. Important Files

Core runtime:

```text
src/data_subagent/agent.py
src/data_subagent/cli.py
src/data_subagent/config.py
src/data_subagent/eval_runner.py
src/data_subagent/llm_deepseek.py
src/data_subagent/sql_guardrail.py
src/data_subagent/trace_store.py
src/data_subagent/adapters/wren_cli.py
```

Tests:

```text
tests/test_agent_loop.py
tests/test_eval_runner.py
tests/test_llm_deepseek.py
tests/test_prepare_bird_mini_dev_subset.py
tests/test_sql_guardrail.py
tests/test_trace_store.py
```

Wren project:

```text
data/wren/jaffle_wren_project/wren_project.yml
data/wren/jaffle_wren_project/models/*/metadata.yml
data/wren/jaffle_wren_project/relationships.yml
data/wren/jaffle_wren_project/knowledge/sql/*.md
```

Eval helpers:

```text
data/evals/cases/jaffle_smoke.jsonl
data/evals/cases/bird_mini_dev_debit_card_specializing.jsonl
data/evals/cases/README.md
scripts/prepare_bird_mini_dev_subset.py
scripts/prepare_sqlite_wren_project.py
scripts/setup_bird_mini_dev_eval.py
```

Docs:

```text
docs/data_subagent_architecture_workflow_react.html
docs/data_subagent_bird_smoke_cases.html
docs/data_subagent_mvp_real_case.html
docs/data_subagent_react_repair_demo.md
docs/data_subagent_eval_dataset_research.md
docs/wren_and_open_source_feasibility.md
docs/wren_jaffle_setup_and_smoke.md
docs/data_subagent_mvp_plan.md
```

Documentation update on 2026-07-09:

```text
docs/data_subagent_architecture_workflow_react.html
```

The architecture page now embeds the generated workflow/ReAct diagram directly
as a base64 data URI. It no longer depends on an external image reference and
now explains the diagram, workflow stages, ReAct repair loop, Wren dry-plan /
dry-run / execute, and Trace/Eval role in one page.

New upstream workstream prompt on 2026-07-09:

```text
new_session_prompt_for_wren_context_builder.md
docs/wren_context_builder_plan.md
docs/wren_context_builder_feasibility.md
```

This workstream is separate from the Data Subagent runtime. Its goal is to
research, design, and possibly implement a WrenAI Context Builder / MDL
Onboarding Tool that can take a database or dbt project and produce a Wren
project, validation/build results, onboarding report, and smoke eval cases.
The builder should use WrenAI native capabilities first and only use scripts as
glue/fallback scaffolding.

First Context Builder feasibility pass on 2026-07-09:

- Local Wren CLI is `wrenai 0.12.0`.
- `wren context import --help` and `wren profile import --help` both list
  `dbt` as the current import source.
- `wren context init/validate/build` support OSI/MDL inputs, but this is not
  native arbitrary database introspection.
- `wren skills get generate-mdl` is the installed Wren workflow for generic
  database onboarding: agent/script inspects schema, Wren handles project
  scaffolding, type normalization, validate/build, and query primitives.
- `wren docs connection-info --format json` exposes datasource profile fields
  and should drive profile template/report generation.
- `scripts/prepare_sqlite_wren_project.py` is reusable as the first
  SQLite/DuckDB fallback seed, while BIRD dataset discovery/eval conversion
  should stay benchmark glue.

First Context Builder implementation on 2026-07-09:

```text
src/data_subagent_context_builder/
tests/test_context_builder.py
```

Implemented commands:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent_context_builder.cli inspect ...
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent_context_builder.cli generate-from-db ...
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent_context_builder.cli validate ...
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent_context_builder.cli enrich-with-codex ...
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent_context_builder.cli make-smoke-eval ...
```

`generate-from-db` currently supports SQLite input through the existing
SQLite-to-DuckDB fallback flow. It writes a DuckDB-backed Wren project/profile,
runs Wren `context validate`, `context build`, optional `dry-run`, and can write
an onboarding report. This is still schema-level draft MDL, not automatic
business semantic modeling.

Verification:

```text
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest tests.test_context_builder
Ran 2 tests
OK

$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
Ran 22 tests
OK
```

Real Wren smoke on a temporary SQLite fixture:

```text
ok: true
models: customers, orders
relationship_count: 1
context validate: Valid - 2 models, 0 views, 1 relationships.
context build: built target/mdl.json
dry-run "select count(*) as order_count from orders": OK
```

Wren-native Context Builder pass on 2026-07-10:

- SQLite fallback generation now uses Wren type normalization through
  `wren.type_mapping.parse_type(raw_type, "sqlite")`.
- Context Builder `generate-from-db` now scaffolds the target project with
  `wren context init --empty` before writing model metadata.
- The remaining non-native glue is still required for SQLite: schema
  introspection with SQLite PRAGMA, SQLite-to-DuckDB conversion, and YAML
  model/relationship writing. WrenAI CLI `0.12.0` still has no verified generic
  `context import database` command.

Verification:

```text
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
Ran 27 tests
OK

generate-from-db real temporary SQLite smoke:
context init --empty --force: OK
type normalization: INTEGER -> INT, REAL -> FLOAT, DATETIME -> DATETIME
context validate: Valid - 2 models, 0 views, 1 relationships.
context build: Built 2 models, 0 views
dry-run "select count(*) as order_count from orders": OK
```

Skill-first Context Builder decision on 2026-07-10:

- `generate-from-db` is now the recommended Wren `generate-mdl` skill path.
- For SQLite, it prepares factual inputs only: Wren `context init --empty`,
  SQLite-to-DuckDB runtime conversion, Wren-normalized schema manifest, DuckDB
  profile, and a Codex prompt that requires reading
  `wren skills get generate-mdl` before writing MDL.
- It does not write `models/*/metadata.yml` by default.
- The old deterministic SQLite YAML generation is retained as explicit
  `generate-schema-draft` / `generate-from-db --mode draft` fallback.
- This keeps MDL authoring unified around Wren's skill workflow while preserving
  reproducible glue for schema facts and validation substrates.

Verification:

```text
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
Ran 30 tests
OK

generate-from-db real temporary SQLite smoke:
ok: true
mode: skill
context init --empty --force: OK
schema_manifest_path: wren_project/onboarding/schema_manifest.json
codex.executed: false
models/orders/metadata.yml exists: false

generate-schema-draft fallback smoke:
context validate: Valid - 2 models, 0 views, 1 relationships.
context build: Built 2 models, 0 views
dry-run "select count(*) as order_count from orders": OK
```

Codex runtime scaffold added to Context Builder:

```text
src/data_subagent_context_builder/codex_runtime.py
tests/test_context_builder_codex_runtime.py
```

Purpose:

- Keep Codex agent work in upstream Wren context onboarding/enrichment.
- Do not place Codex SDK/CLI inside the online Data Subagent ask path.
- Generate a Codex prompt that tells the agent to read project docs, inspect
  Wren's installed `generate-mdl` skill, edit only the target Wren project, and
  rerun Wren validate/build/dry-run.
- Default behavior is prompt-only. `--execute` is required before invoking
  `codex exec`.

Local availability check:

```text
.\.venv-wren\python.exe -m pip show openai-codex
WARNING: Package(s) not found: openai-codex

codex --help
Codex CLI available, including exec and experimental app-server commands.
```

Verification:

```text
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest tests.test_context_builder_codex_runtime tests.test_context_builder
Ran 5 tests
OK

Prompt-only enrich-with-codex smoke:
ok: true
executed: false
```

Smoke eval generation added:

```text
src/data_subagent_context_builder/smoke_eval.py
tests/test_context_builder_smoke_eval.py
```

Purpose:

- Read Wren model metadata.
- Emit conservative Data Subagent eval JSONL cases.
- Default to row-count questions per model because they are stable onboarding
  health checks for schema-level draft MDL.
- Keep relationship join smoke optional via `--include-relationship-case`.

Verification:

```text
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest tests.test_context_builder_smoke_eval
Ran 2 tests
OK

make-smoke-eval against data/wren/jaffle_wren_project:
ok: true
emitted: 3
eval_ids: jaffle_shop_customers_count, jaffle_shop_orders_count, jaffle_shop_stg_customers_count
```

Context Builder inspect command added on 2026-07-10:

```text
src/data_subagent_context_builder/inspect.py
tests/test_context_builder_inspect.py
```

Purpose:

- Read SQLite schema facts without generating DuckDB, Wren project files, or
  Wren home state.
- Emit JSON and optional Markdown reports for Wren `generate-mdl` onboarding,
  Codex prompts, and human semantic review.
- Preserve warnings for incomplete SQLite FK metadata while preventing bad
  relationships from entering generated Wren YAML.

The SQLite fallback generator now skips FK rows whose child or parent column is
missing in SQLite `PRAGMA foreign_key_list` output. This prevents bad generated
join conditions such as:

```text
"yearmonth"."CustomerID" = "customers"."None"
```

Verification:

```text
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
Ran 33 tests
OK

inspect against BIRD Mini-Dev debit_card_specializing:
table_count: 5
relationship_count: 0
warnings: 2 incomplete SQLite FK metadata warnings
report_path: data/tmp/context_builder_inspect_smoke/schema_report.md
json_output_path: data/tmp/context_builder_inspect_smoke/schema_report.json
```

Context Builder outer Codex repair loop added on 2026-07-10:

```text
src/data_subagent_context_builder/skill_onboarding.py
src/data_subagent_context_builder/codex_runtime.py
src/data_subagent_context_builder/report.py
tests/test_context_builder_skill_onboarding.py
```

Purpose:

- Keep `generate-from-db --mode skill` as the first-line Codex + Wren
  `generate-mdl` workflow.
- When `--execute` is used, the outer builder now runs Codex in bounded rounds,
  then runs Wren `context validate`, `context build`, and optional `dry-run`
  itself.
- If outer Wren validation fails, the builder writes a repair prompt containing
  the structured Wren command outputs and invokes Codex again, up to
  `--max-repair-rounds`.
- This is the deterministic outer validation/repair guardrail around Codex's
  own in-process skill-following loop.

New CLI controls:

```powershell
--max-repair-rounds 2
--no-post-validate
```

Artifacts:

```text
<wren_project>/onboarding/prompts/round_<n>.md
<wren_project>/onboarding/codex_last_messages/round_<n>.md
<wren_project>/onboarding/validation/round_<n>.json
```

Onboarding reports now include Codex execution rounds and final outer Wren
validation output.

Verification:

```text
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
Ran 34 tests
OK
```

Prompt boundary refinement on 2026-07-10:

- The generated Codex prompt now states that Wren's installed `generate-mdl`
  skill takes precedence if it conflicts with the prompt.
- `schema_manifest.json` is described as seed evidence, not the complete
  semantic model.
- Codex is explicitly allowed and expected to inspect the DuckDB runtime
  directly when the Wren skill calls for schema checks, sample queries,
  relationship validation, or orphan checks.
- Relationships, descriptions, rules, and examples should be grounded in the
  manifest, runtime data, user instructions, or other explicit evidence rather
  than guessed from names alone.

Real BIRD Context Builder Codex + Wren skill-first run on 2026-07-10:

Input:

```text
data/external/bird_mini_dev/raw/minidev/minidev/MINIDEV/dev_databases/debit_card_specializing/debit_card_specializing.sqlite
```

Command shape:

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli `
  --project-root . `
  generate-from-db `
  --sqlite-path data\external\bird_mini_dev\raw\minidev\minidev\MINIDEV\dev_databases\debit_card_specializing\debit_card_specializing.sqlite `
  --project-name bird_debit_card_context_builder_real `
  --project-dir data\tmp\context_builder_bird_real\wren_project `
  --duckdb-path data\tmp\context_builder_bird_real\bird_debit_card.duckdb `
  --wren-home data\tmp\context_builder_bird_real\wren_home `
  --smoke-sql "select count(*) as transaction_count from transactions_1k" `
  --prompt-output data\tmp\context_builder_bird_real\generate_mdl_prompt.md `
  --report-path data\tmp\context_builder_bird_real\onboarding_report.md `
  --execute `
  --max-repair-rounds 1 `
  --codex-bin codex.cmd `
  --force
```

Result:

```text
Codex round 0: returncode 0
repair_rounds_used: 0
outer context_validate: Valid - 5 models, 0 views, 4 relationships.
outer context_build: Built target/mdl.json
outer dry_run "select count(*) as transaction_count from transactions_1k": OK
```

Generated artifacts:

```text
data/tmp/context_builder_bird_real/wren_project/models/*/metadata.yml
data/tmp/context_builder_bird_real/wren_project/relationships.yml
data/tmp/context_builder_bird_real/wren_project/knowledge/rules/general.md
data/tmp/context_builder_bird_real/wren_project/knowledge/sql/*.md
data/tmp/context_builder_bird_real/wren_project/target/mdl.json
data/tmp/context_builder_bird_real/wren_project/onboarding/prompts/round_0.md
data/tmp/context_builder_bird_real/wren_project/onboarding/codex_last_messages/round_0.md
data/tmp/context_builder_bird_real/wren_project/onboarding/validation/round_0.json
data/tmp/context_builder_bird_real/onboarding_report.md
```

Codex added 4 verified relationships. The input SQLite FK metadata was
incomplete, so this confirms the intended split: deterministic inspect/generator
does not emit bad FK joins, while Codex + Wren validation can add defensible
relationships after checking the runtime data.

New fixes from the real run:

- `--codex-bin` may need the full path returned by `(Get-Command codex).Source`
  on Windows because Python subprocess cannot reliably launch the npm
  PowerShell shim `codex.ps1` by the bare name `codex`.
- Context Builder CLI now reconfigures stdout to UTF-8 so printing JSON with
  symbols such as `€`, `—`, or `→` does not fail under a GBK console.
- Skill-first reports now refresh model and relationship counts from the actual
  Codex-generated Wren project before writing the final report.

Post-run validation:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
.\.venv-wren\python.exe -m data_subagent_context_builder.cli validate `
  --project-dir data\tmp\context_builder_bird_real\wren_project `
  --wren-home data\tmp\context_builder_bird_real\wren_home `
  --smoke-sql "select count(*) as transaction_count from transactions_1k"
```

Result:

```text
ok: true
context_validate: Valid - 5 models, 0 views, 4 relationships.
context_build: Built target/mdl.json
dry_run: OK
```

Documentation added on 2026-07-09:

```text
docs/wren_context_builder_methods.html
```

This page explains the different WrenAI context/MDL construction paths:

- dbt native import
- existing MDL / OSI input
- hand-written or ordinary agent-generated Wren YAML
- `generate-mdl` skill workflow
- `dlt-connector` skill/script path

It clarifies that generic database onboarding is currently agent/script schema
introspection plus Wren validate/build, not a single Wren core command that
automatically imports arbitrary databases into a high-quality business semantic
layer.

## 4. Verified Commands

Use `.venv-wren/python.exe`, not `.venv-wren/Scripts/python.exe`.

Run unit tests:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
```

Latest verified result:

```text
Ran 20 tests
OK
```

Check Wren setup:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli doctor-wren
```

Expected shape:

```json
{
  "models": ["customers", "orders", "stg_customers", "stg_orders", "stg_payments"],
  "dry_run_ok": true,
  "dry_run_message": "OK"
}
```

Ask a real question:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?"
```

Run a real Wren + DeepSeek ReAct repair demo:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?" --inject-initial-sql "SELECT bad_column FROM orders" --limit 5
```

The repair demo intentionally injects a bad first SQL attempt. The Wren error,
DeepSeek repair, Wren dry-run, Wren execute, and summarization are real.

Run the jaffle eval suite:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval --suite data\evals\cases\jaffle_smoke.jsonl --suite-name jaffle_smoke --limit 20
```

For `eval`, `--limit` means case count. Use `--query-limit` to change the row
limit for each SQL execution. For `ask`, `--limit` still means query row limit.

Latest verified eval result:

```text
run_id: 20260709-145158-jaffle_smoke
total: 5
passed: 5
failed: 0
duration_ms: 59300
run_path: data/evals/runs/20260709-145158-jaffle_smoke.jsonl
report_path: data/evals/reports/20260709-145158-jaffle_smoke.md
```

Eval records now include timing:

```text
suite started_at / finished_at / duration_ms
case started_at / finished_at / duration_ms
```

Rationale: pass/fail alone is not enough. Timing lets us compare prompt,
provider, Wren context, and repair-loop changes for latency regressions.

Eval records also preserve `gold_sql` when external converters provide it.
Failing cases with `gold_sql` get:

```text
review_status: needs_triage
```

This is deliberate. BIRD / Spider2-style benchmark labels can be noisy, so a
single gold-SQL mismatch must not automatically trigger prompt or Wren context
changes.

Eval now also validates read-only `gold_sql` through Wren:

```text
gold_sql_check.guardrail_ok
gold_sql_check.dry_run_ok
gold_sql_check.execute_ok
gold_sql_check.gold_row_count
gold_sql_check.execution_match
gold_sql_check.needs_triage
gold_sql_check.error
```

If automatic checks pass but predicted rows and gold rows differ, the case stays
`status: pass` but becomes `review_status: needs_triage`. The report includes
these cases under `Review Details`.

BIRD Mini-Dev conversion scaffold:

```powershell
.\.venv-wren\python.exe scripts\prepare_bird_mini_dev_subset.py `
  --input data\external\bird_mini_dev\mini_dev_sqlite.json `
  --output data\evals\cases\bird_mini_dev_subset.jsonl `
  --db-id debit_card_specializing `
  --limit 30
```

This only converts local BIRD JSON into eval case JSONL. It does not download
the dataset and does not create a Wren project. The next step is generating or
importing Wren context for the selected BIRD SQLite database.

SQLite-to-Wren project generation scaffold:

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

The Data Subagent CLI can now run against non-default Wren projects:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\bird_mini_dev_subset.jsonl `
  --suite-name bird_mini_dev_subset `
  --wren-project-dir data\wren\bird_<db_id>_wren_project `
  --wren-home data\wren\home
```

Combined BIRD Mini-Dev setup scaffold:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --source-dir data\external\bird_mini_dev\raw `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

If Hugging Face network access works, add `--download`:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --download `
  --source-dir data\external\bird_mini_dev\raw `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

If Hugging Face is unavailable, use the BIRD OSS package shortcut:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --download-oss `
  --source-dir data\external\bird_mini_dev\raw `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

OSS package check on 2026-07-09:

```text
URL: https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip
Status: 200
Content-Length: 800943648 bytes
Approx size: 764 MB compressed
```

The script expects to find BIRD files such as:

```text
data/external/bird_mini_dev/raw/**/mini_dev_sqlite.json
data/external/bird_mini_dev/raw/**/<db_id>.sqlite
```

It emits:

```text
data/evals/cases/bird_mini_dev_<db_id>.jsonl
data/wren/bird_<db_id>.duckdb
data/wren/bird_<db_id>_wren_project/
```

Verified with real BIRD Mini-Dev `debit_card_specializing` on 2026-07-09:

```powershell
.\.venv-wren\python.exe scripts\setup_bird_mini_dev_eval.py `
  --source-dir data\external\bird_mini_dev\raw\minidev\minidev\MINIDEV `
  --db-id debit_card_specializing `
  --limit 30 `
  --force
```

Result:

```text
emitted: 30
models: customers, gasstations, products, transactions_1k, yearmonth
relationships: 2
duckdb_path: data/wren/bird_debit_card_specializing.duckdb
wren_project_dir: data/wren/bird_debit_card_specializing_wren_project
```

Wren verification:

```powershell
$env:WREN_HOME = (Resolve-Path 'data\wren\home').Path
.\.venv-wren\Scripts\wren.exe context validate
.\.venv-wren\Scripts\wren.exe context build
.\.venv-wren\Scripts\wren.exe dry-run --sql "select count(*) as customer_count from customers"
```

Result:

```text
context validate: Valid - 5 models, 0 views, 2 relationships
context build: built target/mdl.json
dry-run: OK
```

BIRD smoke eval:

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\bird_mini_dev_debit_card_specializing.jsonl `
  --suite-name bird_mini_dev_debit_card_specializing_smoke5 `
  --wren-project-dir data\wren\bird_debit_card_specializing_wren_project `
  --wren-home data\wren\home `
  --limit 5
```

Latest verified result:

```text
run_id: 20260709-165501-bird_mini_dev_debit_card_specializing_smoke5
total: 5
passed: 4
failed: 1
duration_ms: 93138
run_path: data/evals/runs/20260709-165501-bird_mini_dev_debit_card_specializing_smoke5.jsonl
report_path: data/evals/reports/20260709-165501-bird_mini_dev_debit_card_specializing_smoke5.md
```

Representative trace IDs:

```text
auto_pass: trace_73da8bceb38d4ed68bf72244d8e5f2e3
auto_pass: trace_f1188fd1f14f460c97182b60efdf4f29
needs_triage gold mismatch: trace_9e4f4e17a9c04474bda41a7ab49aa190
needs_triage gold mismatch: trace_1b5e4bc5d42447909e9e3aaa847538bc
DeepSeek empty-response failure: trace_3d6666ca72ef486380c7696a419a7494
```

Interpretation:

- 4/5 means the runtime produced executable Wren-backed answers.
- 2/5 were auto-pass with predicted and gold execution matching.
- 2/5 were runtime pass but `review_status: needs_triage` because predicted
  and gold result rows differed.
- 1/5 failed because DeepSeek returned an empty or unparsable SQL JSON response.
- This result should drive grouped triage, not blind prompt edits.

Verified on 2026-07-09 with a temporary BIRD-shaped fixture:

```text
setup_bird_mini_dev_eval.py emitted 1 SELECT-only case
created eval JSONL
created DuckDB file
created Wren project
created Wren profile
```

Verified on 2026-07-09 with a temporary SQLite fixture:

```text
prepare_sqlite_wren_project.py emitted 2 models and 1 relationship
wren context validate: Valid — 2 models, 0 views, 1 relationships.
wren context build: built target/mdl.json
wren dry-run "select count(*) as order_count from orders": OK
```

## 5. Real Demo Cases

### Normal Success Path

Question:

```text
收入最高的前5个客户是谁？
```

Final SQL:

```sql
SELECT first_name, last_name, customer_lifetime_value
FROM customers
ORDER BY customer_lifetime_value DESC
LIMIT 5
```

Result:

```text
Howard R.      99.0
Kathleen P.    65.0
Norma C.       64.0
Christina W.   57.0
Rose M.        57.0
```

Trace:

```text
trace_f4babfdf564c4efdb646fca1e2141505
```

### ReAct Repair Path

Question:

```text
How many orders are there?
```

Injected bad SQL:

```sql
SELECT bad_column FROM orders
```

Wren dry-run observation:

```text
Binder Error: Referenced column "bad_column" not found in FROM clause!
phase=SQL_DRY_RUN
```

DeepSeek repaired SQL:

```sql
SELECT COUNT(*) FROM orders
```

Result:

```json
[{"count_star()": 99}]
```

Trace:

```text
trace_8123219a172d4ed2b7c977e8af45a4d1
```

## 6. Wren Usage Details

This repo uses a real WrenAI CLI installation, not a mock context layer.

Current config:

```text
wren_bin: .venv-wren/Scripts/wren.exe
wren_project_dir: data/wren/jaffle_wren_project
wren_home: data/wren/home
```

Adapter mapping:

```text
get_context()
  -> wren context show --output json
  -> wren memory describe

recall_examples()
  -> read data/wren/jaffle_wren_project/knowledge/sql/*.md

dry_plan(sql)
  -> wren dry-plan --sql ...

dry_run(sql)
  -> wren dry-run --sql ...

execute(sql)
  -> wren query --sql ... --output json --quiet --limit ...
```

`recall_examples()` currently reads markdown examples directly instead of using
`wren memory recall`. This was a stability choice for Windows.

For BIRD SQLite evals, the current Wren context layer is generated by this repo,
then consumed by WrenAI CLI. It is not a WrenAI-native automatic SQLite import:

```text
BIRD SQLite schema
-> scripts/prepare_sqlite_wren_project.py
-> data/wren/bird_<db_id>_wren_project/
-> WrenAI CLI context validate/build/dry-plan/dry-run/query
```

This means:

- WrenAI is still mandatory and is used for context validation, semantic SQL
  expansion, dry-run, and execution.
- The minimal BIRD MDL/model metadata files are authored by our generator.
- The generated BIRD context is schema-level only and currently lacks curated
  business metrics, synonyms, rules, and high-quality examples.
- Relationship generation has a known issue for `debit_card_specializing`:
  generated conditions include `"customers"."None"`. Fix this before relying
  on relationship-driven joins.

## 7. Known Pitfalls And Workarounds

### Python Path In The Wren Env

The project-local environment uses:

```text
.venv-wren/python.exe
```

Do not assume this exists:

```text
.venv-wren/Scripts/python.exe
```

### Wren CLI Unicode On Windows

Wren CLI can print Unicode symbols that fail under a GBK console. Use:

```powershell
$env:PYTHONIOENCODING='utf-8'
```

`WrenCliAdapter` already sets this for subprocess calls.

Context Builder note from 2026-07-09: `wren context validate` reached warning
printing on `data/wren/jaffle_wren_project`, then failed with
`UnicodeEncodeError` when `PYTHONIOENCODING` was not set. With UTF-8 enabled it
completed with 3 warnings and 0 errors. Any builder subprocess wrapper should
set this env var.

### Wren Memory Fetch / Recall On Windows

`wren memory fetch` and `wren memory recall` can hang during first-time
memory/embedding initialization on Windows.

Current workaround:

- `get_context()` uses `context show --output json` and `memory describe`
- `recall_examples()` reads confirmed examples from `knowledge/sql/*.md`

### Wren CLI Output Formats

Observed behavior:

- `dry-plan` returns expanded SQL text, not JSON.
- `dry-run` returns `OK` or error text, not JSON.
- `query --output json --quiet` can return JSON object lines, not only a JSON
  array.

The adapter already handles this.

### Chinese Trace Display In PowerShell

Trace JSONL is written as UTF-8. `Get-Content` can display Chinese as mojibake
depending on the console encoding. The file contents are still valid UTF-8.

### Secret Handling

`deepseek_apikey.txt` is local-only and ignored by `.gitignore`. Do not print or
copy it into documentation, traces, commits, or screenshots.

Before the first GitHub push on 2026-07-22, the ignore rules were broadened to
cover any local `*apikey*.txt` file and COMP7706 draft logbooks. This prevents
alternate credential files and potentially personal practicum drafts from
being staged accidentally; reviewed presentation artifacts remain opt-in.

### DeepSeek Summary JSON Can Be Malformed

An eval run on 2026-07-09 initially got 4/5 passing cases. The failing case had
valid SQL, valid Wren dry-run, and valid Wren execution, but the DeepSeek summary
response could not be parsed as strict JSON:

```text
Unterminated string starting at: line 2 column 13
```

Fix:

- SQL generation and repair still require strict JSON.
- `summarize_result()` now falls back to a deterministic summary when only the
  summary JSON parse fails.

Verification after fix:

```text
Ran 12 tests
OK

jaffle_smoke eval: 5/5 passed
```

### DeepSeek Empty Or Malformed JSON Should Retry

Earlier BIRD smoke testing produced a failure where DeepSeek returned an empty
or unparsable SQL JSON response before Wren dry-plan/dry-run could run:

```text
trace_3d6666ca72ef486380c7696a419a7494
Failed to parse LLM JSON response: ''
```

Fix on 2026-07-09:

- `DeepSeekLLMAdapter` retries parse failures, unexpected response shapes,
  network timeouts, URL errors, HTTP 429, and HTTP 5xx responses.
- Defaults are `max_retries=2`, `retry_initial_delay_seconds=1.0`, and
  exponential backoff factor `2.0`.
- HTTP 400/401-style configuration or request errors are not retried.
- `summarize_result()` still falls back to deterministic text after retry
  exhaustion, while `generate_sql()` and `repair_sql()` surface the error.

Verification:

```text
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest tests.test_llm_deepseek
Ran 3 tests
OK

$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m unittest discover -s tests
Ran 20 tests
OK
```

### Eval Timing Should Be Recorded

Eval runs now record UTC timestamps and elapsed duration:

```text
suite started_at / finished_at / duration_ms
case started_at / finished_at / duration_ms
```

Use timestamps to align with trace records, and use duration to catch latency
regressions across prompt/model/Wren changes. `duration_ms` is measured with a
monotonic timer.

### Wren Context Import Is dbt-Only In Current CLI

Checked on 2026-07-09:

```powershell
.\.venv-wren\Scripts\wren.exe context import --help
.\.venv-wren\Scripts\wren.exe profile import --help
```

Both import commands currently list `dbt` as the external import source. Wren
can use DuckDB profiles, but it does not automatically introspect arbitrary
SQLite databases into a Wren project through `context import`.

Re-verified during the Wren Context Builder feasibility pass with WrenAI
`0.12.0`. Additional relevant commands:

```powershell
.\.venv-wren\Scripts\wren.exe context init --help
.\.venv-wren\Scripts\wren.exe context validate --help
.\.venv-wren\Scripts\wren.exe context build --help
.\.venv-wren\Scripts\wren.exe skills get generate-mdl
.\.venv-wren\Scripts\wren.exe docs connection-info --format json
```

The clean interpretation is:

- dbt import is Wren-native.
- OSI/MDL migration/build is Wren-native.
- arbitrary DB onboarding is Wren-assisted agent/script schema discovery, not
  one-command native DB import.

Workaround:

- convert SQLite data into a local DuckDB file
- generate minimal Wren model metadata from SQLite schema
- create/update a Wren DuckDB profile pointing to the DuckDB file directory
- run Data Subagent with `--wren-project-dir`

### SQLite-To-DuckDB Conversion Must Be Bulk Imported

The initial SQLite converter copied rows with Python `executemany`, which timed
out on the real BIRD `debit_card_specializing` database.

Fix:

- use DuckDB `sqlite_scanner` when available
- set DuckDB extension directory to `data/duckdb_extensions`
- bulk import each SQLite table with `CREATE TABLE ... AS SELECT ...`
- fall back to Python row copying only if the extension path fails

Real verification on 2026-07-09:

```text
debit_card_specializing.sqlite: 34 MB
generated DuckDB + Wren project: about 2 seconds through setup script
```

### DuckDB WAL Locks On Windows

Interrupted eval or conversion runs can leave `.venv-wren\python.exe` processes
holding `data/wren/bird_debit_card_specializing.duckdb.wal`.

Observed Wren error:

```text
[ATTACH_DUCKDB_ERROR] Cannot open file ... bird_debit_card_specializing.duckdb.wal
File is already open in ... .venv-wren\python.exe
```

Fixes added on 2026-07-09:

- `setup_bird_mini_dev_eval.py --force` removes both `.duckdb` and `.duckdb.wal`
- `prepare_sqlite_wren_project.py` runs `CHECKPOINT` after conversion
- eval runner flushes JSONL after each case, so a timeout does not lose all
  completed case records

If this recurs, inspect and stop only stale project-local Python processes:

```powershell
Get-Process | Where-Object { $_.Path -like '*dataAgent_mvpLoop*.venv-wren*python.exe' }
```

Do not kill unrelated Python processes.

### Eval Limit Semantics

Before 2026-07-09, `data_subagent.cli eval --limit` accidentally controlled
query row limit, while case count required `--max-cases`. This caused a supposed
smoke5 run to process all 30 BIRD cases.

Current behavior:

```text
ask --limit N       -> SQL result row limit
eval --limit N      -> number of eval cases
eval --query-limit N -> SQL result row limit per case
```

### External Benchmark Results Need Manual Triage

BIRD Mini-Dev is still the recommended first external benchmark, but do not
treat every gold mismatch as proof that the MVP is wrong. A 2026 benchmark audit
reported substantial annotation-error rates in BIRD Mini-Dev / Spider2-style
benchmarks. Use failures as triage inputs:

- check Wren dry-run / execution first
- compare predicted and gold result tables where possible
- group repeated failures by cause before prompt or context changes
- record timing and trace IDs for every run

Current implementation:

- `EvalCase.gold_sql`
- `EvalRunRecord.gold_sql`
- `EvalRunRecord.gold_sql_check`
- `EvalRunRecord.review_status`
- `needs_triage` for failed cases that include `gold_sql`
- `needs_triage` for pass cases whose predicted rows differ from executable
  gold SQL rows

### Hugging Face Network Can Be Unavailable

Observed on 2026-07-09:

```text
huggingface_hub.list_repo_files("birdsql/bird_mini_dev")
WinError 10013 under sandbox
WinError 10060 timeout after approval
```

Do not block on live download. `scripts/setup_bird_mini_dev_eval.py` supports a
local `--source-dir` flow. Put manually downloaded BIRD Mini-Dev SQLite files
under `data/external/bird_mini_dev/raw/`, then run the setup script without
`--download`.

GitHub availability:

```text
git ls-remote https://github.com/bird-bench/mini_dev.git HEAD: OK
shallow clone to data/external/bird_mini_dev/repo: OK
```

The GitHub repo contains README/evaluation/baseline files, but not the full
SQLite database package. Use Hugging Face, OSS zip, or a manually downloaded
package for the actual databases and `mini_dev_sqlite.json`.

### Generated / Local Wren State

Avoid hand-editing or committing:

```text
data/wren/home/
data/wren/jaffle_shop_duckdb/
data/wren/jaffle_wren_project/.wren/
data/traces/*.jsonl
data/tmp/
```

`data/tmp/` is ignored and can be used for local Context Builder smoke fixtures,
generated Wren projects, and onboarding reports that should not be committed.

### Local Git Metadata

Earlier on 2026-07-09, `git status --short` failed because local git metadata
appeared incomplete. Rechecked during the Wren Context Builder feasibility pass:

```text
git status --short
 M docs/data_subagent_progress_and_pitfalls.md
 M docs/wren_context_builder_plan.md
?? docs/wren_context_builder_feasibility.md
```

Git status is currently available again in this workspace. If it fails in a
future session, treat that as local environment drift rather than a project
behavior issue.

## 8. Current Limitations

- The clarity check is only a local minimal heuristic:

  ```python
  len(question.strip()) >= 4 and any(char.isalpha() for char in question.strip())
  ```

  It does not yet understand business ambiguity.

- Real data sources currently include jaffle_shop and BIRD Mini-Dev
  `debit_card_specializing`.
- Wren Python SDK is not used; the MVP uses Wren CLI through subprocess.
- `memory fetch` / `memory recall` are not on the main path.
- There is no FastAPI service yet; CLI is the smoke-test interface.
- Eval runner exists for `jaffle_smoke` and generated BIRD Mini-Dev subsets.
- BIRD eval quality is still early. The generated Wren project has minimal
  schema/relationship context and no curated business examples.
- The SQLite-to-Wren generator creates a minimal schema/foreign-key context. It
  does not infer business metrics, synonyms, caveats, or high-quality NL-SQL
  examples. Those should be added from BIRD evidence/gold SQL or real business
  docs after the first external eval run.

## 9. Recommended Next Steps

Current priority is to stabilize and validate the two existing workstreams, not
to merge them.

Context Builder:

1. Preserve the successful BIRD onboarding artifacts and use them as the first
   reference for the bounded Codex + Wren workflow.
2. Manually review generated model descriptions, relationships, rules, and
   examples before treating a generated Wren project as business-ready.
3. Keep the Wren `generate-mdl` skill path as the default; retain mechanical
   schema generation only as a fallback/debug mode.
4. Add Postgres/MySQL inspection only after the SQLite/DuckDB onboarding
   contract is stable. Generic database onboarding is not implemented yet.
5. Keep dbt onboarding Wren-native. Do not claim an implemented `import-dbt`
   command until it exists and has a real validation run.

Data Subagent:

1. Keep CLI as the MVP entry point. FastAPI remains deferred until a frontend
   or external service needs to call the runtime.
2. Triage BIRD `needs_triage` cases separately before changing prompts or Wren
   context; a gold mismatch is not automatically a runtime bug.
3. Upgrade clarity checking later as a separate business-agent enhancement.
4. Add trace inspection utilities and skippable real Wren/DeepSeek integration
   tests when operational debugging becomes the next priority.
5. Design later Codex improvement work around traces and evals, but keep it out
   of the online ask path.

## 11. Eval Dataset Research Update

Open-source text-to-SQL datasets were reviewed on 2026-07-09. The current
recommendation is:

```text
Phase E0: internal jaffle_shop eval suite
Phase E1: BIRD Mini-Dev SQLite SELECT-only subset
Phase E2: Spider2-DBT
Phase E3: BIRD-Interact / LiveSQLBench for later interactive evaluation
```

Reasoning:

- BIRD Mini-Dev is the best next external fit because it has SQLite variants,
  professional/business-like databases, question/evidence/SQL records, and a
  smaller development subset.
- Spider2-DBT is relevant after the eval harness is stable because it is closer
  to our dbt/DuckDB/Wren setup.
- Spider 1.0 is useful as a classical baseline but is less business-realistic.
- Gretel synthetic_text_to_sql is useful for broad synthetic coverage but should
  not be the primary business validation benchmark.

Detailed notes are in:

```text
docs/data_subagent_eval_dataset_research.md
```

## 10. Documentation Update Protocol

When a future session changes behavior, update this document with:

- new command or result
- changed architecture decision
- new trace ID for a representative run
- new pitfall or workaround
- test result after the change

Do not treat this file as polished public docs. Treat it as engineering memory.
