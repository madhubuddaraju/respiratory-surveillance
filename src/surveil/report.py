"""
Weekly surveillance bulletin: figures plus reports/bulletin.md, all computed from the warehouse.

    python -m surveil.report
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import REPORTS_DIR, WAREHOUSE  # noqa: E402
from .tiles import TILES  # noqa: E402

log = logging.getLogger(__name__)
FIG = REPORTS_DIR / "figures"
FLU, COVID = "#2a78d6", "#eb6834"
COLOR = {"flu": FLU, "covid": COVID}
LABEL = {"flu": "Influenza", "covid": "COVID-19"}
INK, INK2, GRID, MUTED = "#0b0b0b", "#52514e", "#e6e5e1", "#b9b8b3"
LEVEL_COLORS = {"Low": "#dbe8f8", "Moderate": "#9cc1ec", "High": "#4a90de", "Very high": "#184f99"}
plt.rcParams.update({
    "figure.dpi": 130, "savefig.bbox": "tight", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlelocation": "left", "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID,
    "xtick.color": INK2, "ytick.color": INK2, "legend.frameon": False,
})


def _save(fig, name: str) -> Path:
    fig.savefig(FIG / name)
    plt.close(fig)
    return FIG / name


def fig_national(w: pd.DataFrame) -> Path:
    us = w[w.location == "US"]
    fig, ax = plt.subplots(figsize=(10, 4))
    for d in ("covid", "flu"):
        s = us[us.disease == d]
        ax.plot(pd.to_datetime(s.week_end), s.rate_per_100k, color=COLOR[d], lw=2, label=LABEL[d])
    ax.axvspan(pd.Timestamp("2024-05-01"), pd.Timestamp("2024-11-02"), color=GRID, alpha=0.6, lw=0)
    ax.text(pd.Timestamp("2024-05-08"), ax.get_ylim()[1] * 0.92, "voluntary\nreporting", fontsize=8, color=INK2, va="top")
    ax.set(title="Weekly hospital admissions per 100,000, United States", ylabel="Admissions per 100k")
    ax.legend(loc="upper right")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="x", visible=False)
    return _save(fig, "national_trends.png")


def fig_season_overlay(w: pd.DataFrame, disease: str) -> Path:
    s = w[(w.location == "US") & (w.disease == disease)]
    seasons = sorted(s.season.unique())
    current = seasons[-1]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    past = [x for x in seasons[:-1] if len(s[s.season == x]) >= 40]
    shades = np.linspace(0.35, 0.8, len(past))
    for x, a in zip(past, shades, strict=True):
        d = s[s.season == x]
        ax.plot(d.season_week, d.rate_per_100k, color=INK2, alpha=a, lw=1.2)
        peak = d.loc[d.rate_per_100k.idxmax()]
        ax.text(peak.season_week, peak.rate_per_100k, f" {x}", fontsize=8, color=INK2, va="bottom")
    d = s[s.season == current]
    ax.plot(d.season_week, d.rate_per_100k, color=COLOR[disease], lw=3, label=f"{current} (current)")
    ax.scatter(d.season_week.iloc[-1:], d.rate_per_100k.iloc[-1:], color=COLOR[disease], s=40, zorder=3)
    ticks = [1, 14, 27, 40, 52]
    ax.set_xticks(ticks, ["Oct", "Jan", "Apr", "Jul", "Sep"])
    ax.set(title=f"{LABEL[disease]}: this season vs past seasons (US)", ylabel="Admissions per 100k", xlim=(1, 53))
    ax.legend(loc="upper right")
    return _save(fig, f"season_overlay_{disease}.png")


def fig_tile_map(status: pd.DataFrame, disease: str) -> Path:
    s = status[(status.disease == disease) & (status.level == "state")].set_index("state")
    fig, ax = plt.subplots(figsize=(9, 5.6))
    arrow = {"Increasing": "▲", "Decreasing": "▼", "Stable": "●"}
    for st, (r, c) in TILES.items():
        lvl = s.activity_level.get(st, None)
        col = LEVEL_COLORS.get(lvl, "#f2f2f0")
        ax.add_patch(plt.Rectangle((c, -r), 0.92, 0.92, color=col, lw=0))
        txt = "white" if lvl in ("High", "Very high") else INK
        ax.text(c + 0.46, -r + 0.58, st, ha="center", va="center", fontsize=9, fontweight="bold", color=txt)
        if st in s.index:
            ax.text(c + 0.46, -r + 0.26, arrow.get(s.trend[st], ""), ha="center", va="center", fontsize=7, color=txt)
    ax.set_xlim(-0.2, 12.2)
    ax.set_ylim(-7.3, 1.1)
    ax.set_aspect("equal")
    ax.axis("off")
    handles = [plt.Rectangle((0, 0), 1, 1, color=v) for v in LEVEL_COLORS.values()]
    ax.legend(handles, LEVEL_COLORS.keys(), loc="lower center", bbox_to_anchor=(0.5, -0.08), ncol=4, fontsize=9,
              title="Activity (3-week average vs history)   ▲ increasing  ● stable  ▼ decreasing", title_fontsize=8.5)
    week = pd.to_datetime(s.week_end.iloc[0]).strftime("%b %d, %Y")
    ax.set_title(f"{LABEL[disease]} activity by state, week ending {week}", loc="left")
    return _save(fig, f"activity_map_{disease}.png")


def fig_forecast(w: pd.DataFrame, fc: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, d in zip(axes, ("flu", "covid"), strict=True):
        hist = w[(w.location == "US") & (w.disease == d)].tail(20)
        f = fc[(fc.location == "US") & (fc.disease == d)].sort_values("horizon")
        x0 = pd.to_datetime(hist.week_end.iloc[-1])
        y0 = hist.admissions.iloc[-1]
        xs = [x0, *pd.to_datetime(f.target_week_end)]
        for lo, hi, a in (("q0.025", "q0.975", 0.15), ("q0.1", "q0.9", 0.25), ("q0.25", "q0.75", 0.4)):
            ax.fill_between(xs, [y0, *f[lo]], [y0, *f[hi]], color=COLOR[d], alpha=a, lw=0)
        ax.plot(xs, [y0, *f["q0.5"]], color=COLOR[d], lw=2, ls=(0, (4, 2)))
        ax.plot(pd.to_datetime(hist.week_end), hist.admissions, color=INK, lw=2, marker="o", ms=3)
        ax.set(title=f"{LABEL[d]}: 4-week forecast (US)", ylabel="Weekly admissions")
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.grid(axis="x", visible=False)
    fig.text(0.01, -0.03, "Bands: 50%, 80% and 95% prediction intervals. Dashed: median forecast.", fontsize=8.5, color=INK2)
    return _save(fig, "forecast_us.png")


def fig_backtest(summary: pd.DataFrame) -> Path:
    m = summary[summary.method == "model"]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    width = 0.38
    for i, d in enumerate(("flu", "covid")):
        s = m[m.disease == d].sort_values("horizon")
        xs = s.horizon + (i - 0.5) * width
        ax.bar(xs, s.relative_wis, width=width * 0.95, color=COLOR[d], label=LABEL[d])
        for x, v in zip(xs, s.relative_wis, strict=True):
            ax.text(x, v + 0.02, f"{v:.2f}", ha="center", fontsize=8, color=INK2)
    ax.axhline(1, color=INK, lw=1, ls=(0, (4, 2)))
    ax.text(4.45, 1.02, "baseline", ha="right", fontsize=8.5, color=INK)
    ax.set(title="Forecast error relative to baseline (lower is better)", xlabel="Weeks ahead",
           ylabel="Relative WIS", ylim=(0, 1.2), xticks=[1, 2, 3, 4])
    ax.legend(loc="upper left")
    ax.grid(axis="x", visible=False)
    return _save(fig, "forecast_skill.png")


def fig_peak_timing(pt: pd.DataFrame) -> Path:
    f = pt[pt.disease == "flu"].groupby("state").weeks_vs_national.median().sort_values()
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.bar(f.index, f.values, color=[FLU if v < 0 else ("#9cc1ec" if v == 0 else COVID) for v in f.values], width=0.75)
    ax.axhline(0, color=INK, lw=0.8)
    ax.set(title="Flu peak timing: median weeks before (−) or after (+) the national peak, by state",
           ylabel="Weeks vs national")
    ax.tick_params(axis="x", labelsize=7.5, length=0)
    ax.grid(axis="x", visible=False)
    return _save(fig, "peak_timing_flu.png")


def build(warehouse: Path = WAREHOUSE) -> str:
    FIG.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse), read_only=True)
    q = lambda sql: con.execute(sql).df()  # noqa: E731
    w = q("SELECT * FROM marts.weekly ORDER BY disease, location, week_end")
    status = q("SELECT * FROM marts.current_status")
    seasons = q("SELECT * FROM marts.season_summary")
    fc = q("SELECT * FROM marts.forecasts")
    bt = q("SELECT * FROM marts.backtest_summary")
    pt = q("SELECT * FROM marts.peak_timing")
    al = q("SELECT a.* FROM marts.alerts a JOIN (SELECT disease, max(week_end) m FROM marts.alerts GROUP BY disease) l "
           "ON a.disease = l.disease AND a.week_end = l.m")
    lead = q("SELECT l.* FROM marts.signal_lead_time l JOIN marts.season_summary s USING (disease, location, season) "
             "WHERE s.complete_season")
    sources = q("SELECT source, url, fetched_at FROM audit.sources")
    dq = q("SELECT * FROM audit.dq_results")
    con.close()

    figs = [fig_national(w), fig_season_overlay(w, "flu"), fig_season_overlay(w, "covid"),
            fig_tile_map(status, "flu"), fig_tile_map(status, "covid"), fig_forecast(w, fc),
            fig_backtest(bt), fig_peak_timing(pt)]

    lines = []
    for d in ("flu", "covid"):
        us = w[(w.location == "US") & (w.disease == d)].dropna(subset=["admissions"])
        cur = us.iloc[-1]
        streak = 0
        for v in us.admissions.diff().iloc[::-1]:
            if v > 0:
                streak += 1
            else:
                break
        same_week = us[(us.season_week == cur.season_week) & (us.season != cur.season)]
        prev_max = same_week.admissions.max() if not same_week.empty else np.nan
        st = status[(status.disease == d) & (status.level == "state")]
        sig = al[(al.disease == d) & al.signal & (al.location != "US")]
        f4 = fc[(fc.disease == d) & (fc.location == "US") & (fc.horizon == 4)].iloc[0]
        sev = seasons[(seasons.disease == d) & (seasons.location == "US") & seasons.complete_season]
        worst = sev.loc[sev.cumulative_rate_per_100k.idxmax()]
        lines.append({"d": d, "cur": cur, "streak": streak, "prev_max": prev_max, "st": st, "sig": sig, "f4": f4,
                      "worst": worst, "n_seasons": len(sev)})

    def section(x: dict) -> str:
        cur, st = x["cur"], x["st"]
        lv = st.activity_level.value_counts()
        rising = st[st.trend == "Increasing"].state.tolist()
        vs = (f" That is **{cur.admissions / x['prev_max']:.1f}x** the highest count at this point of any of the previous "
              f"{x['n_seasons']} seasons." if x["prev_max"] == x["prev_max"] and cur.admissions > x["prev_max"] else "")
        return f"""### {LABEL[x['d']]}
