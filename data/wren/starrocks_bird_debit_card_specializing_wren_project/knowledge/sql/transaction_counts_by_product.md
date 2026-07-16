---
nl: How many transaction rows are associated with each product description?
sql: SELECT products.Description AS product_description, COUNT(*) AS transaction_count FROM transactions_1k JOIN products ON transactions_1k.ProductID = products.ProductID GROUP BY products.Description ORDER BY transaction_count DESC
source: controlled_starrocks_discovery_2026_07_16
datasource: doris
---
