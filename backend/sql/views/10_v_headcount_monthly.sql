-- v_headcount_monthly
-- Grain: one row per (month, department, location, job level, manager).
-- Serves: Headcount, Attrition Rate, Voluntary vs Involuntary.
-- NL-queryable: yes.
--
-- This is the most important view in the layer. `avg_headcount` is the denominator
-- every rate metric divides by, computed as the mean of the two activity endpoints
-- the snapshot stores. Exposing it as a column means no downstream metric can reach
-- for end-of-period headcount by accident -- docs/METRICS.md and CLAUDE.md both name
-- that substitution as the most common bug in HR analytics.
--
-- Numerators and denominators are separate columns and are never divided here.
-- Callers filter, aggregate, then divide, so the denominator stays auditable.
CREATE OR REPLACE VIEW v_headcount_monthly AS
SELECT
    s.month_start,
    date_trunc('quarter', s.month_start)::date              AS quarter_start,
    s.department_id,
    s.location_id,
    s.job_level_id,
    s.manager_id,

    COUNT(*)                                                AS employee_months,
    SUM(s.active_at_month_start::int)                        AS active_start,
    SUM(s.active_at_month_end::int)                          AS active_end,

    -- The average-headcount denominator. Linear, so summing it across groups in the
    -- caller is valid.
    (SUM(s.active_at_month_start::int) + SUM(s.active_at_month_end::int)) / 2.0
                                                            AS avg_headcount,

    SUM(s.hired_in_month::int)                               AS hires,
    SUM(s.terminated_in_month::int)                          AS terminations,
    SUM(
        CASE
            WHEN s.terminated_in_month AND e.termination_type = 'voluntary' THEN 1
            ELSE 0
        END
    )                                                        AS voluntary_terminations,
    SUM(
        CASE
            WHEN s.terminated_in_month AND e.termination_type = 'involuntary' THEN 1
            ELSE 0
        END
    )                                                        AS involuntary_terminations,

    SUM(s.fte) FILTER (WHERE s.active_at_month_end)          AS total_fte
FROM fact_monthly_headcount_snapshot s
JOIN dim_employee e ON e.employee_id = s.employee_id
GROUP BY
    s.month_start,
    s.department_id,
    s.location_id,
    s.job_level_id,
    s.manager_id;
