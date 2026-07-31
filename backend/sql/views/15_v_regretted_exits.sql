-- v_regretted_exits
-- Grain: one row per (quarter of exit, department, location, job level, manager).
-- Serves: Regretted Attrition.
-- NL-queryable: yes. This is the view behind "which managers lose high performers?"
--
-- Regretted attrition is a *voluntary* exit by someone whose last rating was 4 or 5.
-- An involuntary exit of a high performer is not regretted -- it is a decision. The
-- filter therefore sits on termination_type, not on rating alone.
--
-- The LATERAL join takes the last review dated at or before the termination, not simply
-- the last review on file. Those are the same thing given how reviews are generated, but
-- relying on that coincidence would break the moment a back-dated review was inserted.
CREATE OR REPLACE VIEW v_regretted_exits AS
SELECT
    date_trunc('quarter', e.termination_date)::date AS quarter_start,
    date_trunc('month', e.termination_date)::date   AS month_start,
    e.department_id,
    e.location_id,
    e.job_level_id,
    e.manager_id,

    COUNT(*)                                                          AS total_exits,
    COUNT(*) FILTER (WHERE e.termination_type = 'voluntary')           AS voluntary_exits,
    COUNT(*) FILTER (
        WHERE e.termination_type = 'voluntary' AND last_review.rating >= 4
    )                                                                 AS regretted_exits,
    AVG(last_review.rating) FILTER (WHERE e.termination_type = 'voluntary')
                                                                      AS mean_exit_rating
FROM dim_employee e
LEFT JOIN LATERAL (
    SELECT r.rating
    FROM fact_performance_review r
    WHERE r.employee_id = e.employee_id
      AND r.review_date <= e.termination_date
    ORDER BY r.review_date DESC
    LIMIT 1
) AS last_review ON TRUE
WHERE e.termination_date IS NOT NULL
GROUP BY
    quarter_start,
    month_start,
    e.department_id,
    e.location_id,
    e.job_level_id,
    e.manager_id;
