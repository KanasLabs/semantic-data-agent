# Business rules

Add custom rules or guidelines for LLM-based query generation here.
# TPC-H StarRocks candidate rules

- Treat this Context Layer as a reviewable TPC-H schema candidate, not production business truth.
- The StarRocks tables use `DUPLICATE KEY` sort keys, which do not enforce uniqueness. Wren primary keys are snapshot-supported logical candidates only.
- `partsupp` has the inspected composite logical key (`ps_partkey`, `ps_suppkey`); `lineitem` has the inspected composite logical key (`l_orderkey`, `l_linenumber`). Neither is represented as a false single-column Wren primary key.
- Use the composite `lineitem` to `partsupp` relationship for part-supplier context. Direct `lineitem` to `part` and `lineitem` to `supplier` relationships were intentionally omitted to avoid redundant join paths.
- Do not assume a currency, quantity unit, account-balance convention, discount/tax representation, or revenue formula from column names alone.
- Treat order, line, return, priority, segment, shipping, manufacturer, brand, type, and container values as source codes or labels unless an expert confirms their business meanings.
- Do not apply a default date field or default time window. Choose the explicitly requested order, ship, commit, or receipt date.
