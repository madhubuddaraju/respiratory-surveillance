import numpy as np
import pandas as pd

from surveil import alerts


def test_c2_flags_a_spike_but_not_noise():
    rng = np.random.default_rng(0)
    s = pd.Series(100 + rng.normal(0, 5, 30))
    s.iloc[25] = 200
    z = alerts.c2_scores(s)["z"]
    assert z.iloc[25] > 3
    assert (z.iloc[10:25].abs() < 3).all()


def test_guard_band_keeps_outbreak_out_of_baseline():
    s = pd.Series([50.0] * 12 + [80, 120, 180])
    base = alerts.c2_scores(s)["baseline_mean"]
    # the week-14 baseline (t-9..t-3) contains only pre-outbreak weeks
    assert base.iloc[14] == 50


def test_detect_requires_minimum_count(tidy):
    w, _ = tidy
    a = alerts.detect(w)
    assert (a[a.signal].admissions >= alerts.MIN_ADMISSIONS).all()
