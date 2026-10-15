"""Paths, sources and surveillance parameters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
WAREHOUSE = ROOT / "data" / "surveillance.duckdb"
SQL_DIR = ROOT / "sql"
REPORTS_DIR = ROOT / "reports"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    description: str
    min_rows: int


HUB = "https://raw.githubusercontent.com"
SOURCES = {
    "flu": Source("flu", f"{HUB}/cdcepi/FluSight-forecast-hub/main/target-data/target-hospital-admissions.csv",
                  "Weekly confirmed influenza hospital admissions by state (CDC NHSN, via the FluSight hub)", 5_000),
    "covid": Source("covid", f"{HUB}/CDCgov/covid19-forecast-hub/main/target-data/covid-hospital-admissions.csv",
                    "Weekly confirmed COVID-19 hospital admissions by state (CDC NHSN, via the COVID-19 forecast hub)", 5_000),
    "locations": Source("locations", f"{HUB}/cdcepi/FluSight-forecast-hub/main/auxiliary-data/locations.csv",
                        "Location codes, names and population used by the CDC hubs", 50),
}

DISEASES = ("flu", "covid")
SEASON_START_WEEK = 40          # respiratory season = MMWR week 40 through week 39 of the next year
# Aberration detection (EARS C2-style): 7-week baseline separated from the current week by a 2-week guard band
BASELINE_WEEKS, GUARD_WEEKS, SIGNAL_Z = 7, 2, 3.0
FORECAST_HORIZONS = (1, 2, 3, 4)
QUANTILES = (0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975)
