"""Schema guards.

These assert against `Base.metadata` and never open a connection, so they run in
the edit hook and on a machine with no Postgres. They are deliberately about
*structure the metrics depend on* — not a restatement of every column, which would
just be the model files typed twice.
"""

from sqlalchemy import Float, Numeric
from sqlalchemy.orm import configure_mappers

from app.models import Base

EXPECTED_TABLES = {
    # dimensions
    "dim_date",
    "dim_department",
    "dim_location",
    "dim_job_level",
    "dim_source",
    "dim_employee",
    "dim_requisition",
    "dim_survey",
    # facts
    "fact_employment_event",
    "fact_monthly_headcount_snapshot",
    "fact_application",
    "fact_application_stage_event",
    "fact_survey_response",
    "fact_timesheet_week",
    "fact_goal",
    "fact_absence",
    "fact_performance_review",
    "fact_department_revenue",
    "fact_training",
    "fact_flight_risk_score",
    "fact_comment_theme",
}

#: Tables that exist to run the application rather than to model the business. They are
#: listed separately so the star-schema counts below stay meaningful — "21 tables" is a
#: statement about the warehouse, and quietly incrementing it whenever an operational table
#: appears would turn the guard into a number that always agrees with reality.
OPERATIONAL_TABLES = {
    "ai_cache",  # phase 6: read-through cache for AI responses
}


def test_all_models_are_registered() -> None:
    """A model missing from app/models/__init__.py is invisible to Alembic, which
    then generates a DROP TABLE for it on the next revision."""
    configure_mappers()

    assert set(Base.metadata.tables) == EXPECTED_TABLES | OPERATIONAL_TABLES


def test_the_star_schema_is_still_eight_dimensions_and_thirteen_facts() -> None:
    """The shape docs/ARCHITECTURE.md describes. A new warehouse table has to be a
    deliberate change to that document, not a side effect of adding a model."""
    warehouse = set(Base.metadata.tables) - OPERATIONAL_TABLES

    assert len(warehouse) == 21
    assert sum(1 for t in warehouse if t.startswith("dim_")) == 8
    assert sum(1 for t in warehouse if t.startswith("fact_")) == 13


def test_employee_manager_is_a_resolvable_self_reference() -> None:
    """Span of control and the manager rollup both walk this edge."""
    employee = Base.metadata.tables["dim_employee"]
    (fk,) = employee.c.manager_id.foreign_keys

    assert fk.column.table.name == "dim_employee"
    assert fk.column.name == "employee_id"
    assert employee.c.manager_id.nullable, "the top of the org has no manager"


def test_snapshot_grain_is_employee_month() -> None:
    snapshot = Base.metadata.tables["fact_monthly_headcount_snapshot"]

    assert [c.name for c in snapshot.primary_key.columns] == ["month_start", "employee_id"]


def test_snapshot_stores_both_activity_endpoints() -> None:
    """Average headcount is (SUM(start) + SUM(end)) / 2. Without both flags stored,
    the denominator silently degrades to end-of-period headcount — which CLAUDE.md
    names as the single most common bug in HR analytics."""
    snapshot = Base.metadata.tables["fact_monthly_headcount_snapshot"]

    for column in ("active_at_month_start", "active_at_month_end"):
        assert column in snapshot.c, f"{column} is required for average-headcount denominators"
        assert not snapshot.c[column].nullable, f"{column} must not be nullable"


def test_attrition_numerator_flag_exists() -> None:
    snapshot = Base.metadata.tables["fact_monthly_headcount_snapshot"]

    assert "terminated_in_month" in snapshot.c
    assert not snapshot.c.terminated_in_month.nullable


def test_stage_events_can_measure_dwell_time() -> None:
    """The Sales bottleneck scenario (41 days at Interview vs 12 elsewhere) needs
    both endpoints; entry alone would force an ordered window function."""
    stage_event = Base.metadata.tables["fact_application_stage_event"]

    assert not stage_event.c.entered_on.nullable
    assert stage_event.c.exited_on.nullable, "NULL exited_on means still in stage"


def test_survey_open_text_is_optional_but_employee_is_not() -> None:
    """open_text is skippable; employee_id drives the engagement-to-attrition link."""
    response = Base.metadata.tables["fact_survey_response"]

    assert response.c.open_text.nullable
    assert not response.c.employee_id.nullable


def test_one_response_per_employee_per_survey() -> None:
    response = Base.metadata.tables["fact_survey_response"]
    unique_indexes = {
        tuple(c.name for c in index.columns) for index in response.indexes if index.unique
    }

    assert ("survey_id", "employee_id") in unique_indexes


def test_all_five_engagement_drivers_are_present() -> None:
    response = Base.metadata.tables["fact_survey_response"]
    drivers = {
        "driver_manager",
        "driver_growth",
        "driver_recognition",
        "driver_workload",
        "driver_belonging",
    }

    assert drivers <= set(response.c.keys())


def test_money_and_hours_are_never_float() -> None:
    """Binary floating point on currency produces totals that do not reconcile, and
    a metric that is off by a cent is indistinguishable from one that is wrong."""
    offenders = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, Float)
    ]

    assert offenders == [], f"use Numeric, not Float: {offenders}"


def test_comp_and_hours_columns_use_numeric() -> None:
    checks = [
        ("dim_employee", "comp_amount"),
        ("dim_job_level", "comp_band_min"),
        ("dim_job_level", "comp_band_max"),
        ("dim_requisition", "internal_cost"),
        ("dim_requisition", "external_cost"),
        ("fact_timesheet_week", "billable_hours"),
        ("fact_timesheet_week", "available_hours"),
        ("fact_department_revenue", "revenue_amount"),
    ]

    for table_name, column_name in checks:
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, Numeric), f"{table_name}.{column_name} must be Numeric"


def test_every_foreign_key_target_exists() -> None:
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            assert fk.column.table.name in Base.metadata.tables, (
                f"{table.name} points at unknown table {fk.column.table.name}"
            )


def test_absenteeism_denominator_is_available() -> None:
    """available_workdays comes from the date spine; it is not derivable otherwise."""
    assert "is_workday" in Base.metadata.tables["dim_date"].c


# One test per metric domain: the tables that domain's formulas read from must all
# exist. This is the guard that the coverage walk stays true as the schema evolves.
DOMAIN_TABLES = {
    "acquisition": {
        "dim_requisition",
        "dim_source",
        "fact_application",
        "fact_application_stage_event",
        "dim_employee",
        "fact_performance_review",
    },
    "retention": {
        "dim_employee",
        "fact_employment_event",
        "fact_monthly_headcount_snapshot",
        "fact_performance_review",
        "fact_flight_risk_score",
    },
    "engagement": {
        "dim_survey",
        "fact_survey_response",
        "fact_comment_theme",
        "fact_absence",
        "dim_date",
    },
    "productivity": {
        "fact_timesheet_week",
        "fact_goal",
        "fact_department_revenue",
        "fact_training",
        "fact_monthly_headcount_snapshot",
    },
}


def test_every_domain_has_its_source_tables() -> None:
    for domain, tables in DOMAIN_TABLES.items():
        missing = tables - set(Base.metadata.tables)
        assert not missing, f"{domain} metrics have no source table for: {sorted(missing)}"
