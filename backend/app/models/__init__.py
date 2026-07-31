"""SQLAlchemy ORM models — the star schema.

8 dimensions and 13 facts. Every model must be imported here: Alembic's
autogenerate compares the database against `Base.metadata`, so a model that is not
imported is invisible to it and the next revision will generate a `DROP TABLE` for
its table.

Design notes worth knowing before adding to this package:

- `dim_employee` is Type-1 (current state only). History is `fact_employment_event`;
  as-of-month state is `fact_monthly_headcount_snapshot`.
- Rates are never stored. Facts carry numerators and denominators; the division
  happens in a view or the metric layer so the denominator stays auditable.
- Attrition denominators are AVERAGE headcount — the snapshot stores both
  `active_at_month_start` and `active_at_month_end` to make that the natural
  computation.
"""

from app.db import Base
from app.models.ai import AiCache
from app.models.calendar import DimDate
from app.models.engagement import DimSurvey, FactCommentTheme, FactSurveyResponse
from app.models.enums import (
    FUNNEL_ORDER,
    AbsenceType,
    ApplicationStage,
    ChannelType,
    EventType,
    GoalStatus,
    OutputType,
    RequisitionStatus,
    RiskBand,
    Sentiment,
    TerminationType,
)
from app.models.organization import DimDepartment, DimEmployee, DimJobLevel, DimLocation
from app.models.productivity import (
    FactDepartmentRevenue,
    FactGoal,
    FactTimesheetWeek,
    FactTraining,
)
from app.models.recruiting import (
    DimRequisition,
    DimSource,
    FactApplication,
    FactApplicationStageEvent,
)
from app.models.workforce import (
    FactAbsence,
    FactEmploymentEvent,
    FactFlightRiskScore,
    FactMonthlyHeadcountSnapshot,
    FactPerformanceReview,
)

__all__ = [
    "FUNNEL_ORDER",
    "AiCache",
    "AbsenceType",
    "ApplicationStage",
    "Base",
    "ChannelType",
    "DimDate",
    "DimDepartment",
    "DimEmployee",
    "DimJobLevel",
    "DimLocation",
    "DimRequisition",
    "DimSource",
    "DimSurvey",
    "EventType",
    "FactAbsence",
    "FactApplication",
    "FactApplicationStageEvent",
    "FactCommentTheme",
    "FactDepartmentRevenue",
    "FactEmploymentEvent",
    "FactFlightRiskScore",
    "FactGoal",
    "FactMonthlyHeadcountSnapshot",
    "FactPerformanceReview",
    "FactSurveyResponse",
    "FactTimesheetWeek",
    "FactTraining",
    "GoalStatus",
    "OutputType",
    "RequisitionStatus",
    "RiskBand",
    "Sentiment",
    "TerminationType",
]
