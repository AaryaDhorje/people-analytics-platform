-- v_mobility_monthly
-- Grain: one row per (month, department).
-- Serves: Internal Mobility Rate.
-- NL-queryable: yes.
--
-- Only PROMOTION and LATERAL_TRANSFER count, per docs/METRICS.md. Hires, comp changes and
-- manager changes are movement but not mobility, and including them would inflate the rate
-- several-fold.
--
-- **Monthly grain, and that matters.** The first version was grained by (year, department)
-- and exposed a pre-divided `avg_headcount` per group. Summing that across departments
-- inside one year is correct, and gave the right answer for any single-year query -- but
-- summing it across *years*, which a whole-window query does, adds four yearly averages
-- together. The all-window call reported an average headcount of 4,760 for a company
-- averaging 1,194 people, and the API emitted that figure as a field.
--
-- A pre-divided average can only be re-aggregated along the dimensions it was *not* divided
-- by. Exposing avg_headcount per month and letting the caller divide by the number of months
-- it actually asked for removes the trap entirely.
--
-- Headcount is the left side of the join so a department with no mobility in a month still
-- produces a row with a real denominator, rather than vanishing.
CREATE OR REPLACE VIEW v_mobility_monthly AS
WITH events AS (
    SELECT
        date_trunc('month', ev.event_date)::date                 AS month_start,
        -- A transfer is attributed to the receiving department; a promotion carries no
        -- department change, so COALESCE falls back to where it happened.
        COALESCE(ev.to_department_id, ev.from_department_id)     AS department_id,
        COUNT(*) FILTER (WHERE ev.event_type = 'promotion')         AS promotions,
        COUNT(*) FILTER (WHERE ev.event_type = 'lateral_transfer')  AS lateral_transfers
    FROM fact_employment_event ev
    WHERE ev.event_type IN ('promotion', 'lateral_transfer')
    GROUP BY month_start, department_id
),
headcount AS (
    SELECT
        s.month_start,
        s.department_id,
        SUM((s.active_at_month_start::int + s.active_at_month_end::int) / 2.0)
            AS avg_headcount
    FROM fact_monthly_headcount_snapshot s
    GROUP BY s.month_start, s.department_id
)
SELECT
    h.month_start,
    EXTRACT(YEAR FROM h.month_start)::int      AS year,
    date_trunc('quarter', h.month_start)::date AS quarter_start,
    h.department_id,

    COALESCE(e.promotions, 0)                                    AS promotions,
    COALESCE(e.lateral_transfers, 0)                             AS lateral_transfers,
    COALESCE(e.promotions, 0) + COALESCE(e.lateral_transfers, 0) AS mobility_events,
    h.avg_headcount
FROM headcount h
LEFT JOIN events e
       ON e.month_start = h.month_start
      AND e.department_id = h.department_id;
