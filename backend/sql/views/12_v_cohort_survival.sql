-- v_cohort_survival
-- Grain: one row per (hire quarter, source, department, months since hire).
-- Serves: New Hire 12-Month Retention, and the cohort survival curve in phase 5.
-- NL-queryable: yes.
--
-- The subtlety here is censoring. `cohort_size` counts only cohort members who have
-- actually *reached* that milestone inside the data window -- someone hired three
-- months ago cannot inform 12-month retention. Counting them in the denominator would
-- make recent cohorts look worse, and counting them in the numerator would make them
-- look perfect. Both are wrong, so they are excluded from that offset entirely, which
-- is why cohort_size varies by months_since_hire rather than being constant.
CREATE OR REPLACE VIEW v_cohort_survival AS
WITH horizon AS (
    SELECT MAX(day) AS last_day FROM dim_date
),
cohort AS (
    SELECT
        e.employee_id,
        date_trunc('quarter', e.hire_date)::date AS hire_quarter,
        e.source_id,
        e.department_id,
        e.location_id,
        e.hire_date,
        e.termination_date
    FROM dim_employee e
    -- Employees predating the window have no recorded channel and no meaningful
    -- cohort, so they are not part of any survival curve.
    WHERE e.source_id IS NOT NULL
),
expanded AS (
    SELECT
        c.*,
        m.months_since_hire,
        (c.hire_date + (m.months_since_hire || ' months')::interval)::date AS milestone
    FROM cohort c
    CROSS JOIN generate_series(0, 24) AS m(months_since_hire)
)
SELECT
    e.hire_quarter,
    e.source_id,
    e.department_id,
    e.location_id,
    e.months_since_hire,
    COUNT(*)                                                       AS cohort_size,
    COUNT(*) FILTER (
        WHERE e.termination_date IS NULL OR e.termination_date >= e.milestone
    )                                                              AS still_active
FROM expanded e
CROSS JOIN horizon h
WHERE e.milestone <= h.last_day
GROUP BY
    e.hire_quarter,
    e.source_id,
    e.department_id,
    e.location_id,
    e.months_since_hire;
