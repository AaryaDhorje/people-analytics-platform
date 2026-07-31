-- v_flight_risk_inputs
-- Grain: one row per currently-active employee.
-- Serves: Flight Risk Score.
-- NL-queryable: no. This view carries raw per-person signals; the Ask feature should read
-- v_flight_risk_scored instead, which exposes the finished score without the inputs.
--
-- Assembles the five raw signals docs/METRICS.md names for the flight-risk score:
-- tenure band, months since last promotion, engagement delta, manager attrition rate, and
-- comp percentile against band. **No scoring happens here** -- every value is raw, and the
-- weighting lives in app/metrics/flight_risk.py so it can be read aloud and defended live.
--
-- As-of the latest snapshot month only. Flight risk answers "who is at risk now", and
-- computing 36 months of history for every employee would cost far more than it informs.
--
-- Employees with no survey response get a NULL engagement index rather than a zero. The
-- scorer treats that as neutral: never having answered a survey is not evidence of
-- disengagement, and scoring it as such would punish new joiners.
CREATE OR REPLACE VIEW v_flight_risk_inputs AS
WITH horizon AS (
    SELECT MAX(month_start) AS as_of FROM fact_monthly_headcount_snapshot
),
active AS (
    SELECT
        s.employee_id,
        s.month_start AS as_of_month,
        s.department_id,
        s.location_id,
        s.job_level_id,
        s.manager_id,
        s.tenure_months,
        s.comp_amount
    FROM fact_monthly_headcount_snapshot s
    CROSS JOIN horizon h
    WHERE s.month_start = h.as_of
      AND s.active_at_month_end
),
last_promotion AS (
    SELECT ev.employee_id, MAX(ev.event_date) AS last_promotion_date
    FROM fact_employment_event ev
    WHERE ev.event_type = 'promotion'
    GROUP BY ev.employee_id
),
latest_engagement AS (
    -- Most recent survey response per person.
    SELECT DISTINCT ON (r.employee_id)
        r.employee_id,
        (
            r.driver_manager + r.driver_growth + r.driver_recognition
            + r.driver_workload + r.driver_belonging
        ) / 5.0 AS raw_index
    FROM fact_survey_response r
    ORDER BY r.employee_id, r.submitted_on DESC
),
department_engagement AS (
    -- The comparison baseline. Department rather than company, because a low score in a
    -- department where everyone scores low says less than the same score among peers who
    -- are content.
    SELECT
        s.department_id,
        AVG(
            (
                r.driver_manager + r.driver_growth + r.driver_recognition
                + r.driver_workload + r.driver_belonging
            ) / 5.0
        ) AS department_raw_index
    FROM fact_survey_response r
    JOIN fact_monthly_headcount_snapshot s
      ON s.employee_id = r.employee_id
     AND s.month_start = date_trunc('month', r.submitted_on)::date
    GROUP BY s.department_id
),
manager_trailing AS (
    -- Trailing twelve months, so a manager's record reflects the recent past rather than
    -- being diluted by three years of history.
    SELECT
        s.manager_id,
        SUM(s.terminated_in_month::int) AS terminations,
        SUM((s.active_at_month_start::int + s.active_at_month_end::int) / 2.0)
            AS headcount_months
    FROM fact_monthly_headcount_snapshot s
    CROSS JOIN horizon h
    WHERE s.manager_id IS NOT NULL
      AND s.month_start > (h.as_of - INTERVAL '12 months')
      AND s.month_start <= h.as_of
    GROUP BY s.manager_id
),
company_trailing AS (
    SELECT
        SUM(s.terminated_in_month::int) AS terminations,
        SUM((s.active_at_month_start::int + s.active_at_month_end::int) / 2.0)
            AS headcount_months
    FROM fact_monthly_headcount_snapshot s
    CROSS JOIN horizon h
    WHERE s.month_start > (h.as_of - INTERVAL '12 months')
      AND s.month_start <= h.as_of
)
SELECT
    a.employee_id,
    a.as_of_month,
    a.department_id,
    a.location_id,
    a.job_level_id,
    a.manager_id,

    a.tenure_months,

    -- Never promoted counts as "months since joining": someone three years in with no
    -- promotion carries the same signal as someone three years past their last one.
    COALESCE(
        (
            EXTRACT(YEAR FROM AGE(a.as_of_month, lp.last_promotion_date)) * 12
            + EXTRACT(MONTH FROM AGE(a.as_of_month, lp.last_promotion_date))
        )::int,
        a.tenure_months
    )                                          AS months_since_promotion,
    (lp.last_promotion_date IS NOT NULL)       AS ever_promoted,

    le.raw_index                               AS employee_raw_index,
    de.department_raw_index,

    COALESCE(mt.terminations, 0)               AS manager_terminations,
    COALESCE(mt.headcount_months, 0)           AS manager_headcount_months,
    ct.terminations                            AS company_terminations,
    ct.headcount_months                        AS company_headcount_months,

    a.comp_amount,
    jl.comp_band_min,
    jl.comp_band_max
FROM active a
CROSS JOIN company_trailing ct
JOIN dim_job_level jl        ON jl.job_level_id = a.job_level_id
LEFT JOIN last_promotion lp  ON lp.employee_id = a.employee_id
LEFT JOIN latest_engagement le ON le.employee_id = a.employee_id
LEFT JOIN department_engagement de ON de.department_id = a.department_id
LEFT JOIN manager_trailing mt ON mt.manager_id = a.manager_id;
