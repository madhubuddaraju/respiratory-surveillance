-- One row per disease x location x week, with smoothing and short-term change.
WITH smoothed AS (
    SELECT w.*,
           avg(rate_per_100k) OVER (PARTITION BY disease, location ORDER BY week_end ROWS 2 PRECEDING) AS rate_3wk_avg
    FROM staging.weekly w
)
SELECT
    s.*,
    rate_per_100k - lag(rate_per_100k) OVER ord              AS rate_change_1wk,
    admissions / nullif(lag(admissions) OVER ord, 0) - 1      AS pct_change_1wk,
    -- 2-week growth of the 3-week average smooths week-to-week reporting noise
    rate_3wk_avg / nullif(lag(rate_3wk_avg, 2) OVER ord, 0) - 1 AS growth_2wk
FROM smoothed s
WINDOW ord AS (PARTITION BY disease, location ORDER BY week_end)
