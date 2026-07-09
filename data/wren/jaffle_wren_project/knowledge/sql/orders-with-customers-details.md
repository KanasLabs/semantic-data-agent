---
nl: orders with customers details
sql: SELECT * FROM orders JOIN customers ON orders.customer_id = customers.customer_id
  LIMIT 100
source: dbt
datasource: duckdb
---
