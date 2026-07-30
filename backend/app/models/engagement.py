"""Engagement: surveys, responses, and Claude-extracted comment themes.

Driver scores are stored **raw on a 1-5 scale** and normalized to 0-100 in the
views via `(raw - 1) / 4.0 * 100`. The planted scenarios are written in points on
the 0-100 scale — "28 points below company mean", "Belonging and Growth drop 15
points" — so normalization has to happen in exactly one place or those numbers
stop reconciling.

`employee_id` is NOT NULL: the engagement-to-attrition link and the driver
breakdown by manager both require it. A real deployment would anonymize; this data
is synthetic. Small-N suppression, matching the "min 8 reports" rule METRICS.md
already sets for attrition by manager, belongs in the phase-3 views.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import Sentiment, pg_enum


class DimSurvey(Base):
    __tablename__ = "dim_survey"
    __table_args__ = {"comment": "6 quarterly engagement surveys at ~70% participation."}

    survey_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, comment="Q1-Y1")
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    quarter_start: Mapped[date] = mapped_column(Date, nullable=False)
    opens_on: Mapped[date] = mapped_column(Date, nullable=False)
    closes_on: Mapped[date] = mapped_column(Date, nullable=False)


class FactSurveyResponse(Base):
    __tablename__ = "fact_survey_response"
    __table_args__ = (
        Index("ix_survey_response_survey_employee", "survey_id", "employee_id", unique=True),
        Index("ix_survey_response_employee", "employee_id"),
        {
            "comment": (
                "One response per employee per survey. Participation rate is "
                "responses / eligible employees, where eligibility comes from the "
                "monthly headcount snapshot."
            )
        },
    )

    response_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    survey_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dim_survey.survey_id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("dim_employee.employee_id", ondelete="CASCADE"), nullable=False
    )
    submitted_on: Mapped[date] = mapped_column(Date, nullable=False)

    enps_score: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="0-10. Promoters 9-10, passives 7-8, detractors 0-6.",
    )

    #: The five engagement drivers, raw 1-5. Normalized to 0-100 in views only.
    driver_manager: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    driver_growth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    driver_recognition: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    driver_workload: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    driver_belonging: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    open_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Free-text comment. NULL when the respondent skipped it."
    )


class FactCommentTheme(Base):
    __tablename__ = "fact_comment_theme"
    __table_args__ = (
        Index("ix_comment_theme_response", "survey_response_id"),
        Index("ix_comment_theme_theme", "theme"),
        {
            "comment": (
                "Claude-extracted themes, written in phase 6 by a batch Haiku job. "
                "Cached here so the dashboard never blocks on a live API call, and so "
                "a failed call degrades to stale themes rather than an error."
            )
        },
    )

    comment_theme_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    survey_response_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fact_survey_response.response_id", ondelete="CASCADE"),
        nullable=False,
    )

    theme: Mapped[str] = mapped_column(String(64), nullable=False)
    sentiment: Mapped[Sentiment] = mapped_column(pg_enum(Sentiment, "sentiment"), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, comment="0.000-1.000"
    )

    model: Mapped[str] = mapped_column(
        String(48), nullable=False, comment="Model id that produced this, for auditability."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
