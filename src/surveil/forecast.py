"""
Probabilistic 1-4 week ahead forecasts of hospital admissions for every state.

Model: one global LightGBM quantile regressor per horizon and quantile, trained on all states and
both diseases at once (pooling lets small states borrow strength from large ones). It predicts the
change in log rate from the current week, from recent lags, local and national momentum, and
seasonality.

Evaluation follows the CDC FluSight protocol: rolling-origin backtest, weighted interval score
(WIS) on counts, relative to a baseline that carries the last value forward with empirical
uncertainty, plus interval coverage.
"""

from __future__ import annotations

import logging

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import FORECAST_HORIZONS, QUANTILES

log = logging.getLogger(__name__)

LAGS = 5
PARAMS = {"learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 40, "feature_fraction": 0.8,
          "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0, "verbose": -1, "num_threads": 0, "seed": 7}
N_ROUNDS = 250
FEATURES = [*[f"lag{i}" for i in range(LAGS)], "d1", "d2", "nat_lag0", "nat_d1", "sin_week", "cos_week",
            "is_flu", "location_code"]


def make_frame(weekly: pd.DataFrame) -> pd.DataFrame:
    """Feature rows (one per disease x location x week) plus future targets for every horizon."""
    w = weekly[["disease", "location", "week_end", "season_week", "admissions", "population"]].copy()
    w = w.sort_values(["disease", "location", "week_end"])
    w["y"] = np.log1p(w.admissions / w.population * 1e5)
    g = w.groupby(["disease", "location"], sort=False)["y"]
    for i in range(LAGS):
        w[f"lag{i}"] = g.shift(i)
    w["d1"] = w.lag0 - w.lag1
    w["d2"] = w.lag1 - w.lag2
    for h in FORECAST_HORIZONS:
        w[f"target_h{h}"] = g.shift(-h) - w.lag0
        w[f"target_week_h{h}"] = w.groupby(["disease", "location"], sort=False)["week_end"].shift(-h)
    nat = w[w.location == "US"][["disease", "week_end", "lag0", "d1"]].rename(columns={"lag0": "nat_lag0", "d1": "nat_d1"})
    w = w.merge(nat, on=["disease", "week_end"], how="left")
    angle = 2 * np.pi * w.season_week / 52.18
    w["sin_week"], w["cos_week"] = np.sin(angle), np.cos(angle)
    w["is_flu"] = (w.disease == "flu").astype(int)
    w["location_code"] = pd.Categorical(w.location).codes
    return w.reset_index(drop=True)


def fit(train: pd.DataFrame) -> dict:
    models = {}
    for h in FORECAST_HORIZONS:
        d = train.dropna(subset=[*FEATURES[:-2], f"target_h{h}"])
        ds = lgb.Dataset(d[FEATURES], d[f"target_h{h}"], categorical_feature=["location_code"], free_raw_data=False)
        for q in QUANTILES:
            models[(h, q)] = lgb.train({**PARAMS, "objective": "quantile", "alpha": q}, ds, num_boost_round=N_ROUNDS)
    return models


def predict(models: dict, rows: pd.DataFrame) -> pd.DataFrame:
    """Quantile forecasts of admissions (counts) for each row and horizon."""
    out = []
    for h in FORECAST_HORIZONS:
        qs = np.column_stack([models[(h, q)].predict(rows[FEATURES]) for q in QUANTILES])
        qs = np.sort(qs, axis=1)  # enforce non-crossing quantiles
        counts = np.expm1(rows.lag0.to_numpy()[:, None] + qs).clip(min=0) * rows.population.to_numpy()[:, None] / 1e5
        frame = rows[["disease", "location", "week_end"]].copy()
        frame["horizon"] = h
        frame["target_week_end"] = pd.to_datetime(rows.week_end) + pd.Timedelta(weeks=h)
        for j, q in enumerate(QUANTILES):
            frame[f"q{q}"] = counts[:, j]
        out.append(frame)
    return pd.concat(out, ignore_index=True)


def baseline(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """Flat-line baseline: last observed value with quantiles of historical h-week changes (symmetrised)."""
    out = []
    for h in FORECAST_HORIZONS:
        ch = train[f"target_h{h}"].dropna().to_numpy()
        ch = np.concatenate([ch, -ch])
        qs = np.quantile(ch, QUANTILES)
        counts = np.expm1(rows.lag0.to_numpy()[:, None] + qs[None, :]).clip(min=0) * rows.population.to_numpy()[:, None] / 1e5
        frame = rows[["disease", "location", "week_end"]].copy()
        frame["horizon"] = h
        frame["target_week_end"] = pd.to_datetime(rows.week_end) + pd.Timedelta(weeks=h)
        for j, q in enumerate(QUANTILES):
            frame[f"q{q}"] = counts[:, j]
        out.append(frame)
    return pd.concat(out, ignore_index=True)


def wis(y: np.ndarray, f: pd.DataFrame) -> np.ndarray:
    """Weighted interval score (Bracher et al., 2021) using the median and 50/80/95% intervals."""
    score = 0.5 * np.abs(y - f["q0.5"].to_numpy())
    pairs = [(0.25, 0.75), (0.1, 0.9), (0.025, 0.975)]
    for lo_q, hi_q in pairs:
        alpha = 2 * lo_q
        lo, hi = f[f"q{lo_q}"].to_numpy(), f[f"q{hi_q}"].to_numpy()
        interval = (hi - lo) + (2 / alpha) * (lo - y) * (y < lo) + (2 / alpha) * (y - hi) * (y > hi)
        score += alpha / 2 * interval
    return score / (len(pairs) + 0.5)


def score(fc: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    t = truth[["disease", "location", "week_end", "admissions"]].rename(
        columns={"week_end": "target_week_end", "admissions": "observed"})
    t["target_week_end"] = pd.to_datetime(t.target_week_end)
    m = fc.merge(t, on=["disease", "location", "target_week_end"], how="inner").dropna(subset=["observed"])
    y = m.observed.to_numpy()
    m["wis"] = wis(y, m)
    m["ae"] = np.abs(y - m["q0.5"])
    m["cov50"] = (y >= m["q0.25"]) & (y <= m["q0.75"])
    m["cov80"] = (y >= m["q0.1"]) & (y <= m["q0.9"])
    m["cov95"] = (y >= m["q0.025"]) & (y <= m["q0.975"])
    return m


def backtest(frame: pd.DataFrame, weeks: int = 52, refit_every: int = 4) -> pd.DataFrame:
    """Rolling-origin evaluation over the last `weeks` reference weeks. Training never sees the future."""
    ref_weeks = sorted(frame.week_end.unique())[-weeks - max(FORECAST_HORIZONS):-max(FORECAST_HORIZONS)]
    results, models = [], None
    for i, ref in enumerate(ref_weeks):
        if i % refit_every == 0:
            # a training row is usable only if its target week is already observed at the reference date
            train = frame[frame.week_end <= ref].copy()
            for h in FORECAST_HORIZONS:
                train.loc[pd.to_datetime(train[f"target_week_h{h}"]) > pd.Timestamp(ref), f"target_h{h}"] = np.nan
            models = fit(train)
            log.info("backtest refit at %s (%d/%d)", ref, i + 1, len(ref_weeks))
        rows = frame[(frame.week_end == ref)].dropna(subset=FEATURES[:-2])
        for name, fc in (("model", predict(models, rows)), ("baseline", baseline(train, rows))):
            results.append(fc.assign(method=name, reference_week=ref))
    return pd.concat(results, ignore_index=True)


def summarise(scored: pd.DataFrame) -> pd.DataFrame:
    g = scored.groupby(["disease", "horizon", "method"]).agg(
        wis=("wis", "mean"), mae=("ae", "mean"), cov50=("cov50", "mean"), cov80=("cov80", "mean"),
        cov95=("cov95", "mean"), n=("wis", "size")).reset_index()
    base = g[g.method == "baseline"][["disease", "horizon", "wis"]].rename(columns={"wis": "baseline_wis"})
    g = g.merge(base, on=["disease", "horizon"])
    g["relative_wis"] = g.wis / g.baseline_wis
    return g.drop(columns="baseline_wis")
