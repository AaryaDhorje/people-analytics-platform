-- v_tenure_band_monthly
-- Grain: one row per (month, department, location, job level, tenure band).
-- Serves: Tenure Distribution.
-- NL-queryable: yes.
--
-- Bands are the ones fixed in docs/METRICS.md: <6m, 6-12m, 1-2y, 2-5y, 5y+.
-- `band_order` exists so charts sort chronologically rather than alphabetically --
-- without it "1-2y" sorts before "6-12m".
CREATE OR REPLACE VIEW v_tenure_band_monthly AS
SELECT
    s.month_start,
    date_trunc('quarter', s.month_start)::date AS quarter_start,
    s.department_id,
    s.location_id,
    s.job_level_id,
    CASE
        WHEN s.tenure_months < 6  THEN '<6m'
        WHEN s.tenure_months < 12 THEN '6-12m'
        WHEN s.tenure_months < 24 THEN '1-2y'
        WHEN s.tenure_months < 60 THEN '2-5y'
        ELSE '5y+'
    END                                        AS tenure_band,
    CASE
        WHEN s.tenure_months < 6  THEN 1
        WHEN s.tenure_months < 12 THEN 2
        WHEN s.tenure_months < 24 THEN 3
        WHEN s.tenure_months < 60 THEN 4
        ELSE 5
    END                                        AS band_order,

    -- Month-end headcount, matching the Headcount metric's own definition.
    COUNT(*) FILTER (WHERE s.active_at_month_end) AS headcount
FROM fact_monthly_headcount_snapshot s
GROUP BY
    s.month_start,
    s.department_id,
    s.location_id,
    s.job_level_id,
    tenure_band,
    band_order;
