---
nl: How many yearmonth source rows are associated with each customer segment?
sql: SELECT customers.Segment AS customer_segment, COUNT(*) AS source_row_count FROM yearmonth JOIN customers ON yearmonth.CustomerID = customers.CustomerID GROUP BY customers.Segment ORDER BY source_row_count DESC
source: controlled_starrocks_discovery_2026_07_16
datasource: doris
---
