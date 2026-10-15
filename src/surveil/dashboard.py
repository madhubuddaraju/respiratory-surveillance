"""
Build the self-contained HTML dashboard (docs/index.html, served by GitHub Pages) from the warehouse.

    python -m surveil.dashboard
"""

from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from .config import QUANTILES, ROOT, WAREHOUSE

GEO = Path(__file__).with_name("geo") / "us_states.json"

log = logging.getLogger(__name__)
TEMPLATE = ROOT / "dashboard" / "template.html"
OUT = ROOT / "docs" / "index.html"


def _num(x, nd: int = 3):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


def build_data(warehouse: Path = WAREHOUSE) -> dict:
    con = duckdb.connect(str(warehouse), read_only=True)
    q = lambda sql: con.execute(sql).df()  # noqa: E731
    w = q("SELECT disease, location, week_end, admissions, rate_per_100k, season, season_week FROM marts.weekly")
    status = q("SELECT * FROM marts.current_status")
    al = q("SELECT * FROM marts.alerts")
    fc = q("SELECT * FROM marts.forecasts")
    bt = q("SELECT * FROM marts.backtest_summary WHERE method = 'model'")
    sources = q("SELECT source, url FROM audit.sources")
    dq = q("SELECT * FROM audit.dq_results")
    con.close()
    w["week_end"] = pd.to_datetime(w.week_end).dt.strftime("%Y-%m-%d")
    al["week_end"] = pd.to_datetime(al.week_end).dt.strftime("%Y-%m-%d")

    data = {"generated": datetime.now(UTC).strftime("%b %d, %Y"), "geo": json.loads(GEO.read_text()),
            "dq_passed": int(dq.passed.sum()), "dq_total": len(dq),
            "sources": sources.to_dict("records"), "diseases": {}, "weeks": {}, "series": {}, "status": {},
            "forecasts": {}, "signals": {}, "overlay": {}, "skill": {}}
    for d in ("flu", "covid"):
        wd = w[w.disease == d]
        weeks = sorted(wd.week_end.unique())
        data["weeks"][d] = weeks
        piv = wd.pivot(index="week_end", columns="location", values="admissions").reindex(weeks)
        data["series"][d] = {loc: [_num(v, 0) for v in piv[loc]] for loc in piv.columns}

        latest_alert = al[(al.disease == d) & (al.week_end == al[al.disease == d].week_end.max())].set_index("location")
        st = {}
        for r in status[status.disease == d].itertuples():
            a = latest_alert.loc[r.location] if r.location in latest_alert.index else None
            st[r.location] = {"location": r.location, "state": r.state, "name": r.name, "level": r.level,
                              "admissions": _num(r.admissions, 0), "rate": _num(r.rate_per_100k), "pct_change_1wk": _num(r.pct_change_1wk),
                              "activity_level": r.activity_level, "trend": r.trend, "growth": _num(r.growth_2wk),
                              "signal": bool(a.signal) if a is not None else False,
                              "z": _num(a.z, 2) if a is not None else None,
                              "baseline": _num(a.baseline_mean, 0) if a is not None else None}
        data["status"][d] = st

        f = fc[fc.disease == d]
        data["forecasts"][d] = {
            loc: [{"h": int(r["horizon"]), "t": pd.Timestamp(r["target_week_end"]).strftime("%Y-%m-%d"),
                   "q": [_num(r[f"q{qq}"], 0) for qq in QUANTILES]} for r in g.sort_values("horizon").to_dict("records")]
            for loc, g in f.groupby("location")}

        recent = al[(al.disease == d) & al.signal & (al.week_end >= weeks[-52])]
        data["signals"][d] = recent.groupby("location").week_end.apply(list).to_dict()

        ov = {}
        for loc, g in wd.groupby("location"):
            seasons = {}
            cur = g.season.max()
            for s, gs in g.groupby("season"):
                if len(gs) >= 30 or s == cur:
                    seasons[s] = [[int(a), _num(b)] for a, b in zip(gs.season_week, gs.rate_per_100k, strict=True) if b == b]
            ov[loc] = seasons
        data["overlay"][d] = ov

        b = bt[bt.disease == d]
        data["skill"][d] = {int(r.horizon): {"rel": _num(r.relative_wis)} for r in b.itertuples()}
        data["skill"][d].update({"cov50": _num(b.cov50.mean()), "cov80": _num(b.cov80.mean())})

        us = wd[wd.location == "US"].dropna(subset=["admissions"])
        cur = us.iloc[-1]
        streak = 0
        for v in us.admissions.diff().iloc[::-1]:
            if v > 0:
                streak += 1
            else:
                break
        same = us[(us.season_week == cur.season_week) & (us.season != cur.season)]
        prev, n_prev = same.admissions.max(), same.season.nunique()
        states = [s for s in st.values() if s["level"] == "state"]
        n_sig = sum(s["signal"] for s in states)
        name = "Flu" if d == "flu" else "COVID-19"
        if streak >= 3:
            lede = f"{name} hospital admissions have risen {streak} weeks in a row, to {cur.admissions:,.0f} this week"
            if prev == prev and cur.admissions > prev:
                lede += (f", {cur.admissions / prev:.1f}x the highest level at this point of the season in any of the "
                         f"previous {n_prev} seasons")
        else:
            chg = st["US"]["pct_change_1wk"] or 0
            lede = f"{name} hospital admissions {'rose' if chg > 0 else 'fell'} {abs(chg) * 100:.0f}% to {cur.admissions:,.0f} this week"
        lede += f". {n_sig} of {len(states)} states and territories show a statistically unusual increase."
        data["diseases"][d] = {"latest": weeks[-1], "lede": lede}
    return data


def build(out: Path = OUT) -> Path:
    data = build_data()
    html = TEMPLATE.read_text().replace("__DATA__", json.dumps(data, separators=(",", ":")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    log.info("wrote %s (%.0f KB)", out.relative_to(ROOT), out.stat().st_size / 1024)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build()
