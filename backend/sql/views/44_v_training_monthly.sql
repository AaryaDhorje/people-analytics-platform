-- v_training_monthly
-- Grain: one row per (month, department, location, level).
-- Serves: Training Hours per head, and training completion rate.
-- NL-queryable: yes.
--
-- Monthly grain, even though docs/METRICS.md reports this per department per year. A
-- yearly view would have to divide headcount by "months this group was observed", and that
-- divisor is wrong for any group that does not span the whole year. In this warehouse a
-- Support L2 in London exists for three months of 2025 and then leaves: dividing their
-- three headcount-months by their own three observed months yields an average of 1.0,
-- claiming a full-year presence for someone who was there for a quarter.
--
-- Keeping it monthly makes the denominator the caller's problem, which is the only place
-- that knows how many months the requested period actually spans.
--
-- Headcount is the left side of the join so a team that did no training still reports a
-- real denominator and a zero, rather than disappearing from the result.
CREATE OR REPLACE VIEW v_training_monthly AS
WITH assignments AS (
    SELECT
        s.month_start,
        s.department_id,
        s.location_id,
        s.job_level_id,
        SUM(tr.hours)              AS training_hours,
        COUNT(*)                   AS assigned,
        COUNT(tr.completed_on)     AS completed
    FROM fact_training tr
    JOIN fact_monthly_headcount_snapshot s
      ON s.employee_id = tr.employee_id
     AND s.month_start = date_trunc('month', tr.assigned_on)::date
    GROUP BY s.month_start, s.department_id, s.location_id, s.job_level_id
),
headcount AS (
    SELECT
        s.month_start,
        s.department_id,
        s.location_id,
        s.job_level_id,
        SUM((s.active_at_month_start::int + s.active_at_month_end::int) / 2.0)
            AS avg_headcount
    FROM fact_monthly_headcount_snapshot s
    GROUP BY s.month_start, s.department_id, s.location_id, s.job_level_id
)
SELECT
    h.month_start,
    EXTRACT(YEAR FROM h.month_start)::int       AS year,
    date_trunc('quarter', h.month_start)::date  AS quarter_start,
    h.department_id,
    h.location_id,
    h.job_level_id,

    COALESCE(a.training_hours, 0)               AS training_hours,
    COALESCE(a.assigned, 0)                     AS assigned,
    COALESCE(a.completed, 0)                    AS completed,
    h.avg_headcount
FROM headcount h
LEFT JOIN assignments a
       ON a.month_start = h.month_start
      AND a.department_id = h.department_id
      AND a.location_id = h.location_id
      AND a.job_level_id = h.job_level_id;
