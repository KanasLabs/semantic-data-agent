---
nl: How many line items does each order have?
sql: SELECT orders.o_orderkey, COUNT(lineitem.l_linenumber) AS line_count FROM orders JOIN lineitem ON orders.o_orderkey = lineitem.l_orderkey GROUP BY orders.o_orderkey ORDER BY orders.o_orderkey LIMIT 20
source: tpch_sf001_controlled_discovery
datasource: doris
---
