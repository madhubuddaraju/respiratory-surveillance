"""Data quality and freshness checks on the warehouse. `error` checks fail the run; `warn` checks are logged."""

from __future__ import annotations

import logging

import duckdb
import pandas as pd

log = logging.getLogger(__name__)

CHECKS = [
    ("one row per disease/location/week", "error",
     "SELECT count(*) FROM (SELECT 1 FROM marts.weekly GROUP BY disease, location, week_end HAVING count(*) > 1)"),
    ("rates are non-negative", "error", "SELECT count(*) FROM marts.weekly WHERE rate_per_100k < 0"),
    ("every location has a population", "error", "SELECT count(*) FROM marts.weekly WHERE population IS NULL"),
    ("states sum to the national total within 5% (latest 8 weeks)", "error", """
        WITH s AS (SELECT disease, week_end, sum(admissions) FILTER (WHERE level = 'state') st,
                          max(admissions) FILTER (WHERE level = 'national') nat
                   FROM marts.weekly GROUP BY ALL),
             r AS (SELECT *, row_number() OVER (PARTITION BY disease ORDER BY week_end DESC) rn FROM s)
        SELECT count(*) FROM r WHERE rn <= 8 AND abs(st / nat - 1) > 0.05"""),
    ("latest week covers at least 50 states/territories", "warn", """
        SELECT count(*) FROM (SELECT disease, count(*) n FROM marts.current_status WHERE level = 'state'
                              AND admissions IS NOT NULL GROUP BY disease) WHERE n < 50"""),
    ("data is no more than 21 days old", "warn",
     "SELECT count(*) FROM (SELECT disease, max(week_end) m FROM marts.weekly GROUP BY disease) "
     "WHERE date_diff('day', m, current_date) > 21"),
    ("forecast quantiles do not cross", "error",
     'SELECT count(*) FROM marts.forecasts WHERE "q0.025" > "q0.5" OR "q0.5" > "q0.975"'),
]


class QualityError(RuntimeError):
    pass


def run_checks(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    rows = []
    for name, sev, sql in CHECKS:
        n = int(con.execute(sql).fetchone()[0] or 0)
        rows.append({"check": name, "severity": sev, "failing": n, "passed": n == 0})
        log.log(logging.INFO if n == 0 else logging.WARNING, "[%s] %s", "PASS" if n == 0 else "FAIL", name)
    df = pd.DataFrame(rows)
    bad = df[~df.passed & (df.severity == "error")]
    if not bad.empty:
        raise QualityError("; ".join(bad.check))
    return df
