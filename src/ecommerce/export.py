"""Run every named query in sql/analytics.sql and write each result to CSV."""
import re
from pathlib import Path

import duckdb

ANALYTICS_SQL = Path(__file__).resolve().parents[2] / "sql" / "analytics.sql"


def parse_queries(text: str) -> dict[str, str]:
    parts = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def export_analytics(con: duckdb.DuckDBPyConnection, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, sql in parse_queries(ANALYTICS_SQL.read_text()).items():
        path = out_dir / f"{name}.csv"
        con.execute(f"COPY ({sql.rstrip(';')}) TO '{path}' (HEADER, DELIMITER ',')")
        counts[name] = con.execute(f"SELECT count(*) FROM read_csv('{path}')").fetchone()[0]
    return counts
