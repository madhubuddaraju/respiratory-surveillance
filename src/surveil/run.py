"""
Weekly surveillance pipeline.

    python -m surveil              # ingest -> warehouse -> alerts -> forecasts (+ backtest) -> checks
    python -m surveil --refresh    # force re-download
    python -m surveil --no-backtest
"""

from __future__ import annotations

import argparse
import json
import logging
import time

import pandas as pd

from . import alerts, forecast, ingest, load, quality, transform
from .config import RAW_DIR

log = logging.getLogger("surveil")


def run(refresh: bool = False, backtest: bool = True, skip_ingest: bool = False, warehouse=None, raw_dir=RAW_DIR) -> dict:
    t0 = time.time()
    manifest = json.loads((raw_dir / "manifest.json").read_text()) if skip_ingest else ingest.ingest(raw_dir, force=refresh)
    weekly, issues = transform.tidy(raw_dir)
    con = load.connect(warehouse)
    load.write(con, "staging.weekly", weekly)
    load.write(con, "audit.transform_issues", issues)
    load.write(con, "audit.sources", pd.DataFrame([{"source": k, **v} for k, v in manifest.items()]))
    load.build_marts(con)

    w = con.execute("SELECT * FROM marts.weekly").df()
    a = alerts.detect(w)
    load.write(con, "marts.alerts", a)
    load.write(con, "marts.signal_lead_time", alerts.first_signal_per_season(a, w))

    frame = forecast.make_frame(w)
    if backtest:
        bt = forecast.backtest(frame)
        scored = forecast.score(bt, w)
        load.write(con, "marts.backtest_scores", scored)
        load.write(con, "marts.backtest_summary", forecast.summarise(scored))
    latest = frame.groupby("disease").week_end.transform("max") == frame.week_end
    models = forecast.fit(frame)
    rows = frame[latest].dropna(subset=forecast.FEATURES[:-2])
    load.write(con, "marts.forecasts", forecast.predict(models, rows))
    dq = quality.run_checks(con)
    load.write(con, "audit.dq_results", dq)
    con.close()
    log.info("pipeline finished in %.0fs", time.time() - t0)
    return {"rows": len(weekly), "latest_week": str(w.week_end.max()), "checks_passed": int(dq.passed.sum()),
            "checks_total": len(dq)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--no-backtest", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    try:
        log.info("summary: %s", run(refresh=a.refresh, backtest=not a.no_backtest))
    except (quality.QualityError, ingest.IngestError) as exc:
        log.error(str(exc))
        return 1
    return 0
