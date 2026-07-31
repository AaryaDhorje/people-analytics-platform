-- v_survey_scores
-- Grain: one row per (survey, department, location, level, manager).
-- Serves: eNPS, Engagement Index, Driver Breakdown.
-- NL-queryable: yes.
--
-- Driver columns are exposed as raw **sums** over a response count, not as averages.
-- Averaging here would make every downstream figure subtly wrong: AVG of a view's
-- pre-averaged column weights each group equally regardless of how many people answered,
-- so a two-person team would count as much as a two-hundred-person one. Summing keeps the
-- caller's division correctly response-weighted.
--
-- Scores stay on the raw 1-5 scale. The conversion to 0-100 is
-- `(raw - 1) / 4 * 100`, applied once in app/metrics/engagement.py.
--
-- Department comes from the snapshot for the month the response was submitted, not from
-- dim_employee. Someone who transferred after answering is counted under the team they
-- were actually in when they gave that answer.
CREATE OR REPLACE VIEW v_survey_scores AS
SELECT
    r.survey_id,
    sv.quarter_start,
    s.department_id,
    s.location_id,
    s.job_level_id,
    s.manager_id,

    COUNT(*)                                             AS responses,

    -- eNPS bands, per docs/METRICS.md: promoters 9-10, passives 7-8, detractors 0-6.
    COUNT(*) FILTER (WHERE r.enps_score >= 9)            AS promoters,
    COUNT(*) FILTER (WHERE r.enps_score BETWEEN 7 AND 8) AS passives,
    COUNT(*) FILTER (WHERE r.enps_score <= 6)            AS detractors,
    SUM(r.enps_score)                                    AS enps_score_sum,

    SUM(r.driver_manager)                                AS driver_manager_sum,
    SUM(r.driver_growth)                                 AS driver_growth_sum,
    SUM(r.driver_recognition)                            AS driver_recognition_sum,
    SUM(r.driver_workload)                               AS driver_workload_sum,
    SUM(r.driver_belonging)                              AS driver_belonging_sum,

    -- All five drivers summed, so the engagement index is one division rather than a
    -- mean of five separately-rounded means.
    SUM(
        r.driver_manager + r.driver_growth + r.driver_recognition
        + r.driver_workload + r.driver_belonging
    )                                                    AS driver_total_sum,

    COUNT(r.open_text)                                   AS comments
FROM fact_survey_response r
JOIN dim_survey sv ON sv.survey_id = r.survey_id
JOIN fact_monthly_headcount_snapshot s
  ON s.employee_id = r.employee_id
 AND s.month_start = date_trunc('month', r.submitted_on)::date
GROUP BY
    r.survey_id,
    sv.quarter_start,
    s.department_id,
    s.location_id,
    s.job_level_id,
    s.manager_id;
