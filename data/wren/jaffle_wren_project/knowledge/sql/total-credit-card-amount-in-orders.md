---
nl: Total credit_card_amount in orders
sql: SELECT SUM(credit_card_amount) FROM orders
source: dbt
datasource: duckdb
---
