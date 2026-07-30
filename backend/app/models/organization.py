"""Organizational dimensions: department, location, job level, employee.

`dim_employee` is a **Type-1 dimension** — it holds current state only. History
lives in `fact_employment_event`, and as-of-month state lives in
`fact_monthly_headcount_snapshot`. That split is deliberate: attrition by manager
must attribute an exit to the manager at the time of exit, not to whoever holds
the reports today.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import TerminationType, pg_enum


class DimDepartment(Base):
    __tablename__ = "dim_department"
    __table_args__ = {
        "comment": "8 departments. Also serves as the 'team' grain for productivity metrics."
    }

    department_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    is_billable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="Billable departments file timesheets; utilization applies only to these.",
    )
    carries_revenue: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="Whether revenue per FTE is meaningful for this dept."
    )


class DimLocation(Base):
    __tablename__ = "dim_location"
    __table_args__ = {"comment": "4 locations."}

    location_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)


class DimJobLevel(Base):
    __tablename__ = "dim_job_level"
    __table_args__ = {
        "comment": (
            "6 job levels. The comp band is here so the flight-risk component "
            "'comp percentile vs band' needs no separate compensation table."
        )
    }

    job_level_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True, comment="L1..L6")
    name: Mapped[str] = mapped_column(String(48), nullable=False)
    rank: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="1 = most junior; orders levels for span of control."
    )

    comp_band_min: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    comp_band_max: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_manager_level: Mapped[bool] = mapped_column(Boolean, nullable=False)


class DimEmployee(Base):
    __tablename__ = "dim_employee"
    __table_args__ = (
        Index("ix_dim_employee_manager", "manager_id"),
        Index("ix_dim_employee_department", "department_id"),
        Index("ix_dim_employee_hire_date", "hire_date"),
        Index("ix_dim_employee_termination_date", "termination_date"),
        {
            "comment": (
                "~1,850 employee records over 36 months. Type-1: current state only. "
                "History is in fact_employment_event; as-of-month state is in the "
                "monthly headcount snapshot."
            )
        },
    )

    #: Text key so IDs are legible in the demo. Managers keep an `M-` prefix because
    #: the bad-manager scenario names M-114 and it is read aloud in the Loom.
    #: Individual contributors are `E-####`. One ID space, no collision.
    employee_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(96), nullable=False)

    manager_id: Mapped[str | None] = mapped_column(
        String(12),
        ForeignKey("dim_employee.employee_id", ondelete="SET NULL"),
        nullable=True,
        comment="Self-reference. NULL for the top of the org.",
    )

    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="NULL means currently active."
    )
    termination_type: Mapped[TerminationType | None] = mapped_column(
        pg_enum(TerminationType, "termination_type"),
        nullable=True,
        comment="Set if and only if termination_date is set.",
    )
    termination_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    department_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_department.department_id"), nullable=False
    )
    location_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_location.location_id"), nullable=False
    )
    job_level_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_job_level.job_level_id"), nullable=False
    )
    source_id: Mapped[int | None] = mapped_column(
        SmallInteger,
        ForeignKey("dim_source.source_id"),
        nullable=True,
        comment=(
            "Channel this person was hired through. Drives source effectiveness, "
            "quality of hire, and cohort retention by source. NULL for founding staff."
        ),
    )

    comp_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fte: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, comment="1.000 = full time. Denominator for revenue per FTE."
    )

    #: The only ORM relationships in the schema. Metrics read through SQL views, so
    #: further relationships would be dead weight — but the self-reference is worth
    #: mapping because span-of-control and the manager rollup both walk it.
    manager: Mapped["DimEmployee | None"] = relationship(
        remote_side=[employee_id], back_populates="reports"
    )
    reports: Mapped[list["DimEmployee"]] = relationship(back_populates="manager")
