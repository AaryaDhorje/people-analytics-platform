-- v_source_cost
-- Grain: one row per (source, department, quarter the requisition opened).
-- Serves: Cost per Hire attributed to the hiring channel.
-- NL-queryable: yes. This is the view behind "which channel costs us most per hire?"
--
-- Cost lives on the requisition and the channel lives on the application, so attributing
-- one to the other needs care. **Each requisition's cost is divided by its own hire count
-- and that share follows each hire's channel.** A requisition that filled two roles through
-- two different channels therefore splits its cost between them.
--
-- The naive join — requisition cost summed per channel — double-counts any multi-hire
-- requisition once per hire, inflating expensive channels precisely where they hire most.
--
-- In the current generator every requisition is single-channel and fills one opening, so
-- the two approaches agree numerically today. Relying on that would make the metric wrong
-- the moment the generator changed, which is why it is computed properly here.
CREATE OR REPLACE VIEW v_source_cost AS
WITH req_hires AS (
    SELECT
        a.requisition_id,
        a.source_id,
        COUNT(*) AS hires_from_source
    FROM fact_application a
    WHERE a.hired_employee_id IS NOT NULL
    GROUP BY a.requisition_id, a.source_id
),
req_totals AS (
    SELECT requisition_id, SUM(hires_from_source) AS total_hires
    FROM req_hires
    GROUP BY requisition_id
)
SELECT
    h.source_id,
    r.department_id,
    r.location_id,
    date_trunc('quarter', r.opened_date)::date AS opened_quarter,
    date_trunc('month', r.opened_date)::date   AS opened_month,

    SUM(h.hires_from_source)                   AS hires,

    -- The requisition's cost, split in proportion to how many of its hires came through
    -- this channel.
    SUM(
        (r.internal_cost + r.external_cost)
        * h.hires_from_source::numeric / t.total_hires
    )                                          AS attributed_cost,
    SUM(
        r.internal_cost * h.hires_from_source::numeric / t.total_hires
    )                                          AS attributed_internal_cost,
    SUM(
        r.external_cost * h.hires_from_source::numeric / t.total_hires
    )                                          AS attributed_external_cost
FROM req_hires h
JOIN req_totals t       ON t.requisition_id = h.requisition_id
JOIN dim_requisition r  ON r.requisition_id = h.requisition_id
GROUP BY
    h.source_id,
    r.department_id,
    r.location_id,
    opened_quarter,
    opened_month;
