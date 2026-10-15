"""
Tidy the hub files into one weekly table:
disease x location x week, with MMWR week, respiratory season and rate per 100,000.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import RAW_DIR, SEASON_START_WEEK

VOLUNTARY_START, VOLUNTARY_END = date(2024, 5, 1), date(2024, 11, 2)

log = logging.getLogger(__name__)


def mmwr_week_start(year: int, week: int) -> date:
    """Sunday that starts MMWR week `week` of `year` (week 1 is the Sun-Sat week containing Jan 4)."""
    jan4 = date(year, 1, 4)
    week1 = jan4 - timedelta(days=(jan4.weekday() + 1) % 7)
    return week1 + timedelta(weeks=week - 1)


def mmwr(week_end: date) -> tuple[int, int]:
    """(MMWR year, MMWR week) for a week ending on Saturday."""
    year = (week_end - timedelta(days=3)).year  # the Wednesday decides which year the week belongs to
    start = week_end - timedelta(days=6)
    return year, (start - mmwr_week_start(year, 1)).days // 7 + 1


def season_of(week_end: date) -> tuple[str, int]:
    """Respiratory season label ('2024-25') and week of season (1 = MMWR week 40)."""
    y, w = mmwr(week_end)
    start_year = y if w >= SEASON_START_WEEK else y - 1
    season_start = mmwr_week_start(start_year, SEASON_START_WEEK)
    return f"{start_year}-{(start_year + 1) % 100:02d}", (week_end - timedelta(days=6) - season_start).days // 7 + 1


def load_locations(raw_dir: Path) -> pd.DataFrame:
    loc = pd.read_csv(raw_dir / "locations.csv", dtype={"location": str})
    return loc[["location", "abbreviation", "location_name", "population"]]


def tidy(raw_dir: Path = RAW_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    locs = load_locations(raw_dir)
    flu = pd.read_csv(raw_dir / "flu.csv", dtype={"location": str}).rename(columns={"date": "week_end"})
    covid = pd.read_csv(raw_dir / "covid.csv", dtype={"location": str}).rename(columns={"target_end_date": "week_end"})
    frames = []
    for disease, df in (("flu", flu), ("covid", covid)):
        d = df[["week_end", "location", "value"]].copy()
        d["disease"] = disease
        frames.append(d)
    w = pd.concat(frames, ignore_index=True)
    w["week_end"] = pd.to_datetime(w["week_end"]).dt.date
    w["value"] = pd.to_numeric(w["value"], errors="coerce")

    issues = []
    bad_day = pd.to_datetime(w.week_end).dt.dayofweek != 5
    issues.append(("week does not end on a Saturday", int(bad_day.sum())))
    neg = w.value < 0
    issues.append(("negative admissions", int(neg.sum())))
    dup = w.duplicated(["disease", "location", "week_end"], keep="last")
    issues.append(("duplicate disease/location/week", int(dup.sum())))
    unknown = ~w.location.isin(locs.location)
    issues.append(("unknown location code", int(unknown.sum())))
    w = w[~(bad_day | neg | dup | unknown)]
    issues.append(("missing value (kept as NULL, not imputed)", int(w.value.isna().sum())))

    w = w.merge(locs, on="location", how="left")
    w["rate_per_100k"] = w.value / w.population * 1e5
    mm = [mmwr(d) for d in w.week_end]
    ss = [season_of(d) for d in w.week_end]
    w["mmwr_year"], w["mmwr_week"] = [m[0] for m in mm], [m[1] for m in mm]
    w["season"], w["season_week"] = [s[0] for s in ss], [s[1] for s in ss]
    w["level"] = np.where(w.location == "US", "national", "state")
    # CMS reporting requirement lapsed May 1 - Oct 31 2024 (reporting was voluntary), so those weeks undercount
    w["reporting_mandatory"] = ~((w.week_end >= VOLUNTARY_START) & (w.week_end <= VOLUNTARY_END))
    w = w.rename(columns={"value": "admissions", "abbreviation": "state", "location_name": "name"})
    w = w.sort_values(["disease", "location", "week_end"]).reset_index(drop=True)
    for msg, n in issues:
        if n:
            log.warning("%s: %d rows", msg, n)
    log.info("tidy table: %d rows, %d locations, %s to %s", len(w), w.location.nunique(), w.week_end.min(), w.week_end.max())
    return w, pd.DataFrame(issues, columns=["check", "rows"])
