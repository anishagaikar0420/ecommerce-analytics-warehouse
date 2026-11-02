-- Raw CSV -> staging: type casting, trimming, standardising, de-duplication.
-- {raw_dir} is substituted by src/ecommerce/etl.py.

CREATE OR REPLACE TABLE stg_customers AS
SELECT customer_id::INTEGER AS customer_id,
       trim(first_name) AS first_name,
       upper(left(trim(last_name), 1)) || lower(substr(trim(last_name), 2)) AS last_name,
       lower(trim(email)) AS email,
       coalesce(nullif(trim(country), ''), 'UNKNOWN') AS country,
       signup_date::DATE AS signup_date
FROM read_csv('{raw_dir}/customers.csv', all_varchar = true)
QUALIFY row_number() OVER (PARTITION BY customer_id::INTEGER ORDER BY updated_at::DATE DESC) = 1;

CREATE OR REPLACE TABLE stg_products AS
SELECT product_id::INTEGER AS product_id,
       trim(product_name) AS product_name,
       trim(category) AS category,
       replace(unit_price, '$', '')::DECIMAL(10, 2) AS unit_price,
       cost::DECIMAL(10, 2) AS cost
FROM read_csv('{raw_dir}/products.csv', all_varchar = true)
QUALIFY row_number() OVER (PARTITION BY product_id::INTEGER ORDER BY product_id) = 1;

CREATE OR REPLACE TABLE stg_orders AS
SELECT order_id::INTEGER AS order_id,
       customer_id::INTEGER AS customer_id,
       order_date::DATE AS order_date,
       lower(trim(status)) AS status
FROM read_csv('{raw_dir}/orders.csv', all_varchar = true)
QUALIFY row_number() OVER (PARTITION BY order_id::INTEGER ORDER BY order_date) = 1;

CREATE OR REPLACE TABLE stg_order_items AS
SELECT order_item_id::INTEGER AS order_item_id,
       order_id::INTEGER AS order_id,
       product_id::INTEGER AS product_id,
       quantity::INTEGER AS quantity,
       unit_price::DECIMAL(10, 2) AS unit_price,
       discount::DECIMAL(4, 2) AS discount
FROM read_csv('{raw_dir}/order_items.csv', all_varchar = true)
QUALIFY row_number() OVER (PARTITION BY order_item_id::INTEGER ORDER BY order_item_id) = 1;

CREATE OR REPLACE TABLE stg_payments AS
SELECT payment_id::INTEGER AS payment_id,
       order_id::INTEGER AS order_id,
       lower(trim(payment_method)) AS payment_method,
       amount::DECIMAL(12, 2) AS amount,
       payment_date::DATE AS payment_date
FROM read_csv('{raw_dir}/payments.csv', all_varchar = true)
QUALIFY row_number() OVER (PARTITION BY payment_id::INTEGER ORDER BY payment_id) = 1;
