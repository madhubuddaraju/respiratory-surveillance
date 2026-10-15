import numpy as np
import pandas as pd
import pytest

from surveil import forecast
from surveil.config import QUANTILES


def test_wis_of_perfect_point_forecast_is_zero():
    f = pd.DataFrame({f"q{q}": [10.0] for q in QUANTILES})
    assert forecast.wis(np.array([10.0]), f)[0] == pytest.approx(0)


def test_wis_penalises_misses_more_than_width():
    narrow_miss = pd.DataFrame({f"q{q}": [10.0 + (q - 0.5)] for q in QUANTILES})
    wide_hit = pd.DataFrame({f"q{q}": [20.0 + 40 * (q - 0.5)] for q in QUANTILES})
    y = np.array([20.0])
    assert forecast.wis(y, narrow_miss)[0] > forecast.wis(y, wide_hit)[0]


def test_frame_has_no_future_leakage(tidy):
    w, _ = tidy
    f = forecast.make_frame(w)
    row = f[(f.location == "US") & (f.disease == "flu")].iloc[20]
    nxt = f[(f.location == "US") & (f.disease == "flu")].iloc[21]
    assert row.target_h1 == pytest.approx(nxt.lag0 - row.lag0)
    assert row.lag1 == pytest.approx(f[(f.location == "US") & (f.disease == "flu")].iloc[19].lag0)


def test_fit_predict_produces_ordered_quantiles(tidy):
    w, _ = tidy
    f = forecast.make_frame(w)
    old = forecast.N_ROUNDS
    forecast.N_ROUNDS = 20
    try:
        models = forecast.fit(f)
    finally:
        forecast.N_ROUNDS = old
    rows = f[f.week_end == f.week_end.max()].dropna(subset=forecast.FEATURES[:-2])
    out = forecast.predict(models, rows)
    q = out[[f"q{x}" for x in QUANTILES]].to_numpy()
    assert (np.diff(q, axis=1) >= 0).all() and (q >= 0).all()
    assert set(out.horizon) == {1, 2, 3, 4}
