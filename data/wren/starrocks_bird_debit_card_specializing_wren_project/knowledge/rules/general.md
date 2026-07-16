# Business rules

- Treat this Context Layer as a reviewable schema candidate, not production business truth.
- The StarRocks tables use `DUPLICATE KEY` storage keys, which do not enforce uniqueness. Wren primary keys are snapshot-supported logical candidates only.
- `yearmonth` is snapshot-unique on the composite (`Date`, `CustomerID`) pair. Do not treat either column as a single-column primary key.
- Use only the four validated relationships in `relationships.yml`. They had complete observed child coverage and zero orphans at discovery time.
- Do not create a relationship for `transactions_1k.CardID` or `gasstations.ChainID` until corresponding dimension tables and join evidence exist.
- Do not join `transactions_1k` directly to `yearmonth`: shared customer identifiers repeat on both sides, and the two date fields have different source types and unconfirmed grains.
- Do not infer units, currency, tax treatment, accounting meaning, or formulas for `Amount`, `Price`, or `Consumption`. A customer's `Currency` value is not assumed to govern either numeric field.
- Do not filter zero `Amount` or negative `Consumption` values without an expert-confirmed rule.
- Treat customer segments, station segments, country values, product descriptions, and currency values as source labels or codes unless an expert confirms their meaning.
- Do not apply a default date, period transformation, timezone, or reporting window. `transactions_1k.Date`, `transactions_1k.Time`, and `yearmonth.Date` have separate unconfirmed semantics.
- The current `transactions_1k` table has exactly 1,000 inspected rows; do not assume it is complete transaction history.
