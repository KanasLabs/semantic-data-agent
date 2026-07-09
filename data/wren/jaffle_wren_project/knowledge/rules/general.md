# Imported from dbt

- dbt project: `jaffle_shop`
- dbt profile/target: `jaffle_shop.dev`
- imported models: 5
- imported sources: 0
- imported relationships: 1

Structural metadata comes from `manifest.json` and `catalog.json`. The sections below summarize dbt test-derived constraints and warnings.

## Verified Constraints

- customers.customer_id: NOT NULL, UNIQUE (primary key)
- orders.amount: NOT NULL
- orders.bank_transfer_amount: NOT NULL
- orders.coupon_amount: NOT NULL
- orders.credit_card_amount: NOT NULL
- orders.customer_id: NOT NULL
- orders.gift_card_amount: NOT NULL
- orders.order_id: NOT NULL, UNIQUE (primary key)
- orders.status: accepted values = placed, shipped, completed, return_pending, returned
- stg_customers.customer_id: NOT NULL, UNIQUE (primary key)
- stg_orders.order_id: NOT NULL, UNIQUE (primary key)
- stg_orders.status: accepted values = placed, shipped, completed, return_pending, returned
- stg_payments.payment_id: NOT NULL, UNIQUE (primary key)
- stg_payments.payment_method: accepted values = credit_card, coupon, bank_transfer, gift_card
- orders.customer_id -> customers.customer_id (MANY_TO_ONE join verified)

## Relationships

- orders -> customers (MANY_TO_ONE)

## Data Quality Warnings

- No dbt test warnings detected.
