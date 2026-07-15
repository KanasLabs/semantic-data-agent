CREATE DATABASE IF NOT EXISTS data_agent_mvp;
USE data_agent_mvp;

CREATE TABLE IF NOT EXISTS customers (
    customer_id INT NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    region VARCHAR(50) NOT NULL,
    signup_date DATE NOT NULL
)
ENGINE = OLAP
DUPLICATE KEY(customer_id)
DISTRIBUTED BY HASH(customer_id) BUCKETS 1
PROPERTIES (
    "replication_num" = "1"
);

CREATE TABLE IF NOT EXISTS orders (
    order_id BIGINT NOT NULL,
    customer_id INT NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL
)
ENGINE = OLAP
DUPLICATE KEY(order_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES (
    "replication_num" = "1"
);

TRUNCATE TABLE orders;
TRUNCATE TABLE customers;

INSERT INTO customers VALUES
    (1, 'Alice Chen', 'East', '2025-01-05'),
    (2, 'Bob Li', 'North', '2025-01-12'),
    (3, 'Carol Wang', 'South', '2025-02-03'),
    (4, 'David Zhang', 'East', '2025-02-18'),
    (5, 'Eva Liu', 'West', '2025-03-01');

INSERT INTO orders VALUES
    (1001, 1, '2025-03-01', 'completed', 120.50),
    (1002, 2, '2025-03-02', 'completed', 89.00),
    (1003, 1, '2025-03-04', 'shipped', 210.00),
    (1004, 3, '2025-03-06', 'completed', 56.80),
    (1005, 4, '2025-03-07', 'cancelled', 75.00),
    (1006, 5, '2025-03-08', 'completed', 310.20),
    (1007, 3, '2025-03-09', 'completed', 145.30),
    (1008, 2, '2025-03-10', 'shipped', 199.90);