- **{cur.admissions:,.0f} admissions** nationally in the week ending {pd.to_datetime(cur.week_end):%B %d}
  ({cur.rate_per_100k:.2f} per 100k), {cur.pct_change_1wk * 100:+.0f}% from the previous week;
  {'up for ' + str(x['streak']) + ' consecutive weeks' if x['streak'] >= 2 else 'not in a sustained rise'}.{vs}
- Activity: {', '.join(f"{lv.get(k, 0)} {k.lower()}" for k in ('Very high', 'High', 'Moderate', 'Low'))} (of {len(st)} states/territories).
  Trend increasing in **{len(rising)}**.
- **{len(x['sig'])} jurisdictions** have a statistical signal this week (EARS C2, z ≥ 3)
  {('- ' + ', '.join(sorted(x['sig'].state))) if len(x['sig']) else ''}.
- 4-week forecast for the week ending {pd.to_datetime(x['f4'].target_week_end):%B %d}: **{x['f4']['q0.5']:,.0f}**
  admissions (80% interval {x['f4']['q0.1']:,.0f} - {x['f4']['q0.9']:,.0f}).
- Most severe complete season on record here: **{x['worst'].season}** (peak {x['worst'].peak_rate_per_100k:.1f} per 100k,
  week ending {pd.to_datetime(x['worst'].peak_week_end):%b %d, %Y}).
