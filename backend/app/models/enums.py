"""Enumerations shared across the schema.

Every enum is a `StrEnum`, so a value round-trips as a readable string in JSON,
in raw SQL, and in the generated SQL the NL→SQL feature returns to the user. Use
`pg_enum()` to map one onto a column — it stores the lowercase *value*, not the
Python member name, which is what makes hand-written SQL against these columns
readable.
"""

from enum import StrEnum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

E = TypeVar("E", bound=StrEnum)


def pg_enum(enum_cls: type[E], name: str) -> SAEnum:
    """Map a StrEnum to a native PostgreSQL enum type storing member values.

    Without `values_callable`, SQLAlchemy stores member *names* (`VOLUNTARY`),
    which makes every hand-written query shout and diverges from what the API
    returns.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda members: [member.value for member in members],
    )


class EventType(StrEnum):
    """A transition in an employee's record. Drives internal mobility and tenure."""

    HIRE = "hire"
    PROMOTION = "promotion"
    LATERAL_TRANSFER = "lateral_transfer"
    MANAGER_CHANGE = "manager_change"
    COMP_CHANGE = "comp_change"
    TERMINATION = "termination"


class TerminationType(StrEnum):
    """Splits attrition. Regretted attrition is a voluntary exit with a high rating."""

    VOLUNTARY = "voluntary"
    INVOLUNTARY = "involuntary"


class ApplicationStage(StrEnum):
    """Funnel stages, in order. Conversion is stage_n / stage_n-1 across these."""

    APPLIED = "applied"
    SCREEN = "screen"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


#: Funnel order for conversion maths. REJECTED and WITHDRAWN are terminal, not stages.
FUNNEL_ORDER: tuple[ApplicationStage, ...] = (
    ApplicationStage.APPLIED,
    ApplicationStage.SCREEN,
    ApplicationStage.INTERVIEW,
    ApplicationStage.OFFER,
    ApplicationStage.HIRED,
)


class RequisitionStatus(StrEnum):
    """Requisition aging counts `OPEN` reqs older than 60 days."""

    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class ChannelType(StrEnum):
    """Hiring channel. The sourcing-decay scenario contrasts AGENCY with REFERRAL."""

    REFERRAL = "referral"
    AGENCY = "agency"
    JOB_BOARD = "job_board"
    INBOUND = "inbound"
    CAMPUS = "campus"
    INTERNAL = "internal"


class AbsenceType(StrEnum):
    """Only UNPLANNED and SICK count toward absenteeism; PTO is planned time off."""

    UNPLANNED = "unplanned"
    SICK = "sick"
    PTO = "pto"
    LEAVE = "leave"


class GoalStatus(StrEnum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    COMPLETE = "complete"
    MISSED = "missed"


class OutputType(StrEnum):
    """What a team's Output per Head is measured in — varies by department."""

    TICKETS = "tickets"
    STORY_POINTS = "story_points"
    DEALS = "deals"


class Sentiment(StrEnum):
    """Claude-assigned sentiment on an extracted survey-comment theme."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class RiskBand(StrEnum):
    """Banding of a flight-risk score. Only HIGH earns the reserved accent colour."""

    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"
