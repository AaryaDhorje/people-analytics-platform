-- v_absenteeism_monthly
-- Grain: one row per (month, department, location, level).
-- Serves: Absenteeism Rate.
-- NL-queryable: yes.
--
-- docs/METRICS.md: `unplanned_absence_days / available_workdays`. The denominator is the
-- part worth getting right: available workdays is *headcount x workdays in the month*, not
-- calendar days and not workdays alone. A team of 4 and a team of 400 have the same number
-- of workdays in February and wildly different capacity to absorb absence.
--
-- Workdays come from dim_date, which is why `is_workday` exists on the spine at all --
-- weekends and holidays are not available capacity, and deriving them from a date function
-- here would silently ignore the holiday list.
--
-- Only `is_unplanned` days count in the numerator. Booked leave is not absenteeism; it is
-- a plan.
CREATE OR REPLACE VIEW v_absenteeism_monthly AS
WITH workdays AS (
    SELECT month_start, COUNT(*) AS workdays
    FROM dim_date
    WHERE is_workday
    GROUP BY month_start
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
),
absence AS (
    -- `s.month_start` is selected rather than `date_trunc(a.absence_date)` even though the
    -- join makes them equal. Aliasing the date_trunc to `month_start` created an ambiguity:
    -- PostgreSQL resolves a bare GROUP BY name to the *input* column, so it grouped by
    -- s.month_start and then rejected the ungrouped a.absence_date. Selecting the joined
    -- column removes the ambiguity entirely.
    SELECT
        s.month_start,
        s.department_id,
        s.location_id,
        s.job_level_id,
        SUM(a.days) FILTER (WHERE a.is_unplanned)     AS unplanned_days,
        SUM(a.days) FILTER (WHERE NOT a.is_unplanned) AS planned_days,
        SUM(a.days)                                   AS total_absence_days
    FROM fact_absence a
    JOIN fact_monthly_headcount_snapshot s
      ON s.employee_id = a.employee_id
     AND s.month_start = date_trunc('month', a.absence_date)::date
    GROUP BY s.month_start, s.department_id, s.location_id, s.job_level_id
)
SELECT
    h.month_start,
    date_trunc('quarter', h.month_start)::date       AS quarter_start,
    h.department_id,
    h.location_id,
    h.job_level_id,

    COALESCE(ab.unplanned_days, 0)                   AS unplanned_days,
    COALESCE(ab.planned_days, 0)                     AS planned_days,
    COALESCE(ab.total_absence_days, 0)               AS total_absence_days,

    h.avg_headcount,
    w.workdays,
    h.avg_headcount * w.workdays                     AS available_workdays
FROM headcount h
JOIN workdays w ON w.month_start = h.month_start
LEFT JOIN absence ab
       ON ab.month_start = h.month_start
      AND ab.department_id = h.department_id
      AND ab.location_id = h.location_id
      AND ab.job_level_id = h.job_level_id;
