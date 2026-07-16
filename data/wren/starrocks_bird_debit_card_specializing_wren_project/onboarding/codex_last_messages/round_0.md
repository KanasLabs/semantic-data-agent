Implemented the reviewable Wren Context candidate entirely inside the target project.

**Discovery**

- Ran 37 controlled queries: 5 tables, 0 failures, 0 truncations.
- Rows: customers 32,461; gasstations 5,716; products 591; transactions 1,000; yearmonth 383,282.
- All tables use unenforced StarRocks `DUPLICATE KEY`, one unpartitioned hash bucket, and no secondary indexes.
- Evidence and findings: [discovery_snapshot.json](<project-root>/data/wren/starrocks_bird_debit_card_specializing_wren_project/onboarding/discovery_snapshot.json:1), [schema_manifest.json](<project-root>/data/wren/starrocks_bird_debit_card_specializing_wren_project/onboarding/schema_manifest.json:1), [starrocks_query_evidence.jsonl](<project-root>/data/wren/starrocks_bird_debit_card_specializing_wren_project/onboarding/starrocks_query_evidence.jsonl:1).

**Generated Context**

- Added five models under [models](<project-root>/data/wren/starrocks_bird_debit_card_specializing_wren_project/models/customers/metadata.yml:1).
- Added four `MANY_TO_ONE` relationships with complete observed coverage and zero orphans in [relationships.yml](<project-root>/data/wren/starrocks_bird_debit_card_specializing_wren_project/relationships.yml:1).
- Added conservative guardrails in [general.md](<project-root>/data/wren/starrocks_bird_debit_card_specializing_wren_project/knowledge/rules/general.md:1) and four grounded SQL examples under `knowledge/sql/`.
- Validation: `Valid — 5 models, 0 views, 4 relationships`; build succeeded; required customer-count dry-run returned `OK`.

**Review Required**

- Assumptions: logical keys and relationship cardinalities are snapshot-supported, not source-enforced; `yearmonth` has only a composite logical key and no false Wren primary key.
- Rejected relationships: missing card and chain dimensions; direct transaction–yearmonth customer join is many-to-many/redundant; their date fields have incompatible, unconfirmed grains.
- Expert questions: `Amount`/`Price`/`Consumption` units and accounting rules, currency linkage, negative consumption meaning, date/time semantics, segment/code definitions, whether `transactions_1k` is a sample, referential guarantees, and future card/chain dimensions.