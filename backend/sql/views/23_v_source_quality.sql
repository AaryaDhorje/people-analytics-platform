-- v_source_quality
-- Grain: one row per (source, department, location, manager, hire quarter).
-- Serves: Source Effectiveness (the retention half), Quality of Hire.
-- NL-queryable: yes. This is the view behind "which channel produces hires that stay?"
--
-- **This view counts employees, not applications.** Source Effectiveness has two halves
-- that come from different tables: the conversion half (hires / applications) is
-- application-level and lives in v_application_outcomes, while the retention half is
-- employee-level and lives here. Computing both from one table would be wrong in either
-- direction -- applications carry no termination date, and employees carry no funnel.
--
-- Milestones are censored the same way cohort survival is: an employee hired 60 days ago
-- cannot inform 90-day retention, so they are excluded from that denominator rather than
-- counted as retained. `eligible_*` is therefore the honest denominator, not `hires`.
--
-- The rating for Quality of Hire is the latest review on or before day 210. docs/METRICS.md
-- specifies "performance_rating >= 3" at day 180; reviews rarely land exactly on a
-- milestone, so a 30-day grace window is applied rather than requiring an exact hit that
-- would make the metric null for almost everyone.
CREATE OR REPLACE VIEW v_source_quality AS
WITH horizon AS (
    SELECT MAX(day) AS last_day FROM dim_date
),
sourced_hires AS (
    SELECT
        e.employee_id,
        e.source_id,
        e.department_id,
        e.location_id,
        e.job_level_id,
        e.manager_id,
        e.hire_date,
        e.termination_date,
        date_trunc('quarter', e.hire_date)::date AS hire_quarter
    FROM dim_employee e
    -- Employees predating the window have no recorded channel, so they cannot be
    -- attributed to one.
    WHERE e.source_id IS NOT NULL
)
SELECT
    h.source_id,
    h.department_id,
    h.location_id,
    h.job_level_id,
    h.manager_id,
    h.hire_quarter,

    COUNT(*)                                                             AS hires,

    COUNT(*) FILTER (
        WHERE (h.hire_date + INTERVAL '90 days')::date <= z.last_day
    )                                                                    AS eligible_90d,
    COUNT(*) FILTER (
        WHERE (h.hire_date + INTERVAL '90 days')::date <= z.last_day
          AND (
              h.termination_date IS NULL
              OR h.termination_date >= (h.hire_date + INTERVAL '90 days')::date
          )
    )                                                                    AS retained_90d,

    COUNT(*) FILTER (
        WHERE (h.hire_date + INTERVAL '180 days')::date <= z.last_day
    )                                                                    AS eligible_180d,
    COUNT(*) FILTER (
        WHERE (h.hire_date + INTERVAL '180 days')::date <= z.last_day
          AND (
              h.termination_date IS NULL
              OR h.termination_date >= (h.hire_date + INTERVAL '180 days')::date
          )
    )                                                                    AS retained_180d,

    -- Quality of hire: survived to day 180 AND rated 3 or better.
    COUNT(*) FILTER (
        WHERE (h.hire_date + INTERVAL '180 days')::date <= z.last_day
          AND (
              h.termination_date IS NULL
              OR h.termination_date >= (h.hire_date + INTERVAL '180 days')::date
          )
          AND milestone_review.rating >= 3
    )                                                                    AS quality_hires
FROM sourced_hires h
CROSS JOIN horizon z
LEFT JOIN LATERAL (
    SELECT r.rating
    FROM fact_performance_review r
    WHERE r.employee_id = h.employee_id
      AND r.review_date <= (h.hire_date + INTERVAL '210 days')::date
    ORDER BY r.review_date DESC
    LIMIT 1
) AS milestone_review ON TRUE
GROUP BY
    h.source_id,
    h.department_id,
    h.location_id,
    h.job_level_id,
    h.manager_id,
    h.hire_quarter,
    z.last_day;
