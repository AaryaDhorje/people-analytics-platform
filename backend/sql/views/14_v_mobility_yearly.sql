-- v_mobility_yearly
-- Grain: one row per (year, department).
-- Serves: Internal Mobility Rate.
-- NL-queryable: yes.
--
-- Only PROMOTION and LATERAL_TRANSFER count, per docs/METRICS.md. Hires, comp changes
-- and manager changes are movement but not mobility, and including them would inflate
-- the rate several-fold.
--
-- Headcount is the left side of the join so a department with zero mobility in a year
-- still produces a row with a real denominator. Inner-joining events would make those
-- departments vanish, which reads as "no data" rather than "no mobility".
CREATE OR REPLACE VIEW v_mobility_yearly AS
WITH events AS (
    SELECT
        EXTRACT(YEAR FROM ev.event_date)::int                   AS year,
        -- Attribute a transfer to the receiving department; a promotion has no
        -- department change, so COALESCE falls back to where it happened.
        COALESCE(ev.to_department_id, ev.from_department_id)     AS department_id,
        COUNT(*) FILTER (WHERE ev.event_type = 'promotion')         AS promotions,
        COUNT(*) FILTER (WHERE ev.event_type = 'lateral_transfer')  AS lateral_transfers
    FROM fact_employment_event ev
    WHERE ev.event_type IN ('promotion', 'lateral_transfer')
    GROUP BY year, department_id
),
headcount AS (
    SELECT
        EXTRACT(YEAR FROM s.month_start)::int AS year,
        s.department_id,
        SUM((s.active_at_month_start::int + s.active_at_month_end::int) / 2.0)
            / COUNT(DISTINCT s.month_start)   AS avg_headcount,
        COUNT(DISTINCT s.month_start)         AS months_observed
    FROM fact_monthly_headcount_snapshot s
    GROUP BY year, s.department_id
)
SELECT
    h.year,
    h.department_id,
    COALESCE(e.promotions, 0)         AS promotions,
    COALESCE(e.lateral_transfers, 0)  AS lateral_transfers,
    COALESCE(e.promotions, 0) + COALESCE(e.lateral_transfers, 0) AS mobility_events,
    h.avg_headcount,
    h.months_observed
FROM headcount h
LEFT JOIN events e
       ON e.year = h.year
      AND e.department_id = h.department_id;
