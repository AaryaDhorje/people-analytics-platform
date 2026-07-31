-- v_manager_attrition_quarterly
-- Grain: one row per (quarter, manager). Exactly one row per manager per quarter.
-- Serves: Attrition by Manager.
-- NL-queryable: yes. This is the view behind "which managers have the worst attrition?"
--
-- The grain is deliberately NOT split by department or location, even though the other
-- retention views are. docs/METRICS.md reports this metric only for managers with at
-- least 8 reports, and **a threshold does not survive aggregation the way a sum does**.
-- Grained by (quarter, manager, department, location), M-114's 14 reports fanned into
-- three rows of 2-6 each and the manager failed the 8-report floor in every one of them
-- -- filtering the headline demo moment out of the chart built to surface it. Sums can be
-- re-added by the caller; a per-manager cutoff cannot be un-split.
--
-- `manager_id` comes from the snapshot, not dim_employee, so an exit is attributed to
-- whoever held the report *at the time* rather than to whoever inherited the team.
CREATE OR REPLACE VIEW v_manager_attrition_quarterly AS
WITH team AS (
    SELECT
        date_trunc('quarter', s.month_start)::date AS quarter_start,
        s.manager_id,

        COUNT(DISTINCT s.employee_id)              AS reports,
        SUM(s.terminated_in_month::int)            AS terminations,
        SUM(
            CASE
                WHEN s.terminated_in_month AND e.termination_type = 'voluntary' THEN 1
                ELSE 0
            END
        )                                          AS voluntary_terminations,

        -- Sum of each month's average headcount. Annualized rate is
        -- terminations * 12 / headcount_months, valid for any number of months.
        SUM((s.active_at_month_start::int + s.active_at_month_end::int) / 2.0)
                                                   AS headcount_months
    FROM fact_monthly_headcount_snapshot s
    JOIN dim_employee e ON e.employee_id = s.employee_id
    WHERE s.manager_id IS NOT NULL
    GROUP BY quarter_start, s.manager_id
),
manager_context AS (
    -- The manager's *own* as-of attributes, so a heatmap can group managers by team
    -- without splitting the team itself. MAX() picks one value where a manager changed
    -- department mid-quarter; managers are excluded from transfers in the generator, so
    -- in practice there is only ever one value to pick.
    SELECT
        date_trunc('quarter', m.month_start)::date AS quarter_start,
        m.employee_id                              AS manager_id,
        MAX(m.department_id)                       AS department_id,
        MAX(m.location_id)                         AS location_id,
        MAX(m.job_level_id)                        AS job_level_id
    FROM fact_monthly_headcount_snapshot m
    GROUP BY quarter_start, m.employee_id
)
SELECT
    t.quarter_start,
    t.manager_id,
    c.department_id,
    c.location_id,
    c.job_level_id,
    t.reports,
    t.terminations,
    t.voluntary_terminations,
    t.headcount_months
FROM team t
LEFT JOIN manager_context c
       ON c.quarter_start = t.quarter_start
      AND c.manager_id = t.manager_id;
