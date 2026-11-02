"""Build a self-contained HTML dashboard (inline SVG, no network) from the exported KPI CSVs."""
import json
from pathlib import Path

import duckdb

TEMPLATE = Path(__file__).with_name("dashboard_template.html")


def _rows(con: duckdb.DuckDBPyConnection, csv: Path) -> list[dict]:
    cur = con.execute(f"SELECT * FROM read_csv('{csv}')")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, (float(v) if hasattr(v, "as_integer_ratio") and not isinstance(v, int) else v for v in r)))
            for r in cur.fetchall()]


def build_dashboard(output_dir: Path, html_path: Path) -> Path:
    con = duckdb.connect(":memory:")
    names = {"monthly": "monthly_revenue", "aov": "average_order_value", "top": "top_products",
             "category": "revenue_by_category", "country": "revenue_by_country",
             "cohort": "customer_cohort_retention", "repeat": "repeat_purchase_rate"}
    data = {k: _rows(con, output_dir / f"{v}.csv") for k, v in names.items()}
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(data, default=str)))
    return html_path
