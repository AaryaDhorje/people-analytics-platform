-- v_goal_attainment
-- Grain: one row per (quarter, department).
-- Serves: Goal Attainment.
-- NL-queryable: yes.
--
-- **The 1.5 cap is applied per goal, here, before summing.** docs/METRICS.md defines the
-- metric as `AVG(goal_actual / goal_target) capped at 1.5`, and capping after averaging is
-- a different and wrong calculation: one goal at 400% would otherwise drag a whole team's
-- average up before the cap ever bit. This is the same class of per-row threshold as
-- overtime's 40 hours.
--
-- Goals with a zero target are excluded from `goals_with_target` rather than counted as
-- infinite attainment. They are surfaced separately so a data-quality problem stays
-- visible instead of quietly vanishing.
CREATE OR REPLACE VIEW v_goal_attainment AS
SELECT
    g.quarter_start,
    g.department_id,

    COUNT(*)                                             AS goals,
    COUNT(*) FILTER (WHERE g.target_value <> 0)          AS goals_with_target,
    COUNT(*) FILTER (WHERE g.target_value = 0)           AS goals_without_target,

    COALESCE(
        SUM(LEAST(g.actual_value / NULLIF(g.target_value, 0), 1.5)),
        0
    )                                                    AS capped_attainment_sum,

    COUNT(*) FILTER (WHERE g.status = 'complete')        AS completed_goals,
    COUNT(*) FILTER (WHERE g.status = 'missed')          AS missed_goals,
    COUNT(*) FILTER (WHERE g.status = 'at_risk')         AS at_risk_goals
FROM fact_goal g
GROUP BY g.quarter_start, g.department_id;
