-- v_timesheet_weekly
-- Grain: one row per (employee, week) -- a projection, not an aggregation.
-- Serves: Utilization, Overtime Rate, Output per Head.
-- NL-queryable: yes.
--
-- This view stays at row grain deliberately, because **overtime cannot be recovered from
-- an aggregate**. docs/METRICS.md defines it as `hours_over_40 / total_hours`, and the
-- 40-hour threshold applies per week: someone working 30 hours one week and 50 the next
-- has 10 hours of overtime, but their 80-hour fortnight aggregated first shows none.
-- The same reasoning puts the 1.5 cap inside v_goal_attainment. Thresholds that apply
-- per-row must be applied before any summing, which is the one exception to this layer's
-- "views aggregate, Python divides" rule.
--
-- `fte` is joined from the snapshot so Output per Head has a real denominator. A
-- part-timer producing half the tickets of a full-timer is not less productive.
CREATE OR REPLACE VIEW v_timesheet_weekly AS
SELECT
    t.week_start,
    date_trunc('month', t.week_start)::date   AS month_start,
    date_trunc('quarter', t.week_start)::date AS quarter_start,

    t.department_id,
    t.employee_id,
    s.location_id,
    s.job_level_id,
    s.manager_id,
    COALESCE(s.fte, 1.000)                    AS fte,

    t.billable_hours,
    t.non_billable_hours,
    t.available_hours,
    t.billable_hours + t.non_billable_hours   AS total_hours,

    -- Per-week, before any aggregation. See the note above.
    GREATEST(t.billable_hours + t.non_billable_hours - 40, 0) AS overtime_hours,

    t.output_units,
    t.output_type::text                       AS output_type
FROM fact_timesheet_week t
LEFT JOIN fact_monthly_headcount_snapshot s
       ON s.employee_id = t.employee_id
      AND s.month_start = date_trunc('month', t.week_start)::date;
