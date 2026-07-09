---
nl: number_of_orders by first_name in customers
sql: SELECT first_name, SUM(number_of_orders) FROM customers GROUP BY 1
source: dbt
datasource: duckdb
---
