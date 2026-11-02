"""Export the star schema as CSVs for Power BI, plus SQL-computed expected values to check the DAX measures against."""
import csv
from pathlib import Path

import duckdb

TABLES = ["fact_sales", "dim_customer", "dim_product", "dim_date", "dim_payment_method"]
C = "SELECT * FROM fact_sales WHERE order_status = 'completed'"
# (measure name as defined in powerbi/measures.dax, SQL returning the value over the whole dataset)
EXPECTED = [
    ("Revenue", f"SELECT sum(net_amount) FROM ({C})"),
    ("Gross Profit", f"SELECT sum(net_amount - cost_amount) FROM ({C})"),
    ("Gross Margin %", f"SELECT sum(net_amount - cost_amount) / sum(net_amount) FROM ({C})"),
    ("Orders", f"SELECT count(DISTINCT order_id) FROM ({C})"),
    ("Units Sold", f"SELECT sum(quantity) FROM ({C})"),
    ("AOV", f"SELECT sum(net_amount) / count(DISTINCT order_id) FROM ({C})"),
    ("Customers", f"SELECT count(DISTINCT customer_key) FROM ({C})"),
    ("Revenue per Customer", f"SELECT sum(net_amount) / count(DISTINCT customer_key) FROM ({C})"),
    ("Repeat Customers", f"SELECT count(*) FROM (SELECT customer_key FROM ({C}) GROUP BY 1 HAVING count(DISTINCT order_id) > 1)"),
    ("Repeat Rate %", f"SELECT count(*) FILTER (WHERE n > 1) * 1.0 / count(*) FROM (SELECT count(DISTINCT order_id) n FROM ({C}) GROUP BY customer_key)"),
    ("Gross Sales", f"SELECT sum(gross_amount) FROM ({C})"),
    ("Discount Amount", f"SELECT sum(gross_amount - net_amount) FROM ({C})"),
    ("Discount %", f"SELECT sum(gross_amount - net_amount) / sum(gross_amount) FROM ({C})"),
    ("All Orders", "SELECT count(DISTINCT order_id) FROM fact_sales"),
    ("Cancelled Orders", "SELECT count(DISTINCT order_id) FROM fact_sales WHERE order_status = 'cancelled'"),
    ("Cancel Rate %", "SELECT count(DISTINCT order_id) FILTER (WHERE order_status = 'cancelled') * 1.0 / count(DISTINCT order_id) FROM fact_sales"),
    ("Returned Orders", "SELECT count(DISTINCT order_id) FROM fact_sales WHERE order_status = 'returned'"),
    ("Return Rate %", "SELECT count(DISTINCT order_id) FILTER (WHERE order_status = 'returned') * 1.0 / count(DISTINCT order_id) FROM fact_sales"),
    ("Avg Units per Order", f"SELECT sum(quantity) * 1.0 / count(DISTINCT order_id) FROM ({C})"),
    ("Revenue (calendar 2023)", f"SELECT sum(f.net_amount) FROM ({C}) f JOIN dim_date d USING (date_key) WHERE d.year = 2023"),
    ("Revenue (calendar 2024)", f"SELECT sum(f.net_amount) FROM ({C}) f JOIN dim_date d USING (date_key) WHERE d.year = 2024"),
    ("Revenue PY (evaluated for 2024)", f"SELECT sum(f.net_amount) FROM ({C}) f JOIN dim_date d USING (date_key) WHERE d.year = 2023"),
    ("Revenue YoY % (2024 vs 2023)", f"SELECT (sum(f.net_amount) FILTER (WHERE d.year = 2024)) / (sum(f.net_amount) FILTER (WHERE d.year = 2023)) - 1 FROM ({C}) f JOIN dim_date d USING (date_key)"),
    ("Revenue YTD (at 2024-12-31)", f"SELECT sum(f.net_amount) FROM ({C}) f JOIN dim_date d USING (date_key) WHERE d.year = 2024"),
    ("Revenue (2024-12 only)", f"SELECT sum(f.net_amount) FROM ({C}) f JOIN dim_date d USING (date_key) WHERE d.year_month = '2024-12'"),
    ("Revenue PM (evaluated for 2024-12)", f"SELECT sum(f.net_amount) FROM ({C}) f JOIN dim_date d USING (date_key) WHERE d.year_month = '2024-11'"),
]


def export_powerbi(con: duckdb.DuckDBPyConnection, root: Path = Path("powerbi"), cohort_csv: Path | None = None) -> dict:
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    rows = {}
    for t in TABLES:
        con.execute(f"COPY {t} TO '{data / (t + '.csv')}' (HEADER, DELIMITER ',')")
        rows[t] = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    if cohort_csv and cohort_csv.exists():
        con.execute(f"COPY (SELECT * FROM read_csv('{cohort_csv}')) TO '{data / 'cohort_retention.csv'}' (HEADER, DELIMITER ',')")
    with (root / "expected_values.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["measure", "expected_value"])
        for name, sql in EXPECTED:
            v = con.execute(sql).fetchone()[0]
            w.writerow([name, round(float(v), 6)])
    return rows
