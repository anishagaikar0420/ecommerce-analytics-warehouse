-- Business queries on the star schema. Each "-- name:" line starts a query exported to output/<name>.csv.
-- Revenue metrics use completed orders only.

-- name: monthly_revenue
SELECT d.year_month,
       round(sum(f.net_amount), 2) AS revenue,
       round(sum(f.net_amount - f.cost_amount), 2) AS gross_profit,
       count(DISTINCT f.order_id) AS orders
FROM fact_sales f JOIN dim_date d USING (date_key)
WHERE f.order_status = 'completed'
GROUP BY 1 ORDER BY 1;

-- name: top_products
SELECT p.product_name, p.category,
       sum(f.quantity) AS units_sold,
       round(sum(f.net_amount), 2) AS revenue
FROM fact_sales f JOIN dim_product p USING (product_key)
WHERE f.order_status = 'completed'
GROUP BY 1, 2 ORDER BY revenue DESC LIMIT 10;

-- name: average_order_value
SELECT year_month,
       round(avg(order_total), 2) AS aov
FROM (SELECT d.year_month, f.order_id, sum(f.net_amount) AS order_total
      FROM fact_sales f JOIN dim_date d USING (date_key)
      WHERE f.order_status = 'completed'
      GROUP BY 1, 2)
GROUP BY 1 ORDER BY 1;

-- name: customer_cohort_retention
WITH monthly AS (
    SELECT DISTINCT f.customer_key, date_trunc('month', d.full_date) AS m
    FROM fact_sales f JOIN dim_date d USING (date_key)
    WHERE f.order_status = 'completed'
), cohort AS (
    SELECT customer_key, min(m) AS cohort_month FROM monthly GROUP BY 1
), activity AS (
    SELECT c.cohort_month,
           date_diff('month', c.cohort_month, mo.m) AS months_since_first,
           count(DISTINCT mo.customer_key) AS active_customers
    FROM monthly mo JOIN cohort c USING (customer_key)
    GROUP BY 1, 2
)
SELECT strftime(cohort_month, '%Y-%m') AS cohort_month,
       months_since_first,
       active_customers,
       round(100.0 * active_customers / first_value(active_customers)
             OVER (PARTITION BY cohort_month ORDER BY months_since_first), 1) AS retention_pct
FROM activity
ORDER BY cohort_month, months_since_first;

-- name: order_volume
SELECT d.year_month,
       count(DISTINCT f.order_id) AS orders,
       sum(f.quantity) AS units
FROM fact_sales f JOIN dim_date d USING (date_key)
WHERE f.order_status = 'completed'
GROUP BY 1 ORDER BY 1;

-- name: revenue_by_category
SELECT p.category, round(sum(f.net_amount), 2) AS revenue,
       round(100 * sum(f.net_amount) / sum(sum(f.net_amount)) OVER (), 1) AS pct_of_revenue
FROM fact_sales f JOIN dim_product p USING (product_key)
WHERE f.order_status = 'completed'
GROUP BY 1 ORDER BY revenue DESC;

-- name: gross_margin_by_category
SELECT p.category,
       round(sum(f.net_amount - f.cost_amount), 2) AS gross_profit,
       round(100 * sum(f.net_amount - f.cost_amount) / sum(f.net_amount), 1) AS margin_pct
FROM fact_sales f JOIN dim_product p USING (product_key)
WHERE f.order_status = 'completed'
GROUP BY 1 ORDER BY margin_pct DESC;

-- name: revenue_by_country
SELECT c.country, count(DISTINCT c.customer_key) AS customers, round(sum(f.net_amount), 2) AS revenue
FROM fact_sales f JOIN dim_customer c USING (customer_key)
WHERE f.order_status = 'completed'
GROUP BY 1 ORDER BY revenue DESC;

-- name: payment_method_mix
SELECT pm.payment_method,
       count(DISTINCT f.order_id) AS orders,
       round(sum(f.net_amount), 2) AS revenue
FROM fact_sales f JOIN dim_payment_method pm USING (payment_method_key)
WHERE f.order_status = 'completed'
GROUP BY 1 ORDER BY revenue DESC;

-- name: cancellation_return_rate
SELECT d.year_month,
       round(100.0 * count(DISTINCT f.order_id) FILTER (WHERE f.order_status = 'cancelled') / count(DISTINCT f.order_id), 1) AS cancelled_pct,
       round(100.0 * count(DISTINCT f.order_id) FILTER (WHERE f.order_status = 'returned') / count(DISTINCT f.order_id), 1) AS returned_pct
FROM fact_sales f JOIN dim_date d USING (date_key)
GROUP BY 1 ORDER BY 1;

-- name: repeat_purchase_rate
WITH per_customer AS (
    SELECT customer_key, count(DISTINCT order_id) AS orders
    FROM fact_sales WHERE order_status = 'completed' GROUP BY 1
)
SELECT count(*) AS buying_customers,
       count(*) FILTER (WHERE orders > 1) AS repeat_customers,
       round(100.0 * count(*) FILTER (WHERE orders > 1) / count(*), 1) AS repeat_rate_pct
FROM per_customer;

-- name: top_customers_ltv
SELECT c.customer_id, c.first_name, c.last_name, c.country,
       count(DISTINCT f.order_id) AS orders,
       round(sum(f.net_amount), 2) AS lifetime_value
FROM fact_sales f JOIN dim_customer c USING (customer_key)
WHERE f.order_status = 'completed'
GROUP BY 1, 2, 3, 4 ORDER BY lifetime_value DESC LIMIT 20;
