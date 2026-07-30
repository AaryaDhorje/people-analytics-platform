"""Generate the warehouse. Entry point: `python -m seed.generate`.

    python -m seed.generate --reset              # full volume
    python -m seed.generate --reset --scale 0.1  # fast iteration
    python -m seed.generate --reset --no-validate

Determinism is load-bearing and `seed=42` alone does not deliver it. The surrogate
keys are identity columns, so a second run without `RESTART IDENTITY` would produce
the same rows under different ids and phase 3's fixtures would break. `--reset`
therefore truncates with `RESTART IDENTITY CASCADE`, and every table whose ids this
module supplies explicitly has its sequence resynced afterwards — otherwise phase 6's
first insert into a table seeded here would collide on a primary key.
"""

import argparse
import random
import sys
import time
from collections.abc import Sequence

import numpy as np
from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    DimDate,
    DimDepartment,
    DimEmployee,
    DimJobLevel,
    DimLocation,
    DimRequisition,
    DimSource,
    DimSurvey,
    FactAbsence,
    FactApplication,
    FactApplicationStageEvent,
    FactCommentTheme,
    FactDepartmentRevenue,
    FactEmploymentEvent,
    FactFlightRiskScore,
    FactGoal,
    FactMonthlyHeadcountSnapshot,
    FactPerformanceReview,
    FactSurveyResponse,
    FactTimesheetWeek,
    FactTraining,
)
from seed import people as people_mod
from seed import productivity as productivity_mod
from seed.engagement import build_survey_responses
from seed.recruiting import build_recruiting
from seed.reference import (
    DEPARTMENT_IDS,
    DEPARTMENTS,
    JOB_LEVEL_IDS,
    JOB_LEVELS,
    LOCATION_IDS,
    LOCATIONS,
    SOURCE_IDS,
    SOURCES,
    survey_rows,
)
from seed.spine import date_rows

SEED = 42

#: Truncated in one statement. CASCADE handles the FK graph; RESTART IDENTITY is what
#: makes ids reproducible across runs.
ALL_TABLES: tuple[str, ...] = (
    "fact_comment_theme",
    "fact_flight_risk_score",
    "fact_application_stage_event",
    "fact_application",
    "fact_survey_response",
    "fact_timesheet_week",
    "fact_goal",
    "fact_training",
    "fact_absence",
    "fact_performance_review",
    "fact_department_revenue",
    "fact_monthly_headcount_snapshot",
    "fact_employment_event",
    "dim_requisition",
    "dim_employee",
    "dim_survey",
    "dim_source",
    "dim_job_level",
    "dim_location",
    "dim_department",
    "dim_date",
)

#: Tables where this module supplies primary keys explicitly, so their sequences must
#: be advanced past the highest inserted value.
EXPLICIT_ID_COLUMNS: tuple[tuple[str, str], ...] = (
    ("dim_department", "department_id"),
    ("dim_location", "location_id"),
    ("dim_job_level", "job_level_id"),
    ("dim_source", "source_id"),
    ("dim_survey", "survey_id"),
    ("fact_application", "application_id"),
    ("fact_application_stage_event", "stage_event_id"),
    ("fact_survey_response", "response_id"),
    ("fact_timesheet_week", "timesheet_id"),
    ("fact_goal", "goal_id"),
    ("fact_absence", "absence_id"),
    ("fact_performance_review", "review_id"),
    ("fact_training", "training_id"),
    ("fact_employment_event", "event_id"),
)


def reset(session: Session) -> None:
    session.execute(text(f"TRUNCATE {', '.join(ALL_TABLES)} RESTART IDENTITY CASCADE"))
    session.commit()


def resync_sequences(session: Session) -> None:
    for table_name, column in EXPLICIT_ID_COLUMNS:
        sequence = session.execute(
            text("SELECT pg_get_serial_sequence(:table, :column)"),
            {"table": table_name, "column": column},
        ).scalar()
        if not sequence:
            continue
        session.execute(
            text(
                f"SELECT setval('{sequence}', "  # noqa: S608 - identifiers come from a fixed tuple
                f"GREATEST((SELECT COALESCE(MAX({column}), 0) FROM {table_name}), 1))"
            )
        )
    session.commit()


def bulk_insert(session: Session, table: object, rows: Sequence[dict[str, object]]) -> int:
    """Insert in batches. Every dict must carry the same keys — executemany requires it."""
    if not rows:
        return 0
    batch_size = 5_000
    for start in range(0, len(rows), batch_size):
        session.execute(insert(table), list(rows[start : start + batch_size]))  # type: ignore[arg-type]
    session.commit()
    return len(rows)


