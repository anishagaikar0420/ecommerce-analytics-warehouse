"""End-to-end pipeline: generate raw -> staging -> star schema -> quality checks -> analytics CSVs."""
import os
import sys
import time
from pathlib import Path

import duckdb

from src.ecommerce.dashboard import build_dashboard
from src.ecommerce.etl import build_staging, build_star_schema
from src.ecommerce.excel import build_workbook
from src.ecommerce.export import export_analytics
from src.ecommerce.generate_data import generate
from src.ecommerce.quality import DataQualityError, run_checks


def run(raw_dir: Path = Path("data/raw"), db_path: Path = Path("data/warehouse.duckdb"),
        out_dir: Path = Path("output"), regenerate: bool = True) -> dict:
    if regenerate:
        print("Generating synthetic raw data:", generate(raw_dir))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        t = time.time()
        build_staging(con, raw_dir)
        build_star_schema(con)
        print(f"Built staging + star schema in {time.time() - t:.2f}s")
        results = run_checks(con, raw_dir)
        print(f"Data quality: {len(results)}/{len(results)} checks passed")
        if os.environ.get("PG_DSN"):
            from src.ecommerce.postgres import load_star_schema, reconcile
            print("PostgreSQL load:", load_star_schema(con))
            for line in reconcile(con):
                print("  ok", line)
        counts = export_analytics(con, out_dir)
        for name, n in counts.items():
            print(f"  exported output/{name}.csv ({n} rows)")
        print(f"  built {build_workbook(out_dir, Path('excel/ecommerce_kpis.xlsx'))}")
        print(f"  built {build_dashboard(out_dir, Path('dashboard/index.html'))}")
        for table in ["fact_sales", "dim_customer", "dim_product", "dim_date", "dim_payment_method"]:
            print(f"  {table}: {con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]} rows")
    return counts


if __name__ == "__main__":
    try:
        run()
    except DataQualityError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
