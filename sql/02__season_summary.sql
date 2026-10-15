-- Burden, peak and onset for every disease x location x respiratory season.
WITH s AS (
    SELECT disease, location, state, name, season,
           count(*)                                         AS weeks_reported,
           sum(admissions)                                  AS total_admissions,
           sum(rate_per_100k)                               AS cumulative_rate_per_100k,
           max(rate_per_100k)                               AS peak_rate_per_100k,
           arg_max(week_end, rate_per_100k)                 AS peak_week_end,
           arg_max(season_week, rate_per_100k)              AS peak_season_week,
           min(season_week)                                 AS first_week
    FROM marts.weekly
    WHERE admissions IS NOT NULL
    GROUP BY ALL
),
onset AS (
    -- onset: first week the 3-week average reaches 25% of that season's peak
    SELECT w.disease, w.location, w.season, min(w.week_end) AS onset_week_end
    FROM marts.weekly w
    JOIN s USING (disease, location, season)
    WHERE w.rate_3wk_avg >= 0.25 * s.peak_rate_per_100k
    GROUP BY ALL
)
SELECT s.*, o.onset_week_end,
       s.first_week = 1 AND s.weeks_reported >= 52              AS complete_season,
       rank() OVER (PARTITION BY s.disease, s.location ORDER BY s.cumulative_rate_per_100k DESC) AS severity_rank
FROM s
LEFT JOIN onset o USING (disease, location, season)
ORDER BY disease, location, season
