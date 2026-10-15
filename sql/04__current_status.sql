-- Latest reported week per disease x location, with activity level and trend.
WITH latest AS (
    SELECT disease, max(week_end) AS week_end FROM marts.weekly WHERE admissions IS NOT NULL GROUP BY disease
),
cuts AS (
    -- activity thresholds from each disease's full state-week history
    SELECT disease,
           quantile_cont(rate_per_100k, 0.40) AS q40,
           quantile_cont(rate_per_100k, 0.70) AS q70,
           quantile_cont(rate_per_100k, 0.90) AS q90
    FROM marts.weekly WHERE level = 'state' AND rate_per_100k IS NOT NULL
    GROUP BY disease
)
SELECT w.disease, w.location, w.state, w.name, w.level, w.week_end, w.season, w.season_week,
       w.admissions, w.rate_per_100k, w.rate_3wk_avg, w.pct_change_1wk, w.growth_2wk,
       CASE WHEN w.rate_3wk_avg >= c.q90 THEN 'Very high'
            WHEN w.rate_3wk_avg >= c.q70 THEN 'High'
            WHEN w.rate_3wk_avg >= c.q40 THEN 'Moderate'
            ELSE 'Low' END                                                     AS activity_level,
       CASE WHEN w.growth_2wk >= 0.10 THEN 'Increasing'
            WHEN w.growth_2wk <= -0.10 THEN 'Decreasing'
            ELSE 'Stable' END                                                  AS trend
FROM marts.weekly w
JOIN latest l USING (disease, week_end)
JOIN cuts c USING (disease)
