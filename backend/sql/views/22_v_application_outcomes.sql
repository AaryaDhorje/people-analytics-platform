-- v_application_outcomes
-- Grain: one row per (department, location, level, source, month of first application).
-- Serves: Time to Hire, Offer Acceptance Rate.
-- NL-queryable: yes.
--
-- Time to hire runs from `first_application_date`, where time to fill runs from the
-- requisition's `opened_date`. They answer different questions -- how long the candidate
-- waited versus how long the vacancy stood open -- and conflating them is a standard
-- reporting error. They live in different views for that reason.
--
-- COUNT(column) counts non-nulls, which is what makes offers_extended and
-- offers_accepted a clean numerator/denominator pair.
CREATE OR REPLACE VIEW v_application_outcomes AS
SELECT
    r.department_id,
    r.location_id,
    r.job_level_id,
    a.source_id,
    date_trunc('month', a.first_application_date)::date  AS applied_month,
    date_trunc('quarter', a.first_application_date)::date AS applied_quarter,

    COUNT(*)                                             AS applications,
    COUNT(a.offer_extended_date)                         AS offers_extended,
    COUNT(a.offer_accepted_date)                         AS offers_accepted,
    COUNT(a.offer_declined_date)                         AS offers_declined,
    COUNT(a.hired_employee_id)                           AS hires,

    COALESCE(
        SUM(a.offer_accepted_date - a.first_application_date)
            FILTER (WHERE a.offer_accepted_date IS NOT NULL),
        0
    )                                                    AS time_to_hire_day_sum,
    COUNT(*) FILTER (WHERE a.offer_accepted_date IS NOT NULL)
                                                         AS time_to_hire_observations
FROM fact_application a
JOIN dim_requisition r ON r.requisition_id = a.requisition_id
GROUP BY
    r.department_id,
    r.location_id,
    r.job_level_id,
    a.source_id,
    applied_month,
    applied_quarter;
