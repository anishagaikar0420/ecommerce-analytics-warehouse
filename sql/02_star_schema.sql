-- Staging -> star schema. Surrogate keys on dimensions; fact grain = one order line.

CREATE OR REPLACE TABLE dim_customer AS
SELECT row_number() OVER (ORDER BY customer_id) AS customer_key,
       customer_id, first_name, last_name, email, country, signup_date
FROM stg_customers;

CREATE OR REPLACE TABLE dim_product AS
SELECT row_number() OVER (ORDER BY product_id) AS product_key,
       product_id, product_name, category, unit_price AS list_price, cost
FROM stg_products;

CREATE OR REPLACE TABLE dim_date AS
SELECT strftime(d, '%Y%m%d')::INTEGER AS date_key,
       d::DATE AS full_date,
       year(d) AS year,
       quarter(d) AS quarter,
       month(d) AS month,
       strftime(d, '%Y-%m') AS year_month,
       dayname(d) AS day_name,
       isodow(d) IN (6, 7) AS is_weekend
FROM (SELECT unnest(generate_series(
          (SELECT min(order_date) FROM stg_orders),
          (SELECT max(order_date) FROM stg_orders),
          INTERVAL 1 DAY)) AS d);

CREATE OR REPLACE TABLE dim_payment_method AS
SELECT row_number() OVER (ORDER BY payment_method) AS payment_method_key, payment_method
FROM (SELECT DISTINCT payment_method FROM stg_payments UNION SELECT 'none');

CREATE OR REPLACE TABLE fact_sales AS
SELECT i.order_item_id,
       i.order_id,
       c.customer_key,
       p.product_key,
       pm.payment_method_key,
       strftime(o.order_date, '%Y%m%d')::INTEGER AS date_key,
       o.status AS order_status,
       i.quantity,
       i.unit_price,
       i.discount,
       (i.quantity * i.unit_price)::DECIMAL(12, 2) AS gross_amount,
       round(i.quantity * i.unit_price * (1 - i.discount), 2)::DECIMAL(12, 2) AS net_amount,
       (i.quantity * p.cost)::DECIMAL(12, 2) AS cost_amount
FROM stg_order_items i
JOIN stg_orders o ON o.order_id = i.order_id
JOIN dim_customer c ON c.customer_id = o.customer_id
JOIN dim_product p ON p.product_id = i.product_id
LEFT JOIN stg_payments pay ON pay.order_id = i.order_id
JOIN dim_payment_method pm ON pm.payment_method = coalesce(pay.payment_method, 'none');
