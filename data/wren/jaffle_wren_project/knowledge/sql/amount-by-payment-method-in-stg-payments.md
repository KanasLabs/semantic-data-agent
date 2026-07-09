---
nl: amount by payment_method in stg_payments
sql: SELECT payment_method, SUM(amount) FROM stg_payments GROUP BY 1
source: dbt
datasource: duckdb
---
