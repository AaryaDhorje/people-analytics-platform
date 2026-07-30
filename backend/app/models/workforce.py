"""Retention facts: employment events, the monthly snapshot, absence, reviews, risk.

`fact_monthly_headcount_snapshot` is the most important table in the schema. It
carries `active_at_month_start` and `active_at_month_end` as separate booleans, so
average headcount is

    (SUM(active_at_month_start) + SUM(active_at_month_end)) / 2.0

with no lag join and no window function. CLAUDE.md names the average-headcount
denominator as the single most common bug in HR analytics; storing both endpoints
makes the correct denominator the easy one to reach for, which is cheaper than
catching the mistake 31 times in review.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import AbsenceType, EventType, RiskBand, TerminationType, pg_enum


class FactEmploymentEvent(Base):
    __tablename__ = "fact_employment_event"
    __table_args__ = (
        Index("ix_fact_employment_event_employee_date", "employee_id", "event_date"),
        Index("ix_fact_employment_event_type_date", "event_type", "event_date"),
        {
            "comment": (
                "Every transition in an employee's record. from_*/to_* columns make "
                "promotions distinguishable from lateral transfers, which is what "
                "internal mobility rate requires."
            )
        },
    )

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    employee_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="CASCADE"), nullable=False
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_type: Mapped[EventType] = mapped_column(pg_enum(EventType, "event_type"), nullable=False)

    from_department_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("dim_department.department_id"), nullable=True
    )
    to_department_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("dim_department.department_id"), nullable=True
    )
    from_job_level_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("dim_job_level.job_level_id"), nullable=True
    )
    to_job_level_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("dim_job_level.job_level_id"), nullable=True
    )
    from_manager_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="SET NULL"), nullable=True
    )
    to_manager_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="SET NULL"), nullable=True
    )
    from_comp_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    to_comp_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    termination_type: Mapped[TerminationType | None] = mapped_column(
        pg_enum(TerminationType, "termination_type"),
        nullable=True,
        comment="Set only on TERMINATION events.",
    )


class FactMonthlyHeadcountSnapshot(Base):
    __tablename__ = "fact_monthly_headcount_snapshot"
    __table_args__ = (
        Index("ix_snapshot_month", "month_start"),
        Index("ix_snapshot_department_month", "department_id", "month_start"),
        Index("ix_snapshot_manager_month", "manager_id", "month_start"),
        {
            "comment": (
                "One row per employee per month, carrying as-of-month state so no "
                "month-grain metric has to replay the event log. Both activity "
                "endpoints are stored so average headcount is exact."
            )
        },
    )

    month_start: Mapped[date] = mapped_column(Date, primary_key=True)
    employee_id: Mapped[str] = mapped_column(
        String(12),
        ForeignKey("dim_employee.employee_id", ondelete="CASCADE"),
        primary_key=True,
    )

    #: As-of-month attributes. These are the reason attrition-by-manager attributes an
    #: exit to the manager who held the report at the time, not to today's manager.
    department_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_department.department_id"), nullable=False
    )
    location_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_location.location_id"), nullable=False
    )
    job_level_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_job_level.job_level_id"), nullable=False
    )
    manager_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="SET NULL"), nullable=True
    )

    comp_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fte: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    tenure_months: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Whole months from hire_date to this month_start."
    )

    active_at_month_start: Mapped[bool] = mapped_column(Boolean, nullable=False)
    active_at_month_end: Mapped[bool] = mapped_column(Boolean, nullable=False)

    terminated_in_month: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="Numerator flag for attrition. Denominator is average of the two active flags.",
    )
    hired_in_month: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FactAbsence(Base):
    __tablename__ = "fact_absence"
    __table_args__ = (
        Index("ix_fact_absence_employee_date", "employee_id", "absence_date"),
        {"comment": "One row per absence occurrence. Only unplanned/sick count as absenteeism."},
    )

    absence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    employee_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="CASCADE"), nullable=False
    )
    absence_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, comment="Supports half days."
    )
    absence_type: Mapped[AbsenceType] = mapped_column(
        pg_enum(AbsenceType, "absence_type"), nullable=False
    )
    is_unplanned: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="Denormalized from absence_type so the absenteeism numerator is one predicate.",
    )


class FactPerformanceReview(Base):
    __tablename__ = "fact_performance_review"
    __table_args__ = (
        Index("ix_fact_review_employee_date", "employee_id", "review_date"),
        {
            "comment": (
                "Ratings 1-5. Regretted attrition needs the LAST rating before a "
                "voluntary exit; quality of hire needs the rating at day 180."
            )
        },
    )

    review_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    employee_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="SET NULL"), nullable=True
    )

    review_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    review_date: Mapped[date] = mapped_column(Date, nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="1-5")


class FactFlightRiskScore(Base):
    __tablename__ = "fact_flight_risk_score"
    __table_args__ = (
        Index("ix_flight_risk_month_score", "as_of_month", "score"),
        {
            "comment": (
                "Computed in phase 3 by a transparent weighted score, not a model. "
                "`components` holds each contributing factor and its weight so the "
                "score can be explained per employee in the demo."
            )
        },
    )

    employee_id: Mapped[str] = mapped_column(
        String(12),
        ForeignKey("dim_employee.employee_id", ondelete="CASCADE"),
        primary_key=True,
    )
    as_of_month: Mapped[date] = mapped_column(Date, primary_key=True)

    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, comment="0-100")
    band: Mapped[RiskBand] = mapped_column(pg_enum(RiskBand, "risk_band"), nullable=False)
    components: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Per-factor value, weight, and contribution. Drives the expandable reason table.",
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
