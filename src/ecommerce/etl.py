"""Load raw CSVs into DuckDB staging, then build the star schema. Transformations live in sql/."""
from pathlib import Path

import duckdb

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def run_sql_file(con: duckdb.DuckDBPyConnection, name: str, **params: str) -> None:
    sql = (SQL_DIR / name).read_text()
    for key, value in params.items():
        sql = sql.replace("{" + key + "}", value)
    con.execute(sql)


def build_staging(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> None:
    run_sql_file(con, "01_staging.sql", raw_dir=str(raw_dir))


def build_star_schema(con: duckdb.DuckDBPyConnection) -> None:
    run_sql_file(con, "02_star_schema.sql")
