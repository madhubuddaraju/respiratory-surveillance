-- How many weeks before or after the national peak each state peaked (complete seasons only).
WITH nat AS (
    SELECT disease, season, peak_week_end AS national_peak
    FROM marts.season_summary
    WHERE location = 'US' AND complete_season
)
SELECT s.disease, s.season, s.state, s.name, s.peak_week_end, n.national_peak,
       date_diff('day', n.national_peak, s.peak_week_end) // 7 AS weeks_vs_national,
       s.peak_rate_per_100k
FROM marts.season_summary s
JOIN nat n USING (disease, season)
WHERE s.location <> 'US'
