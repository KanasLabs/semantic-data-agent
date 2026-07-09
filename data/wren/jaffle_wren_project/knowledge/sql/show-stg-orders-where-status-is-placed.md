---
nl: Show stg_orders where status is placed
sql: SELECT * FROM stg_orders WHERE status = 'placed' LIMIT 100
source: dbt
datasource: duckdb
---