"""

    m = bt[bt.method == "model"]
    flu_lead = lead[lead.disease == "flu"]
    flu_pt = pt[pt.disease == "flu"].groupby("state").weeks_vs_national.median()
    md = f"""# US respiratory surveillance bulletin

_Week ending {pd.to_datetime(w.week_end.max()):%B %d, %Y}. Generated {datetime.now(UTC):%Y-%m-%d} by
`python -m surveil.report` from CDC NHSN hospital admissions. {int(dq.passed.sum())}/{len(dq)} data checks passed._

## This week
{''.join(section(x) for x in lines)}
![Flu activity map](figures/activity_map_flu.png)

## Context
![National trends](figures/national_trends.png)

| Flu | COVID-19 |
|---|---|
| ![](figures/season_overlay_flu.png) | ![](figures/season_overlay_covid.png) |

- **Early warning works.** In complete seasons, the first flu signal in a state came a median of
  **{flu_lead.lead_weeks.median():.0f} weeks before that state's peak** ({(flu_lead.lead_weeks > 0).mean():.0%} of signals
  came before the peak; n = {len(flu_lead)} state-seasons).
- **Flu tends to peak first in** {', '.join(flu_pt.sort_values().head(4).index)} and **last in**
  {', '.join(flu_pt.sort_values().tail(4).index[::-1])} (median weeks vs the national peak).