def _dimension_rows() -> list[tuple[object, list[dict[str, object]], str]]:
    departments = [
        {"department_id": DEPARTMENT_IDS[str(row["code"])], **row} for row in DEPARTMENTS
    ]
    locations = [{"location_id": LOCATION_IDS[row["code"]], **row} for row in LOCATIONS]
    levels = [{"job_level_id": JOB_LEVEL_IDS[str(row["code"])], **row} for row in JOB_LEVELS]
    sources = [{"source_id": SOURCE_IDS[str(row["code"])], **row} for row in SOURCES]
    return [
        (DimDate, date_rows(), "dim_date"),
        (DimDepartment, departments, "dim_department"),
        (DimLocation, locations, "dim_location"),
        (DimJobLevel, levels, "dim_job_level"),
        (DimSource, sources, "dim_source"),
        (DimSurvey, survey_rows(), "dim_survey"),
    ]


def generate(scale: float, do_reset: bool) -> dict[str, int]:
    """Build every table and return row counts by table name."""
    # Both RNGs seeded: numpy drives generation, stdlib `random` is seeded so any
    # future use cannot silently reintroduce nondeterminism.
    random.seed(SEED)
    rng = np.random.default_rng(SEED)

    counts: dict[str, int] = {}
    started = time.perf_counter()

    with SessionLocal() as session:
        if do_reset:
            print("resetting tables (TRUNCATE ... RESTART IDENTITY CASCADE)")
            reset(session)

        print("building population")
        population = people_mod.build_population(rng, scale)
        people_mod.assign_mobility(population, rng)
        people_mod.assign_terminations(population, rng, scale)
        # Mobility events were appended before terminations, so re-sort the timelines.
        for person in population:
            person.changes.sort(key=lambda change: change.day)

        print("building recruiting, engagement, productivity")
        recruiting = build_recruiting(population, rng, scale)
        responses = build_survey_responses(population, rng)
        productivity = productivity_mod.build_productivity(population, rng, scale)

        print("inserting")
        for table, rows, name in _dimension_rows():
            counts[name] = bulk_insert(session, table, rows)

        # dim_employee must be inserted managers-first: manager_id is a self-reference
        # and the constraint is not deferrable, so a report inserted before its manager
        # would fail. build_population appends CEO -> heads -> managers -> ICs, so the
        # natural order is already correct.
        counts["dim_employee"] = bulk_insert(
            session, DimEmployee, people_mod.employee_rows(population)
        )
        counts["fact_employment_event"] = bulk_insert(
            session, FactEmploymentEvent, people_mod.employment_event_rows(population)
        )
        counts["fact_monthly_headcount_snapshot"] = bulk_insert(
            session, FactMonthlyHeadcountSnapshot, people_mod.snapshot_rows(population)
        )

        counts["dim_requisition"] = bulk_insert(session, DimRequisition, recruiting.requisitions)
        counts["fact_application"] = bulk_insert(session, FactApplication, recruiting.applications)
        counts["fact_application_stage_event"] = bulk_insert(
            session, FactApplicationStageEvent, recruiting.stage_events
        )

        counts["fact_survey_response"] = bulk_insert(session, FactSurveyResponse, responses)

        counts["fact_timesheet_week"] = bulk_insert(
            session, FactTimesheetWeek, productivity.timesheets
        )
        counts["fact_goal"] = bulk_insert(session, FactGoal, productivity.goals)
        counts["fact_department_revenue"] = bulk_insert(
            session, FactDepartmentRevenue, productivity.revenue
        )
        counts["fact_training"] = bulk_insert(session, FactTraining, productivity.training)
        counts["fact_absence"] = bulk_insert(session, FactAbsence, productivity.absences)
        counts["fact_performance_review"] = bulk_insert(
            session, FactPerformanceReview, productivity.reviews
        )

        # Written by later phases; listed so the report shows them as deliberately empty.
        counts["fact_flight_risk_score"] = 0
        counts["fact_comment_theme"] = 0
        _ = (FactFlightRiskScore, FactCommentTheme)

        resync_sequences(session)

    elapsed = time.perf_counter() - started
    total = sum(counts.values())
    print(f"\ninserted {total:,} rows across {len(counts)} tables in {elapsed:.1f}s")
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic HR warehouse data.")
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Fraction of full volume. 0.1 gives a fast iteration database.",
    )
    parser.add_argument(
        "--reset", action="store_true", help="Truncate all tables and restart identities first."
    )
    parser.add_argument(
        "--no-validate", action="store_true", help="Skip the scenario validation report."
    )
    args = parser.parse_args(argv)

    if not 0.01 <= args.scale <= 1.0:
        parser.error("--scale must be between 0.01 and 1.0")

    counts = generate(scale=args.scale, do_reset=args.reset)

    if args.no_validate:
        return 0

    from seed.validate import run_validation

    return 0 if run_validation(counts=counts, scale=args.scale) else 1


if __name__ == "__main__":
    sys.exit(main())
