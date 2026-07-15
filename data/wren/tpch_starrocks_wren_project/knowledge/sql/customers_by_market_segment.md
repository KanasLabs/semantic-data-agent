---
nl: How many customers are in each market segment code?
sql: SELECT c_mktsegment, COUNT(*) AS customer_count FROM customer GROUP BY c_mktsegment ORDER BY c_mktsegment
source: tpch_sf001_controlled_discovery
datasource: doris
---
