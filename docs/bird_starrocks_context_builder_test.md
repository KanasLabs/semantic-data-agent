# BIRD Mini-Dev StarRocks Context Builder Test

Date: 2026-07-16

## Scope

This test uses BIRD Mini-Dev `debit_card_specializing` as a realistic five-table
integration case after the deterministic TPC-H phase. The original mechanical
SQLite Wren project is not reused.

```text
BIRD SQLite source
-> reproducible load into StarRocks
-> empty Wren project
-> generate-from-starrocks
-> Codex follows Wren generate-mdl skill
-> controlled StarRocks discovery
-> outer Wren and artifact acceptance
-> manually audited BIRD Verified subset
```

## StarRocks Fixture

Database: `bird_debit_card_specializing`

| Table | Rows |
|---|---:|
| customers | 32,461 |
| gasstations | 5,716 |
| products | 591 |
| transactions_1k | 1,000 |
| yearmonth | 383,282 |

The loader is `scripts/setup_starrocks_bird.py`. It preserves the BIRD column
names, represents `yearmonth` with the composite storage key `(Date,
CustomerID)`, and verifies every target row count against SQLite.

## Skill-First Onboarding Result

Target project:
`data/wren/starrocks_bird_debit_card_specializing_wren_project`

```text
duration: 1,169.4 seconds
controlled queries: 37 executed
models: 5
relationships: 4
repair rounds: 0
wren context validate: passed
wren context build: passed
wren dry-run: passed
artifact validation: passed
```

Accepted snapshot relationships:

- `transactions_1k.CustomerID -> customers.CustomerID`
- `transactions_1k.GasStationID -> gasstations.GasStationID`
- `transactions_1k.ProductID -> products.ProductID`
- `yearmonth.CustomerID -> customers.CustomerID`

All four relationships had complete child coverage and zero observed orphans.
The candidate did not reproduce the old broken `customers.None` relationship.
It also rejected unsupported `CardID`, `ChainID`, and direct
`transactions_1k-to-yearmonth` relationships.

## Gold Audit

The 30 original BIRD cases are classified in
`data/evals/audits/bird_mini_dev_debit_card_specializing_audit.jsonl`.

| Status | Count | Meaning |
|---|---:|---|
| verified | 9 | Question, evidence, and Gold semantics agree |
| corrected | 2 | A concrete semantic correction is required |
| ambiguous | 3 | The question does not define a unique business interpretation |
| invalid_gold | 9 | Gold SQL does not answer the stated question |
| dialect_issue | 7 | Semantics are usable but SQLite SQL must be adapted for StarRocks |

The first target-executed subset is
`data/evals/cases/bird_mini_dev_debit_card_specializing_verified10.jsonl`.
It contains ten manually reviewed cases covering all five tables and all four
accepted relationships. Corrected StarRocks Gold SQL was executed through the
Builder-owned read-only query path before inclusion.

This Verified subset is intentionally not described as canonical BIRD truth.
It is a reviewed project benchmark for this StarRocks/Wren fixture.

## Data Subagent Eval Result

The first run completed all ten cases but the Windows CLI failed while printing
a Czech product description through a GBK console. Its already-written report
showed `4/10`. Root causes were test-chain issues rather than a failed Context
onboarding: duplicate Wren CLI LIMIT application, overly specific SQL fragment
assertions, a distinct-value wording mismatch, and strict floating comparison.

After fixing the test chain without editing the generated Context:

```text
run_id: 20260716-112855-bird_starrocks_debit_card_verified10_rerun
total: 10
passed: 10
failed: 0
auto_pass: 7
needs_triage: 3
duration_ms: 131,826
```

The three triage records passed their business expectations. They differ from
Gold only through an additional explanatory aggregate column or ratio precision
and remain review inputs rather than forced failures.

Full unit verification after the loader and test-chain fixes:

```text
Ran 90 tests
OK
```

## Clarification And Resume HITL

BIRD case 0012 was used as a real ambiguity test. Builder refused to choose
between monthly-row share, distinct-customer qualification, aggregate
Consumption, and an unspecified time scope. It persisted two clarification
questions and paused the revision in `CLARIFICATION_REQUIRED`.

The user confirmed that any monthly row above `46.73` qualifies the customer,
the denominator is all distinct LAM customers with a yearmonth row, and NULL
Consumption keeps the customer in the denominator without qualifying them.

After `resume-revision`, the isolated candidate added the grounded rule and SQL
example. The deterministic result is 3,594 qualifying customers from a 3,611
customer denominator, or `99.5292163%`.

Acceptance result:

```text
candidate/revision: APPROVED / APPROVED
wren validate/build: passed
generated smoke: 3/3
Verified10 regression: 10/10
clarified semantic regression: 1/1
trace: trace_84a76a03435d4c2d8c022dd96ccf9652
approval task: task_bc1cd9b98d3243d2abc2401c39b0bba2
approval provenance: user_review_decision
publication: not performed
```

One test-chain false negative was found: equivalent customer-level SQL used
`GROUP BY + MAX` instead of literal `COUNT(DISTINCT ...)`, and Wren returned the
percentage as a decimal string. The test now accepts equivalent SQL and
normalizes numeric strings before comparison. Eval retry reused the same
candidate and did not rerun Codex.

After the review packet was presented, the user explicitly approved the
candidate. `approve-candidate` created and answered a separate approval task;
it did not publish or create a Context pointer.
