---
nl: How many orders are in each observed status code?
sql: SELECT o_orderstatus, COUNT(*) AS order_count FROM orders GROUP BY o_orderstatus ORDER BY o_orderstatus
source: tpch_sf001_controlled_discovery
datasource: doris
---
