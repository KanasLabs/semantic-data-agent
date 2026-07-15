# StarRocks MVP schema-level rules

- The dataset is a local development fixture and contains no production data.
- `orders.total_amount` is denominated in CNY.
- Realized revenue is `SUM(orders.total_amount)` for orders where
  `orders.status = 'completed'`.
- Orders with `shipped` or `cancelled` status do not count as realized revenue.
- `order_date` is the observed order date field.
- Customer analysis may use the validated orders-to-customers relationship.
