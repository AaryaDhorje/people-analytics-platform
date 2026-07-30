"""Talent acquisition: source, requisition, application, stage events.

The stage-event fact stores `entered_on` **and** `exited_on` rather than entry
alone. Dwell time per stage — the Sales bottleneck scenario, 41 days at Interview
against 12 elsewhere — is then a subtraction instead of an ordered window
function, and an application that re-enters a stage produces two honest rows
rather than a double-counted funnel step.
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
from app.models.enums import ApplicationStage, ChannelType, RequisitionStatus, pg_enum


class DimSource(Base):
    __tablename__ = "dim_source"
    __table_args__ = {
        "comment": "Hiring channels. The sourcing-decay scenario contrasts agency with referral."
    }

    source_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_type: Mapped[ChannelType] = mapped_column(
        pg_enum(ChannelType, "channel_type"), nullable=False
    )


class DimRequisition(Base):
    __tablename__ = "dim_requisition"
    __table_args__ = (
        Index("ix_dim_requisition_department", "department_id"),
        Index("ix_dim_requisition_status_opened", "status", "opened_date"),
        {
            "comment": (
                "410 requisitions. Costs live here because cost per hire is "
                "(internal_cost + external_cost) / hires_in_period at req grain."
            )
        },
    )

    requisition_id: Mapped[str] = mapped_column(String(12), primary_key=True, comment="R-0001")

    department_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_department.department_id"), nullable=False
    )
    location_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_location.location_id"), nullable=False
    )
    job_level_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_job_level.job_level_id"), nullable=False
    )
    hiring_manager_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[RequisitionStatus] = mapped_column(
        pg_enum(RequisitionStatus, "requisition_status"), nullable=False
    )
    opened_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Start of the time-to-fill clock."
    )
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    openings: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    internal_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Recruiter time, referral bonus, tooling."
    )
    external_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Agency fees, job board spend, advertising."
    )


class FactApplication(Base):
    __tablename__ = "fact_application"
    __table_args__ = (
        Index("ix_fact_application_requisition", "requisition_id"),
        Index("ix_fact_application_source", "source_id"),
        Index("ix_fact_application_first_date", "first_application_date"),
        {
            "comment": (
                "~9,200 applications, one row per candidate per requisition. "
                "Time to hire = offer_accepted_date - first_application_date."
            )
        },
    )

    application_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    requisition_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("dim_requisition.requisition_id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_source.source_id"), nullable=False
    )
    candidate_ref: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="Synthetic candidate handle, e.g. C-004821."
    )

    first_application_date: Mapped[date] = mapped_column(Date, nullable=False)

    #: Terminal stage reached. The funnel is counted from stage events; this column
    #: makes "how far did this candidate get" a single-column filter.
    final_stage: Mapped[ApplicationStage] = mapped_column(
        pg_enum(ApplicationStage, "application_stage"), nullable=False
    )

    offer_extended_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offer_accepted_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="Ends both the time-to-fill and time-to-hire clocks."
    )
    offer_declined_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rejected_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    hired_employee_id: Mapped[str | None] = mapped_column(
        String(12),
        ForeignKey("dim_employee.employee_id", ondelete="SET NULL"),
        nullable=True,
        comment="Links a hire back to its channel for quality of hire and cohort retention.",
    )


class FactApplicationStageEvent(Base):
    __tablename__ = "fact_application_stage_event"
    __table_args__ = (
        Index("ix_fact_stage_event_application", "application_id"),
        Index("ix_fact_stage_event_stage_entered", "stage", "entered_on"),
        {
            "comment": (
                "One row per application per stage entry. exited_on is NULL while the "
                "candidate sits in that stage, which is what makes the pipeline "
                "bottleneck measurable."
            )
        },
    )

    stage_event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    application_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fact_application.application_id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[ApplicationStage] = mapped_column(
        pg_enum(ApplicationStage, "application_stage"), nullable=False
    )

    entered_on: Mapped[date] = mapped_column(Date, nullable=False)
    exited_on: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="NULL = still in this stage."
    )
