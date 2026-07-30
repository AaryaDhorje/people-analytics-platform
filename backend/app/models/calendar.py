"""The date spine.

Every period-grain metric joins here rather than calling date functions inline, so
"month" and "quarter" mean exactly one thing across all 31 metrics. `is_workday`
exists because Absenteeism's denominator — available workdays — is not derivable
from a termination date and a calendar alone.
"""

from datetime import date

from sqlalchemy import Boolean, Date, Index, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DimDate(Base):
    __tablename__ = "dim_date"
    __table_args__ = (
        Index("ix_dim_date_month_start", "month_start"),
        Index("ix_dim_date_quarter_start", "quarter_start"),
        Index("ix_dim_date_week_start", "week_start"),
        {"comment": "One row per calendar day across the 36-month window."},
    )

    day: Mapped[date] = mapped_column(Date, primary_key=True)

    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    quarter: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="1-4")
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="1-12")

    #: Period anchors. Metrics group by these instead of date_trunc(), so a month
    #: boundary is defined in one place.
    month_start: Mapped[date] = mapped_column(Date, nullable=False)
    month_end: Mapped[date] = mapped_column(Date, nullable=False)
    quarter_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, comment="Monday")

    iso_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="1=Mon, 7=Sun")

    is_workday: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="Mon-Fri and not a holiday. Denominator for absenteeism.",
    )
    is_month_end: Mapped[bool] = mapped_column(Boolean, nullable=False)

    tenure_day_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Days since the start of the spine; eases date maths."
    )
