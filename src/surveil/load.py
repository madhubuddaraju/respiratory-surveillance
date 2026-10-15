"""DuckDB warehouse: staging table plus SQL marts built in filename order."""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd

from .config import SQL_DIR, WAREHOUSE

log = logging.getLogger(__name__)


def connect(path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    path = str(path or WAREHOUSE)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(path)
    for s in ("staging", "marts", "audit"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
    return con


def write(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    con.register("_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _df")
    con.unregister("_df")


def build_marts(con: duckdb.DuckDBPyConnection) -> list[str]:
    built = []
    for p in sorted(SQL_DIR.glob("*.sql")):
        name = p.stem.split("__", 1)[1]
        con.execute(f"CREATE OR REPLACE TABLE marts.{name} AS {p.read_text()}")
        log.info("built marts.%-18s %7d rows", name, con.execute(f"SELECT count(*) FROM marts.{name}").fetchone()[0])
        built.append(f"marts.{name}")
    return built
