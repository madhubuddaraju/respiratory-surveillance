"""
Statistical aberration detection (EARS C2-style), the method public-health agencies use to flag
unusual increases in syndromic and laboratory surveillance.

For each week t, the baseline is the mean and standard deviation of weeks t-9 .. t-3: seven weeks
separated from the current week by a two-week guard band, so a building outbreak does not inflate
its own baseline. A signal fires when the current value exceeds the baseline by SIGNAL_Z deviations
and is at least a minimum absolute count (to avoid alerts on tiny numbers).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BASELINE_WEEKS, GUARD_WEEKS, SIGNAL_Z

MIN_ADMISSIONS = 20


def c2_scores(series: pd.Series, baseline: int = BASELINE_WEEKS, guard: int = GUARD_WEEKS) -> pd.DataFrame:
    shifted = series.shift(guard + 1)
    mean = shifted.rolling(baseline, min_periods=baseline).mean()
    sd = shifted.rolling(baseline, min_periods=baseline).std()
    # floor the deviation so flat, near-zero baselines do not create huge z-scores
    sd = np.maximum(sd, np.maximum(0.2 * mean, 1.0))
    return pd.DataFrame({"baseline_mean": mean, "baseline_sd": sd, "z": (series - mean) / sd})


def detect(weekly: pd.DataFrame, z: float = SIGNAL_Z) -> pd.DataFrame:
    out = []
    for (_disease, _loc), g in weekly.sort_values("week_end").groupby(["disease", "location"], sort=False):
        s = c2_scores(g["admissions"].astype(float).reset_index(drop=True))
        s.index = g.index
        out.append(g[["disease", "location", "state", "name", "week_end", "admissions", "rate_per_100k"]].join(s))
    res = pd.concat(out)
    res["signal"] = (res.z >= z) & (res.admissions >= MIN_ADMISSIONS)
    return res.sort_values(["disease", "location", "week_end"]).reset_index(drop=True)


def first_signal_per_season(alerts: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """Earliest signal of each season per state, and how many weeks it came before that state's peak."""
    a = alerts.merge(weekly[["disease", "location", "week_end", "season"]], on=["disease", "location", "week_end"])
    first = a[a.signal].groupby(["disease", "location", "season"]).week_end.min().rename("first_signal").reset_index()
    peaks = (weekly.dropna(subset=["admissions"]).sort_values("admissions")
             .groupby(["disease", "location", "season"]).tail(1)[["disease", "location", "season", "week_end"]]
             .rename(columns={"week_end": "peak_week_end"}))
    m = first.merge(peaks, on=["disease", "location", "season"])
    m["lead_weeks"] = (pd.to_datetime(m.peak_week_end) - pd.to_datetime(m.first_signal)).dt.days // 7
    return m
