-- v_application_funnel
-- Grain: one row per (department, location, level, source, stage, month entered).
-- Serves: Funnel Conversion, and the stage-dwell figures behind the Sales bottleneck.
-- NL-queryable: yes. This is the view behind "where do candidates get stuck?"
--
-- `applications` counts DISTINCT application_id, not stage-event rows. An application
-- that re-enters a stage produces two honest event rows, and counting rows would inflate
-- that stage and make conversion exceed 100% -- a funnel that widens as it descends.
--
-- Dwell is a day sum plus an observation count so the caller divides. `exited_on IS NULL`
-- means the candidate is still sitting in that stage, and those rows are excluded from
-- the dwell denominator: including an in-flight candidate as zero days would drag the
-- mean down exactly where a pipeline is slowest.
CREATE OR REPLACE VIEW v_application_funnel AS
SELECT
    r.department_id,
    r.location_id,
    r.job_level_id,
    a.source_id,

    se.stage::text                                       AS stage,
    CASE se.stage
        WHEN 'applied'   THEN 1
        WHEN 'screen'    THEN 2
        WHEN 'interview' THEN 3
        WHEN 'offer'     THEN 4
        WHEN 'hired'     THEN 5
        ELSE 9
    END                                                  AS stage_order,

    date_trunc('month', se.entered_on)::date             AS entered_month,

    COUNT(DISTINCT se.application_id)                    AS applications,

    COALESCE(
        SUM(se.exited_on - se.entered_on) FILTER (WHERE se.exited_on IS NOT NULL),
        0
    )                                                    AS dwell_day_sum,
    COUNT(*) FILTER (WHERE se.exited_on IS NOT NULL)     AS dwell_observations,
    COUNT(*) FILTER (WHERE se.exited_on IS NULL)         AS still_in_stage
FROM fact_application_stage_event se
JOIN fact_application a ON a.application_id = se.application_id
JOIN dim_requisition r  ON r.requisition_id = a.requisition_id
GROUP BY
    r.department_id,
    r.location_id,
    r.job_level_id,
    a.source_id,
    se.stage,
    stage_order,
    entered_month;
