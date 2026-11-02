"""Publish the DuckDB star schema to PostgreSQL and reconcile it against DuckDB.

Connection string comes from PG_DSN (see docker-compose.yml for the local default).
"""
import os

import duckdb
import psycopg

from src.ecommerce.quality import DataQualityError

DEFAULT_DSN = "postgresql://warehouse:warehouse@localhost:5433/warehouse"
SCHEMA = "warehouse"
TABLES = ["dim_customer", "dim_product", "dim_date", "dim_payment_method", "fact_sales"]  # dimensions first
PRIMARY_KEYS = {"dim_customer": "customer_key", "dim_product": "product_key", "dim_date": "date_key",
                "dim_payment_method": "payment_method_key", "fact_sales": "order_item_id"}
FOREIGN_KEYS = [("customer_key", "dim_customer"), ("product_key", "dim_product"),
                ("date_key", "dim_date"), ("payment_method_key", "dim_payment_method")]
TYPE_MAP = {"INTEGER": "integer", "BIGINT": "bigint", "VARCHAR": "text", "DATE": "date", "BOOLEAN": "boolean", "DOUBLE": "double precision"}


def _pg_type(duck_type: str) -> str:
    if duck_type.startswith("DECIMAL"):
        return "numeric" + duck_type[len("DECIMAL"):]
    return TYPE_MAP[duck_type]


def load_star_schema(duck: duckdb.DuckDBPyConnection, dsn: str | None = None) -> dict[str, int]:
    """Recreate the `warehouse` schema in PostgreSQL with keys and constraints, then COPY each table in."""
    dsn = dsn or os.environ.get("PG_DSN", DEFAULT_DSN)
    counts = {}
    with psycopg.connect(dsn, autocommit=False) as pg, pg.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE; CREATE SCHEMA {SCHEMA}")
        for t in TABLES:
            cols = duck.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{t}' ORDER BY ordinal_position").fetchall()
            ddl = ", ".join(f"{c} {_pg_type(d)} NOT NULL" for c, d in cols)
            fks = "".join(f", FOREIGN KEY ({k}) REFERENCES {SCHEMA}.{d}({k})" for k, d in FOREIGN_KEYS if t == "fact_sales")
            cur.execute(f"CREATE TABLE {SCHEMA}.{t} ({ddl}, PRIMARY KEY ({PRIMARY_KEYS[t]}){fks})")
            with cur.copy(f"COPY {SCHEMA}.{t} FROM STDIN") as cp:
                for row in duck.execute(f"SELECT * FROM {t}").fetchall():
                    cp.write_row(row)
            counts[t] = len(duck.execute(f"SELECT 1 FROM {t}").fetchall())
        cur.execute(f"CREATE INDEX ON {SCHEMA}.fact_sales (date_key); CREATE INDEX ON {SCHEMA}.fact_sales (order_status)")
        pg.commit()
    return counts


def reconcile(duck: duckdb.DuckDBPyConnection, dsn: str | None = None) -> list[str]:
    """Compare row counts, total revenue and monthly revenue between DuckDB and PostgreSQL. Raises on any difference."""
    dsn = dsn or os.environ.get("PG_DSN", DEFAULT_DSN)
    problems, checks = [], []
    with psycopg.connect(dsn) as pg, pg.cursor() as cur:
        for t in TABLES:
            cur.execute(f"SELECT count(*) FROM {SCHEMA}.{t}")
            a, b = duck.execute(f"SELECT count(*) FROM {t}").fetchone()[0], cur.fetchone()[0]
            checks.append(f"rowcount {t}: duckdb={a} postgres={b}")
            if a != b:
                problems.append(checks[-1])
        cur.execute(f"SELECT sum(net_amount), sum(gross_amount), sum(cost_amount) FROM {SCHEMA}.fact_sales")
        pgt = [float(x) for x in cur.fetchone()]
        dkt = [float(x) for x in duck.execute("SELECT sum(net_amount), sum(gross_amount), sum(cost_amount) FROM fact_sales").fetchone()]
        checks.append(f"fact totals (net, gross, cost): duckdb={dkt} postgres={pgt}")
        if any(abs(x - y) > 0.005 for x, y in zip(pgt, dkt)):
            problems.append(checks[-1])
        q = ("SELECT d.year_month, sum(f.net_amount) FROM {s}fact_sales f JOIN {s}dim_date d USING (date_key) "
             "WHERE f.order_status = 'completed' GROUP BY 1 ORDER BY 1")
        cur.execute(q.format(s=SCHEMA + "."))
        pg_m = {k: float(v) for k, v in cur.fetchall()}
        dk_m = {k: float(v) for k, v in duck.execute(q.format(s="")).fetchall()}
        bad = [m for m in dk_m if abs(dk_m[m] - pg_m.get(m, -1)) > 0.005] + [m for m in pg_m if m not in dk_m]
        checks.append(f"monthly revenue: {len(dk_m)} months compared, {len(bad)} differ")
        if bad:
            problems.append(checks[-1])
    if problems:
        raise DataQualityError("PostgreSQL reconciliation failed:\n  " + "\n  ".join(problems))
    return checks
