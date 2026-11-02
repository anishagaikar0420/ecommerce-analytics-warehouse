"""Data quality checks. Any failure raises DataQualityError, which fails the pipeline."""
from dataclasses import dataclass
from pathlib import Path

import duckdb


class DataQualityError(Exception):
    pass


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _scalar(con, sql: str):
    return con.execute(sql).fetchone()[0]


def _null_checks(con) -> list[CheckResult]:
    required = {
        "stg_customers": ["customer_id", "email", "signup_date"],
        "stg_products": ["product_id", "category", "unit_price"],
        "stg_orders": ["order_id", "customer_id", "order_date", "status"],
        "stg_order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price"],
        "stg_payments": ["payment_id", "order_id", "amount"],
        "fact_sales": ["customer_key", "product_key", "payment_method_key", "date_key", "net_amount"],
    }
    out = []
    for table, cols in required.items():
        for col in cols:
            n = _scalar(con, f"SELECT count(*) FROM {table} WHERE {col} IS NULL")
            out.append(CheckResult(f"no_nulls:{table}.{col}", n == 0, f"{n} nulls"))
    return out


def _duplicate_checks(con) -> list[CheckResult]:
    keys = {
        "stg_customers": "customer_id", "stg_products": "product_id", "stg_orders": "order_id",
        "stg_order_items": "order_item_id", "stg_payments": "payment_id",
        "dim_customer": "customer_key", "dim_product": "product_key", "dim_date": "date_key", "dim_payment_method": "payment_method_key",
        "fact_sales": "order_item_id",
    }
    out = []
    for table, key in keys.items():
        n = _scalar(con, f"SELECT count(*) - count(DISTINCT {key}) FROM {table}")
        out.append(CheckResult(f"unique:{table}.{key}", n == 0, f"{n} duplicate keys"))
    return out


def _integrity_checks(con) -> list[CheckResult]:
    fks = [
        ("stg_orders.customer_id -> stg_customers", "stg_orders", "customer_id", "stg_customers", "customer_id"),
        ("stg_order_items.order_id -> stg_orders", "stg_order_items", "order_id", "stg_orders", "order_id"),
        ("stg_order_items.product_id -> stg_products", "stg_order_items", "product_id", "stg_products", "product_id"),
        ("stg_payments.order_id -> stg_orders", "stg_payments", "order_id", "stg_orders", "order_id"),
        ("fact_sales.customer_key -> dim_customer", "fact_sales", "customer_key", "dim_customer", "customer_key"),
        ("fact_sales.product_key -> dim_product", "fact_sales", "product_key", "dim_product", "product_key"),
        ("fact_sales.payment_method_key -> dim_payment_method", "fact_sales", "payment_method_key", "dim_payment_method", "payment_method_key"),
        ("fact_sales.date_key -> dim_date", "fact_sales", "date_key", "dim_date", "date_key"),
    ]
    out = []
    for name, child, ccol, parent, pcol in fks:
        n = _scalar(con, f"SELECT count(*) FROM {child} c LEFT JOIN {parent} p ON c.{ccol} = p.{pcol} "
                         f"WHERE c.{ccol} IS NOT NULL AND p.{pcol} IS NULL")
        out.append(CheckResult(f"ref_integrity:{name}", n == 0, f"{n} orphans"))
    return out


def _reconciliation_checks(con, raw_dir: Path) -> list[CheckResult]:
    out = []
    # Every distinct business key in raw must survive to staging.
    for table, key, stg in [("customers", "customer_id", "stg_customers"), ("products", "product_id", "stg_products"),
                            ("orders", "order_id", "stg_orders"), ("order_items", "order_item_id", "stg_order_items"),
                            ("payments", "payment_id", "stg_payments")]:
        raw = _scalar(con, f"SELECT count(DISTINCT {key}) FROM read_csv('{raw_dir}/{table}.csv', all_varchar=true)")
        got = _scalar(con, f"SELECT count(*) FROM {stg}")
        out.append(CheckResult(f"rowcount:raw.{table} -> {stg}", raw == got, f"raw distinct={raw}, staging={got}"))
    stg_items = _scalar(con, "SELECT count(*) FROM stg_order_items")
    fact = _scalar(con, "SELECT count(*) FROM fact_sales")
    out.append(CheckResult("rowcount:stg_order_items -> fact_sales", stg_items == fact, f"staging={stg_items}, fact={fact}"))
    rev_stg = _scalar(con, "SELECT sum(round(quantity * unit_price * (1 - discount), 2)) FROM stg_order_items")
    rev_fact = _scalar(con, "SELECT round(sum(net_amount), 2) FROM fact_sales")
    out.append(CheckResult("revenue:stg_order_items -> fact_sales", abs(rev_stg - rev_fact) < 0.01,
                           f"staging={rev_stg}, fact={rev_fact}"))
    # Payments should match item revenue for every order that has a payment (1 cent per order tolerance).
    n = _scalar(con, """
        SELECT count(*) FROM stg_payments p
        JOIN (SELECT order_id, sum(net_amount) AS total FROM fact_sales GROUP BY 1) f USING (order_id)
        WHERE abs(p.amount - f.total) > 0.011""")
    out.append(CheckResult("payments_match_order_totals", n == 0, f"{n} orders with mismatched payment"))
    return out


def run_checks(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> list[CheckResult]:
    results = (_null_checks(con) + _duplicate_checks(con) + _integrity_checks(con)
               + _reconciliation_checks(con, Path(raw_dir)))
    failed = [r for r in results if not r.passed]
    if failed:
        lines = "\n".join(f"  FAIL {r.name}: {r.detail}" for r in failed)
        raise DataQualityError(f"{len(failed)} of {len(results)} data quality checks failed:\n{lines}")
    return results
