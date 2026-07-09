---
nl: credit_card_amount by order_date in orders
sql: SELECT order_date, SUM(credit_card_amount) FROM orders GROUP BY 1
source: dbt
datasource: duckdb
---
