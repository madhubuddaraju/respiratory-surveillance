from datetime import date

import pytest

from surveil.transform import mmwr, season_of


@pytest.mark.parametrize("d, expected", [
    (date(2024, 1, 6), (2024, 1)),
    (date(2025, 2, 8), (2025, 6)),
    (date(2024, 10, 5), (2024, 40)),
    (date(2021, 1, 2), (2020, 53)),   # 2020 has 53 MMWR weeks
    (date(2026, 1, 3), (2025, 53)),   # and so does 2025
    (date(2023, 1, 7), (2023, 1)),
])
def test_mmwr_weeks(d, expected):
    assert mmwr(d) == expected


def test_seasons_start_at_week_40():
    assert season_of(date(2024, 10, 5)) == ("2024-25", 1)
    assert season_of(date(2025, 9, 27)) == ("2024-25", 52)
    assert season_of(date(2026, 10, 10))[0] == "2026-27"


def test_tidy_table(tidy):
    w, _ = tidy
    assert set(w.disease) == {"flu", "covid"}
    assert not w.duplicated(["disease", "location", "week_end"]).any()
    assert (w.rate_per_100k.dropna() >= 0).all()
    us = w[(w.location == "US") & (w.disease == "flu")].iloc[-1]
    assert us.rate_per_100k == pytest.approx(us.admissions / us.population * 1e5)
    assert w.loc[w.week_end == date(2024, 8, 3), "reporting_mandatory"].eq(False).all()
    assert w.loc[w.week_end == date(2025, 1, 4), "reporting_mandatory"].all()


def test_marts(warehouse):
    s = warehouse.execute("SELECT * FROM marts.season_summary WHERE location = 'US' AND disease = 'flu' "
                          "AND season = '2024-25'").df().iloc[0]
    assert s.complete_season and str(s.peak_week_end)[:10] == "2025-02-08"
    cur = warehouse.execute("SELECT * FROM marts.current_status").df()
    assert set(cur.activity_level) <= {"Low", "Moderate", "High", "Very high"}
    assert set(cur.trend) <= {"Increasing", "Decreasing", "Stable"}
