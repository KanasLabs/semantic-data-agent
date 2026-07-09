---
nl: Show stg_payments where payment_method is credit_card
sql: SELECT * FROM stg_payments WHERE payment_method = 'credit_card' LIMIT 100
source: dbt
datasource: duckdb
---
