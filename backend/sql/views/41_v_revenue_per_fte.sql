-- v_revenue_per_fte
-- Grain: one row per (quarter, department) that carries revenue.
-- Serves: Revenue per FTE.
-- NL-queryable: yes.
--
-- The denominator is FTE, not headcount. Two half-time people are one FTE and should not
-- read as twice the productive capacity of one full-timer -- which is exactly what a
-- headcount denominator would claim.
--
-- Revenue is the left side of the join: a department with revenue but no snapshot rows
-- still appears, with a null FTE, so the caller can see the gap rather than lose the row.
CREATE OR REPLACE VIEW v_revenue_per_fte AS
WITH quarterly_fte AS (
    SELECT
        date_trunc('quarter', s.month_start)::date AS quarter_start,
        s.department_id,

        -- **Average** FTE across each month, not month-end FTE. The first version of this
        -- view filtered on `active_at_month_end` alone and never read
        -- `active_at_month_start` -- the exact average-versus-end-of-period substitution
        -- CLAUDE.md names as the most common bug in HR analytics, committed in the one view
        -- whose denominator is FTE rather than headcount.
        --
        -- The error flips sign with hiring direction: month-end FTE flatters a growing
        -- department and penalises a shrinking one, so Sales in a quarter it was shedding
        -- staff read 1.34% better than reality.
        SUM(
            (CASE WHEN s.active_at_month_start THEN s.fte ELSE 0 END)
            + (CASE WHEN s.active_at_month_end THEN s.fte ELSE 0 END)
        ) / 2.0                                         AS fte_months,
        COUNT(DISTINCT s.month_start)                   AS months_observed
    FROM fact_monthly_headcount_snapshot s
    GROUP BY quarter_start, s.department_id
)
SELECT
    r.quarter_start,
    r.department_id,
    r.revenue_amount,
    f.fte_months,
    f.months_observed,
    -- Average FTE across the quarter's months. Safe to divide here because both terms come
    -- from the same group; the caller re-derives it when aggregating across departments.
    f.fte_months / NULLIF(f.months_observed, 0) AS avg_fte
FROM fact_department_revenue r
LEFT JOIN quarterly_fte f
       ON f.quarter_start = r.quarter_start
      AND f.department_id = r.department_id;