![Peak timing](figures/peak_timing_flu.png)

## Forecasts
![Forecast](figures/forecast_us.png)

Rolling-origin backtest over the last 52 weeks, all states (weighted interval score relative to a flat-line baseline;
below 1 is better):

| Disease | 1 wk | 2 wk | 3 wk | 4 wk | 80% interval coverage |
|---|---|---|---|---|---|
""" + "\n".join(
        f"| {LABEL[d]} | " + " | ".join(f"{v:.2f}" for v in m[m.disease == d].sort_values("horizon").relative_wis) +
        f" | {m[m.disease == d].cov80.mean():.0%} |" for d in ("flu", "covid")) + """

![Forecast skill](figures/forecast_skill.png)

## Data notes
- Source: CDC National Healthcare Safety Network (NHSN) weekly confirmed admissions, as published to the CDC
  FluSight and COVID-19 forecast hubs. Rates use the hubs' population file.
- Hospital reporting was **voluntary from May 1 to Oct 31, 2024**, so counts in that window are incomplete
  (shaded in the national chart).
- Activity levels compare each state's 3-week average with the distribution of all state-weeks for that disease
  (Low < 40th percentile, Moderate < 70th, High < 90th, Very high ≥ 90th).

| Source | Fetched (UTC) |
|---|---|
""" + "\n".join(f"| [{r.source}]({r.url}) | {str(r.fetched_at)[:16].replace('T', ' ')} |" for r in sources.itertuples()) + "\n"
    (REPORTS_DIR / "bulletin.md").write_text(md)
    log.info("wrote reports/bulletin.md and %d figures", len(figs))
    return md


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build()
