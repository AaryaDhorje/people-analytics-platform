-- v_survey_participation
-- Grain: one row per (survey, department, location, level).
-- Serves: Survey Participation.
-- NL-queryable: yes.
--
-- The denominator is who was *eligible*, taken from the headcount snapshot for the month
-- the survey closed -- not the number of responses, and not current headcount. Someone who
-- left before the survey closed was never eligible, and counting them would understate
-- participation for exactly the teams losing people.
--
-- Eligibility is the left side of the join so a department with zero responses still
-- produces a row with a real denominator. Inner-joining responses would make
-- non-responding teams disappear, which reads as "no data" rather than "nobody replied" --
-- and the second is the more interesting finding.
CREATE OR REPLACE VIEW v_survey_participation AS
WITH eligible AS (
    SELECT
        sv.survey_id,
        sv.quarter_start,
        s.department_id,
        s.location_id,
        s.job_level_id,
        COUNT(*) AS eligible_employees
    FROM dim_survey sv
    JOIN fact_monthly_headcount_snapshot s
      ON s.month_start = date_trunc('month', sv.closes_on)::date
     AND s.active_at_month_end
    GROUP BY sv.survey_id, sv.quarter_start, s.department_id, s.location_id, s.job_level_id
),
responded AS (
    SELECT
        r.survey_id,
        s.department_id,
        s.location_id,
        s.job_level_id,
        COUNT(*) AS responses
    FROM fact_survey_response r
    JOIN fact_monthly_headcount_snapshot s
      ON s.employee_id = r.employee_id
     AND s.month_start = date_trunc('month', r.submitted_on)::date
    GROUP BY r.survey_id, s.department_id, s.location_id, s.job_level_id
)
SELECT
    e.survey_id,
    e.quarter_start,
    e.department_id,
    e.location_id,
    e.job_level_id,
    e.eligible_employees,
    COALESCE(d.responses, 0) AS responses
FROM eligible e
LEFT JOIN responded d
       ON d.survey_id = e.survey_id
      AND d.department_id = e.department_id
      AND d.location_id = e.location_id
      AND d.job_level_id = e.job_level_id;
