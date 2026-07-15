---
nl: What is the realized revenue in CNY?
sql: SELECT SUM(total_amount) AS realized_revenue FROM orders WHERE status = 'completed'
source: user_declared_business_truth
datasource: doris
---
