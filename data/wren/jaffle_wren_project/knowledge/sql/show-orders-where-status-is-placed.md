---
nl: Show orders where status is placed
sql: SELECT * FROM orders WHERE status = 'placed' LIMIT 100
source: dbt
datasource: duckdb
---
