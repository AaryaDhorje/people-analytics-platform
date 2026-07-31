-- v_requisition_metrics
-- Grain: one row per requisition.
-- Serves: Time to Fill, Requisition Aging, Cost per Hire.
-- NL-queryable: yes.
--
-- Time to fill is exposed as a day *sum* plus a count of filled positions rather than as
-- an average, so the caller divides. Averaging inside the view would make a filtered
-- average wrong: AVG over a subset of rows is not the average of a re-filtered subset
-- once the caller aggregates across requisitions.
--
-- `age_days` is measured to the last day in the spine, not to CURRENT_DATE. The warehouse
-- is a fixed window; using the wall clock would make requisition aging drift every day
-- the demo is not run, and would break the moment the data stopped being regenerated.
--
-- The 60-day aging threshold is deliberately NOT applied here. docs/METRICS.md owns it,
-- and app/metrics/acquisition.py applies it as a named constant so it lives in one place.
CREATE OR REPLACE VIEW v_requisition_metrics AS
SELECT
    r.requisition_id,
    r.department_id,
    r.location_id,
    r.job_level_id,
    r.hiring_manager_id                                  AS manager_id,
    r.status::text                                       AS status,

    r.opened_date,
    date_trunc('month', r.opened_date)::date             AS opened_month,
    date_trunc('quarter', r.opened_date)::date           AS opened_quarter,
    r.closed_date,
    r.openings,

    r.internal_cost,
    r.external_cost,
    r.internal_cost + r.external_cost                    AS total_cost,

    COUNT(a.application_id) FILTER (WHERE a.hired_employee_id IS NOT NULL) AS hires,

    -- Numerator and denominator for Time to Fill.
    COALESCE(
        SUM(a.offer_accepted_date - r.opened_date)
            FILTER (WHERE a.offer_accepted_date IS NOT NULL),
        0
    )                                                    AS time_to_fill_day_sum,
    COUNT(*) FILTER (WHERE a.offer_accepted_date IS NOT NULL) AS filled_positions,

    (horizon.last_day - r.opened_date)                   AS age_days
FROM dim_requisition r
CROSS JOIN (SELECT MAX(day) AS last_day FROM dim_date) AS horizon
LEFT JOIN fact_application a ON a.requisition_id = r.requisition_id
GROUP BY
    r.requisition_id,
    r.department_id,
    r.location_id,
    r.job_level_id,
    r.hiring_manager_id,
    r.status,
    r.opened_date,
    r.closed_date,
    r.openings,
    r.internal_cost,
    r.external_cost,
    horizon.last_day;
