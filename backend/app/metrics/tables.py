"""SQLAlchemy Table objects for the analytical views.

**These live in their own MetaData, deliberately.** If a view were declared against
`app.db.Base.metadata`, Alembic's autogenerate would see it as a missing table and
emit `CREATE TABLE v_headcount_monthly` in the next migration — then fail at runtime
because the real view already occupies the name. Views are created by
`app/sql_views.py` from `sql/views/*.sql`; migrations must never know about them.

Column types matter for filtering: a `Date` column compares correctly against a
`datetime.date`, where an untyped lightweight `table()` construct would pass the value
through as a string and quietly compare text.
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
)

#: Separate from Base.metadata. See the module docstring.
VIEW_METADATA = MetaData()


v_headcount_monthly = Table(
    "v_headcount_monthly",
    VIEW_METADATA,
    Column("month_start", Date),
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("manager_id", String(12)),
    Column("employee_months", Integer),
    Column("active_start", Integer),
    Column("active_end", Integer),
    Column("avg_headcount", Numeric),
    Column("hires", Integer),
    Column("terminations", Integer),
    Column("voluntary_terminations", Integer),
    Column("involuntary_terminations", Integer),
    Column("total_fte", Numeric),
)


v_tenure_band_monthly = Table(
    "v_tenure_band_monthly",
    VIEW_METADATA,
    Column("month_start", Date),
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("tenure_band", String(8)),
    Column("band_order", Integer),
    Column("headcount", Integer),
)


v_cohort_survival = Table(
    "v_cohort_survival",
    VIEW_METADATA,
    Column("hire_quarter", Date),
    Column("source_id", SmallInteger),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("months_since_hire", Integer),
    Column("cohort_size", Integer),
    Column("still_active", Integer),
)


v_manager_attrition_quarterly = Table(
    "v_manager_attrition_quarterly",
    VIEW_METADATA,
    Column("quarter_start", Date),
    Column("manager_id", String(12)),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("reports", Integer),
    Column("months_observed", Integer),
    Column("avg_reports", Numeric),
    Column("terminations", Integer),
    Column("voluntary_terminations", Integer),
    Column("headcount_months", Numeric),
)


v_mobility_monthly = Table(
    "v_mobility_monthly",
    VIEW_METADATA,
    Column("month_start", Date),
    Column("year", Integer),
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("promotions", Integer),
    Column("lateral_transfers", Integer),
    Column("mobility_events", Integer),
    Column("avg_headcount", Numeric),
)


v_regretted_exits = Table(
    "v_regretted_exits",
    VIEW_METADATA,
    Column("quarter_start", Date),
    Column("month_start", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("manager_id", String(12)),
    Column("total_exits", Integer),
    Column("voluntary_exits", Integer),
    Column("regretted_exits", Integer),
    Column("mean_exit_rating", Numeric),
)


# --- Acquisition ------------------------------------------------------------

v_requisition_metrics = Table(
    "v_requisition_metrics",
    VIEW_METADATA,
    Column("requisition_id", String(12)),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("manager_id", String(12)),
    Column("status", String(16)),
    Column("opened_date", Date),
    Column("opened_month", Date),
    Column("opened_quarter", Date),
    Column("closed_date", Date),
    Column("openings", Integer),
    Column("internal_cost", Numeric),
    Column("external_cost", Numeric),
    Column("total_cost", Numeric),
    Column("hires", Integer),
    Column("time_to_fill_day_sum", Integer),
    Column("filled_positions", Integer),
    Column("age_days", Integer),
)


v_application_funnel = Table(
    "v_application_funnel",
    VIEW_METADATA,
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("source_id", SmallInteger),
    Column("stage", String(16)),
    Column("stage_order", Integer),
    Column("entered_month", Date),
    Column("applications", Integer),
    Column("dwell_day_sum", Integer),
    Column("dwell_observations", Integer),
    Column("still_in_stage", Integer),
)


v_application_outcomes = Table(
    "v_application_outcomes",
    VIEW_METADATA,
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("source_id", SmallInteger),
    Column("applied_month", Date),
    Column("applied_quarter", Date),
    Column("applications", Integer),
    Column("offers_extended", Integer),
    Column("offers_accepted", Integer),
    Column("offers_declined", Integer),
    Column("hires", Integer),
    Column("time_to_hire_day_sum", Integer),
    Column("time_to_hire_observations", Integer),
)


v_source_quality = Table(
    "v_source_quality",
    VIEW_METADATA,
    Column("source_id", SmallInteger),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("manager_id", String(12)),
    Column("hire_quarter", Date),
    Column("hires", Integer),
    Column("eligible_90d", Integer),
    Column("retained_90d", Integer),
    Column("eligible_180d", Integer),
    Column("retained_180d", Integer),
    Column("quality_hires", Integer),
)


# --- Engagement -------------------------------------------------------------

v_survey_scores = Table(
    "v_survey_scores",
    VIEW_METADATA,
    Column("survey_id", SmallInteger),
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("manager_id", String(12)),
    Column("responses", Integer),
    Column("promoters", Integer),
    Column("passives", Integer),
    Column("detractors", Integer),
    Column("enps_score_sum", Integer),
    Column("driver_manager_sum", Integer),
    Column("driver_growth_sum", Integer),
    Column("driver_recognition_sum", Integer),
    Column("driver_workload_sum", Integer),
    Column("driver_belonging_sum", Integer),
    Column("driver_total_sum", Integer),
    Column("comments", Integer),
)


v_survey_participation = Table(
    "v_survey_participation",
    VIEW_METADATA,
    Column("survey_id", SmallInteger),
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("eligible_employees", Integer),
    Column("responses", Integer),
)


v_engagement_attrition = Table(
    "v_engagement_attrition",
    VIEW_METADATA,
    Column("quarter_start", Date),
    Column("quartile", Integer),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("employees", Integer),
    Column("terminations", Integer),
    Column("headcount_months", Numeric),
    Column("mean_raw_index", Numeric),
)


v_absenteeism_monthly = Table(
    "v_absenteeism_monthly",
    VIEW_METADATA,
    Column("month_start", Date),
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("unplanned_days", Numeric),
    Column("planned_days", Numeric),
    Column("total_absence_days", Numeric),
    Column("avg_headcount", Numeric),
    Column("workdays", Integer),
    Column("available_workdays", Numeric),
)


v_comment_themes = Table(
    "v_comment_themes",
    VIEW_METADATA,
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("theme", String(64)),
    Column("sentiment", String(16)),
    Column("model", String(48)),
    Column("volume", Integer),
    Column("mean_confidence", Numeric),
    Column("distinct_responses", Integer),
)


# --- Productivity -----------------------------------------------------------

v_timesheet_weekly = Table(
    "v_timesheet_weekly",
    VIEW_METADATA,
    Column("week_start", Date),
    Column("month_start", Date),
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("employee_id", String(12)),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("manager_id", String(12)),
    Column("fte", Numeric),
    Column("billable_hours", Numeric),
    Column("non_billable_hours", Numeric),
    Column("available_hours", Numeric),
    Column("total_hours", Numeric),
    Column("overtime_hours", Numeric),
    Column("output_units", Numeric),
    Column("output_type", String(16)),
)


v_revenue_per_fte = Table(
    "v_revenue_per_fte",
    VIEW_METADATA,
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("revenue_amount", Numeric),
    Column("fte_months", Numeric),
    Column("months_observed", Integer),
    Column("avg_fte", Numeric),
)


v_span_of_control = Table(
    "v_span_of_control",
    VIEW_METADATA,
    Column("month_start", Date),
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("managers", Integer),
    Column("direct_reports", Integer),
    Column("largest_team", Integer),
    Column("smallest_team", Integer),
)


v_goal_attainment = Table(
    "v_goal_attainment",
    VIEW_METADATA,
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("goals", Integer),
    Column("goals_with_target", Integer),
    Column("goals_without_target", Integer),
    Column("capped_attainment_sum", Numeric),
    Column("completed_goals", Integer),
    Column("missed_goals", Integer),
    Column("at_risk_goals", Integer),
)


v_flight_risk_inputs = Table(
    "v_flight_risk_inputs",
    VIEW_METADATA,
    Column("employee_id", String(12)),
    Column("as_of_month", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("manager_id", String(12)),
    Column("tenure_months", Integer),
    Column("months_since_promotion", Integer),
    Column("ever_promoted", Boolean),
    Column("employee_raw_index", Numeric),
    Column("department_raw_index", Numeric),
    Column("manager_terminations", Integer),
    Column("manager_headcount_months", Numeric),
    Column("company_terminations", Integer),
    Column("company_headcount_months", Numeric),
    Column("comp_amount", Numeric),
    Column("comp_band_min", Numeric),
    Column("comp_band_max", Numeric),
)


v_training_monthly = Table(
    "v_training_monthly",
    VIEW_METADATA,
    Column("month_start", Date),
    Column("year", Integer),
    Column("quarter_start", Date),
    Column("department_id", SmallInteger),
    Column("location_id", SmallInteger),
    Column("job_level_id", SmallInteger),
    Column("training_hours", Numeric),
    Column("assigned", Integer),
    Column("completed", Integer),
    Column("avg_headcount", Numeric),
)
