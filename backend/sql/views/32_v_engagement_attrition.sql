-- v_engagement_attrition
-- Grain: one row per (survey quarter, engagement quartile, department, location).
-- Serves: Engagement -> Attrition Link.
-- NL-queryable: yes. This is the view behind "do disengaged people actually leave?"
--
-- The metric compares attrition of the bottom engagement quartile against the top. Three
-- decisions make that measurable:
--
-- 1. **Quartiles are cut within each survey quarter**, not across the whole window. A
--    company-wide reorg drags every score down at once; ranking across quarters would then
--    fill the bottom quartile with everyone surveyed after the reorg and measure the
--    calendar rather than the person.
--
-- 2. **The follow-up window starts the month after the survey CLOSES**, not at the survey's
--    quarter start. This was wrong in the first implementation and is worth spelling out:
--    every survey in dim_survey opens in the third month of its quarter (Q1-25 has
--    quarter_start 2025-01-01 but closes_on 2025-03-31). Anchoring the window to
--    quarter_start therefore ran it from three months BEFORE the survey was administered to
--    three months after it closed. Half the exposure predated the answers it was supposed to
--    be a consequence of, inflating the denominator while contributing almost no events, and
--    every quartile read at roughly half its true rate.
--
-- 3. **The window is one quarter, matching the survey cadence, so windows never overlap.**
--    With a six-month window and quarterly surveys, every employee-month fell inside two
--    surveys' windows under two possibly different quartiles, and the respondent count summed
--    to 5,208 against 1,469 real people.
CREATE OR REPLACE VIEW v_engagement_attrition AS
WITH per_response AS (
    SELECT
        r.employee_id,
        sv.quarter_start,
        -- The month after the survey closed: the first month a response could plausibly
        -- have preceded a decision to leave.
        (date_trunc('month', sv.closes_on) + INTERVAL '1 month')::date AS follow_start,
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
        p.follow_start,
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
 AND s.month_start >= b.follow_start
 AND s.month_start < (b.follow_start + INTERVAL '3 months')
GROUP BY
    b.quarter_start,
    b.quartile,
    s.department_id,
    s.location_id;
