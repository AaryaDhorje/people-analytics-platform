-- v_engagement_attrition
-- Grain: one row per (survey quarter, engagement quartile, department).
-- Serves: Engagement -> Attrition Link.
-- NL-queryable: yes. This is the view behind "do disengaged people actually leave?"
--
-- The metric compares attrition of the bottom engagement quartile against the top. Two
-- decisions make that measurable:
--
-- 1. **Quartiles are cut within each survey quarter**, not across the whole window. A
--    company-wide reorg drags every score down at once; ranking across quarters would then
--    fill the bottom quartile with everyone surveyed after the reorg and measure the
--    calendar rather than the person.
-- 2. **Attrition is measured in the six months *after* the survey.** Counting attrition in
--    the same quarter would be circular -- people already leaving answer badly on the way
--    out. The lag is what turns a correlation into something worth showing on a chart, and
--    it is what makes the post-reorg dip visibly precede the attrition spike.
CREATE OR REPLACE VIEW v_engagement_attrition AS
WITH per_response AS (
    SELECT
        r.employee_id,
        sv.quarter_start,
        (
            r.driver_manager + r.driver_growth + r.driver_recognition
            + r.driver_workload + r.driver_belonging
        ) / 5.0 AS raw_index
    FROM fact_survey_response r
    JOIN dim_survey sv ON sv.survey_id = r.survey_id
),
banded AS (
    SELECT
        p.employee_id,
        p.quarter_start,
        p.raw_index,
        NTILE(4) OVER (PARTITION BY p.quarter_start ORDER BY p.raw_index) AS quartile
    FROM per_response p
)
SELECT
    b.quarter_start,
    b.quartile,
    s.department_id,
    s.location_id,

    COUNT(DISTINCT b.employee_id)                        AS employees,
    SUM(s.terminated_in_month::int)                      AS terminations,
    SUM((s.active_at_month_start::int + s.active_at_month_end::int) / 2.0)
                                                         AS headcount_months,
    AVG(b.raw_index)                                     AS mean_raw_index
FROM banded b
JOIN fact_monthly_headcount_snapshot s
  ON s.employee_id = b.employee_id
 AND s.month_start >= b.quarter_start
 AND s.month_start < (b.quarter_start + INTERVAL '6 months')
GROUP BY
    b.quarter_start,
    b.quartile,
    s.department_id,
    s.location_id;
