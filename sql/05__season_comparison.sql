-- National weekly rate aligned by week of season, for overlaying seasons.
SELECT disease, season, season_week, week_end, rate_per_100k, admissions
FROM marts.weekly
WHERE location = 'US'
ORDER BY disease, season, season_week
