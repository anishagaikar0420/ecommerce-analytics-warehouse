import duckdb
import pytest

from src.ecommerce.etl import build_staging, build_star_schema
from src.ecommerce.export import parse_queries, export_analytics, ANALYTICS_SQL
from src.ecommerce.generate_data import generate
from src.ecommerce.quality import DataQualityError, run_checks
from src.pipeline import run


EXPECTED_KPIS = [
    "monthly_revenue", "order_volume", "average_order_value", "top_products", "revenue_by_category",
    "gross_margin_by_category", "revenue_by_country", "payment_method_mix", "cancellation_return_rate",
    "repeat_purchase_rate", "top_customers_ltv", "customer_cohort_retention",
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wh")
    raw = tmp / "raw"
    generate(raw, seed=7, n_customers=300, n_products=30, n_orders=1500)
    con = duckdb.connect(":memory:")
    build_staging(con, raw)
    build_star_schema(con)
    return con, raw


def test_generation_is_seeded(tmp_path):
    generate(tmp_path / "a", seed=1, n_customers=50, n_products=10, n_orders=100)
    generate(tmp_path / "b", seed=1, n_customers=50, n_products=10, n_orders=100)
    assert (tmp_path / "a/orders.csv").read_text() == (tmp_path / "b/orders.csv").read_text()


def test_staging_dedupes_and_casts(built):
    con, raw = built
    raw_rows = con.execute(f"SELECT count(*) FROM read_csv('{raw}/customers.csv')").fetchone()[0]
    stg = con.execute("SELECT count(*) FROM stg_customers").fetchone()[0]
    assert stg < raw_rows  # duplicates removed
    assert con.execute("SELECT typeof(unit_price) FROM stg_products LIMIT 1").fetchone()[0].startswith("DECIMAL")
    assert con.execute("SELECT count(*) FROM stg_customers WHERE email <> lower(email)").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM stg_customers WHERE country = ''").fetchone()[0] == 0


def test_star_schema_grain_matches_order_items(built):
    con, _ = built
    n_items = con.execute("SELECT count(*) FROM stg_order_items").fetchone()[0]
    assert con.execute("SELECT count(*) FROM fact_sales").fetchone()[0] == n_items


def test_quality_checks_pass_on_clean_data(built):
    con, raw = built
    results = run_checks(con, raw)
    assert results and all(r.passed for r in results)


def test_quality_fails_on_duplicate_key(built):
    con, raw = built
    con.execute("CREATE TEMP TABLE bak AS SELECT * FROM stg_customers")
    con.execute("INSERT INTO stg_customers SELECT * FROM stg_customers LIMIT 1")
    try:
        with pytest.raises(DataQualityError, match="unique:stg_customers"):
            run_checks(con, raw)
    finally:
        con.execute("CREATE OR REPLACE TABLE stg_customers AS SELECT * FROM bak")


def test_quality_fails_on_orphan_fact_row(built):
    con, raw = built
    con.execute("CREATE TEMP TABLE fbak AS SELECT * FROM fact_sales")
    con.execute("UPDATE fact_sales SET product_key = 999999 WHERE order_item_id = (SELECT min(order_item_id) FROM fact_sales)")
    try:
        with pytest.raises(DataQualityError, match="ref_integrity:fact_sales.product_key"):
            run_checks(con, raw)
    finally:
        con.execute("CREATE OR REPLACE TABLE fact_sales AS SELECT * FROM fbak")


def test_quality_fails_on_row_count_mismatch(built):
    con, raw = built
    con.execute("CREATE TEMP TABLE fbak2 AS SELECT * FROM fact_sales")
    con.execute("DELETE FROM fact_sales WHERE order_item_id = (SELECT min(order_item_id) FROM fact_sales)")
    try:
        with pytest.raises(DataQualityError, match="rowcount:stg_order_items -> fact_sales"):
            run_checks(con, raw)
    finally:
        con.execute("CREATE OR REPLACE TABLE fact_sales AS SELECT * FROM fbak2")


def test_quality_fails_on_null_key(built):
    con, raw = built
    con.execute("CREATE TEMP TABLE obak AS SELECT * FROM stg_orders")
    con.execute("UPDATE stg_orders SET order_date = NULL WHERE order_id = 1")
    try:
        with pytest.raises(DataQualityError, match="no_nulls:stg_orders.order_date"):
            run_checks(con, raw)
    finally:
        con.execute("CREATE OR REPLACE TABLE stg_orders AS SELECT * FROM obak")


def test_twelve_kpis_defined():
    assert len(parse_queries(ANALYTICS_SQL.read_text())) == 12


def test_analytics_queries_export(built, tmp_path):
    con, _ = built
    queries = parse_queries(ANALYTICS_SQL.read_text())
    assert set(queries) == set(EXPECTED_KPIS)
    counts = export_analytics(con, tmp_path)
    assert all(n > 0 for n in counts.values())
    assert counts["top_products"] == 10
    first = con.execute("SELECT min(retention_pct), max(retention_pct) FROM read_csv(?) WHERE months_since_first = 0",
                        [str(tmp_path / "customer_cohort_retention.csv")]).fetchone()
    assert first == (100.0, 100.0)  # every cohort is 100% retained in month 0


def test_full_pipeline_end_to_end(tmp_path):
    counts = run(tmp_path / "raw", tmp_path / "w.duckdb", tmp_path / "out")
    assert counts["monthly_revenue"] > 0
    assert (tmp_path / "out" / "average_order_value.csv").exists()


def test_dashboard_html_is_self_contained(tmp_path):
    from src.ecommerce.dashboard import build_dashboard
    run(tmp_path / "raw", tmp_path / "w.duckdb", tmp_path / "out")
    html = build_dashboard(tmp_path / "out", tmp_path / "dash" / "index.html").read_text()
    assert "__DATA__" not in html and "const D=" in html
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")  # no external resources


def test_excel_workbook_has_formulas_and_native_charts(tmp_path):
    import zipfile
    from src.ecommerce.excel import build_workbook
    run(tmp_path / "raw", tmp_path / "w.duckdb", tmp_path / "out")
    path = build_workbook(tmp_path / "out", tmp_path / "k.xlsx")
    z = zipfile.ZipFile(path)
    names = z.namelist()
    assert sum(n.startswith("xl/charts/chart") for n in names) >= 6
    assert any("SUM(Monthly!B2" in z.read(n).decode() for n in names if n.startswith("xl/worksheets/sheet1"))


@pytest.mark.skipif(not __import__("os").environ.get("PG_DSN"), reason="needs a PostgreSQL server (make pg-up; set PG_DSN)")
def test_postgres_load_reconciles_with_duckdb(built):
    from src.ecommerce.postgres import load_star_schema, reconcile
    con, _ = built
    counts = load_star_schema(con)
    assert counts["fact_sales"] == con.execute("SELECT count(*) FROM fact_sales").fetchone()[0]
    assert any("monthly revenue" in c for c in reconcile(con))


def test_powerbi_export_and_expected_values(built, tmp_path):
    import csv
    from src.ecommerce.powerbi import export_powerbi
    con, _ = built
    rows = export_powerbi(con, tmp_path / "pbi")
    assert rows["fact_sales"] == con.execute("SELECT count(*) FROM fact_sales").fetchone()[0]
    exp = {r["measure"]: float(r["expected_value"]) for r in csv.DictReader((tmp_path / "pbi" / "expected_values.csv").open())}
    revenue = con.execute("SELECT sum(net_amount) FROM fact_sales WHERE order_status = 'completed'").fetchone()[0]
    assert abs(exp["Revenue"] - float(revenue)) < 0.01
    assert exp["Revenue (calendar 2023)"] + exp["Revenue (calendar 2024)"] == pytest.approx(exp["Revenue"], abs=0.01)
    # every expected measure must be defined in measures.dax
    from pathlib import Path
    dax = (Path(__file__).resolve().parents[1] / "powerbi" / "measures.dax").read_text()
    for name in ["Revenue", "Gross Profit", "Gross Margin %", "Orders", "AOV", "Customers", "Repeat Rate %", "Cancel Rate %", "Discount %"]:
        assert f"\n{name} =" in dax or dax.startswith(f"{name} =")
