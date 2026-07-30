"""Productivity: timesheets, goals, revenue, training.

Three of these exist because the coverage walk found metrics in docs/METRICS.md
with no source table in the phase-1 fact list: Revenue per FTE had no revenue,
Output per Head had no output measure, and Training Hours had no training records.

"Team" grains four metrics in this domain but is not a phase-1 dimension, so team
maps to department. "Sprint" for Output per Head maps to the timesheet week.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import GoalStatus, OutputType, pg_enum


class FactTimesheetWeek(Base):
    __tablename__ = "fact_timesheet_week"
    __table_args__ = (
        Index("ix_timesheet_employee_week", "employee_id", "week_start", unique=True),
        Index("ix_timesheet_department_week", "department_id", "week_start"),
        Index("ix_timesheet_week", "week_start"),
        {
            "comment": (
                "One row per employee per week for billable departments. Hours are "
                "stored, never rates: overtime rate and utilization both divide at "
                "read time so the denominator stays visible."
            )
        },
    )

    timesheet_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    employee_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("dim_department.department_id"),
        nullable=False,
        comment="As-of-week department; also the team grain.",
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False, comment="Monday")

    billable_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    non_billable_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    available_hours: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, comment="Capacity for the week; utilization denominator."
    )

    #: Output per Head. Kept on the timesheet because the grain already matches the
    #: sprint cadence, which avoids a fifth productivity table for two columns.
    output_units: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True, comment="Tickets closed, story points, or deals."
    )
    output_type: Mapped[OutputType | None] = mapped_column(
        pg_enum(OutputType, "output_type"), nullable=True
    )


class FactGoal(Base):
    __tablename__ = "fact_goal"
    __table_args__ = (
        Index("ix_fact_goal_employee_quarter", "employee_id", "quarter_start"),
        Index("ix_fact_goal_department_quarter", "department_id", "quarter_start"),
        {
            "comment": (
                "~2,400 goals. Attainment is AVG(actual / target) capped at 1.5 — the "
                "cap is applied in the metric layer, not stored."
            )
        },
    )

    goal_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    employee_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_department.department_id"), nullable=False
    )
    quarter_start: Mapped[date] = mapped_column(Date, nullable=False)

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    target_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Must be non-zero; the metric guards division."
    )
    actual_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[GoalStatus] = mapped_column(pg_enum(GoalStatus, "goal_status"), nullable=False)


class FactDepartmentRevenue(Base):
    __tablename__ = "fact_department_revenue"
    __table_args__ = {
        "comment": (
            "Revenue by department by quarter. Added because Revenue per FTE is in "
            "METRICS.md but had no source table in the phase-1 fact list."
        )
    }

    department_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_department.department_id"), primary_key=True
    )
    quarter_start: Mapped[date] = mapped_column(Date, primary_key=True)

    revenue_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class FactTraining(Base):
    __tablename__ = "fact_training"
    __table_args__ = (
        Index("ix_fact_training_employee", "employee_id"),
        Index("ix_fact_training_assigned", "assigned_on"),
        {
            "comment": (
                "One row per assigned course. completed_on is NULL while incomplete, "
                "which is what makes completion rate a count of non-nulls rather than "
                "a stored percentage."
            )
        },
    )

    training_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    employee_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="CASCADE"), nullable=False
    )
    course_code: Mapped[str] = mapped_column(String(24), nullable=False)
    course_name: Mapped[str] = mapped_column(String(96), nullable=False)

    assigned_on: Mapped[date] = mapped_column(Date, nullable=False)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    hours: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, comment="Hours spent; 0 if assigned but never started."
    )
