-- v_comment_themes
-- Grain: one row per (survey quarter, department, theme, sentiment).
-- Serves: Comment Themes.
-- NL-queryable: yes.
--
-- Reads fact_comment_theme, which phase 6 populates with a batch Haiku classification of
-- open-text survey comments. Until then this view is valid and returns no rows -- which is
-- the correct behaviour, and why the metric that reads it must render an empty result as
-- "no themes yet" rather than as an error.
--
-- `model` is carried through to the grain so a theme set can be attributed to the model
-- that produced it. When the model changes, old and new themes stay distinguishable
-- instead of silently blending into one series.
CREATE OR REPLACE VIEW v_comment_themes AS
SELECT
    sv.quarter_start,
    s.department_id,
    s.location_id,

    ct.theme,
    ct.sentiment::text                 AS sentiment,
    ct.model,

    COUNT(*)                           AS volume,
    AVG(ct.confidence)                 AS mean_confidence,
    COUNT(DISTINCT ct.survey_response_id) AS distinct_responses
FROM fact_comment_theme ct
JOIN fact_survey_response r ON r.response_id = ct.survey_response_id
JOIN dim_survey sv          ON sv.survey_id = r.survey_id
JOIN fact_monthly_headcount_snapshot s
  ON s.employee_id = r.employee_id
 AND s.month_start = date_trunc('month', r.submitted_on)::date
GROUP BY
    sv.quarter_start,
    s.department_id,
    s.location_id,
    ct.theme,
    ct.sentiment,
    ct.model;
