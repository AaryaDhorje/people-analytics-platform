-- v_span_of_control
-- Grain: one row per (month, manager's department, location, level).
-- Serves: Span of Control.
-- NL-queryable: yes.
--
-- Grouped by the **manager's own** attributes, not the reports'. docs/METRICS.md grains
-- this by department and level, and the question being asked is "how wide are our L5
-- managers' teams", not "what level are the reports". Grouping by the reports' level would
-- split one manager across several rows and make the average meaningless.
--
-- Only managers who actually have reports appear. Counting every employee as a manager of
-- zero would drag the company average toward zero and describe nothing real.
CREATE OR REPLACE VIEW v_span_of_control AS
WITH team_size AS (
    SELECT
        s.month_start,
        s.manager_id,
        COUNT(*) AS direct_reports
    FROM fact_monthly_headcount_snapshot s
    WHERE s.manager_id IS NOT NULL
      AND s.active_at_month_end
    GROUP BY s.month_start, s.manager_id
)
SELECT
    t.month_start,
    date_trunc('quarter', t.month_start)::date AS quarter_start,
    m.department_id,
    m.location_id,
    m.job_level_id,

    COUNT(*)                  AS managers,
    SUM(t.direct_reports)     AS direct_reports,
    MAX(t.direct_reports)     AS largest_team,
    MIN(t.direct_reports)     AS smallest_team
FROM team_size t
JOIN fact_monthly_headcount_snapshot m
  ON m.employee_id = t.manager_id
 AND m.month_start = t.month_start
GROUP BY
    t.month_start,
    quarter_start,
    m.department_id,
    m.location_id,
    m.job_level_id;
