"""Flight risk: a transparent weighted score, deliberately not a model.

docs/METRICS.md specifies "Logistic-style weighted score: tenure band, months since last
promotion, engagement delta, manager attrition rate, comp percentile vs band". Five
components, fixed weights summing to 1.0, each scored 0-100 and each explainable in one
sentence. No training, no coefficients fitted to anything, nothing that has to be taken on
trust.

That constraint is the point rather than a limitation. A gradient-boosted model would
score better on a benchmark nobody in the room can see, and worse on the only question
that matters live: *why is this person on the list?* Every component here answers that in
plain English, and `explain()` returns those sentences alongside the numbers.

The scoring functions are pure — they take numbers and return numbers, with no database
access — so the weighting can be tested exhaustively without a warehouse.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.metrics.tables import v_flight_risk_inputs
from app.models import FactFlightRiskScore
from app.models.enums import RiskBand

#: Weights sum to exactly 1.0 — asserted by a test, because a drifting total silently
#: rescales every score without changing any single component.
WEIGHTS: dict[str, float] = {
    "tenure": 0.20,
    "promotion_gap": 0.20,
    "engagement_delta": 0.25,
    "manager_attrition": 0.20,
    "comp_percentile": 0.15,
}

#: Band thresholds. Only HIGH earns the reserved accent colour in the UI, so the boundary
#: at 70 is the one that decides what a viewer reads as urgent.
BAND_THRESHOLDS: tuple[tuple[float, RiskBand], ...] = (
    (25.0, RiskBand.LOW),
    (50.0, RiskBand.MODERATE),
    (70.0, RiskBand.ELEVATED),
)

#: Used where a signal is genuinely unknown rather than absent. Never having answered a
#: survey is not evidence of disengagement.
NEUTRAL = 50.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# --- Components -------------------------------------------------------------


def score_tenure(tenure_months: int) -> float:
    """Risk peaks between one and two years.

    New joiners are still invested in the decision they just made; people past four years
    have usually chosen to stay. The 12-24 month window is where the original reasons for
    joining have worn off and the next move starts to look attractive.
    """
    if tenure_months < 6:
        return 20.0
    if tenure_months < 12:
        return 45.0
    if tenure_months < 24:
        return 100.0
    if tenure_months < 48:
        return 55.0
    return 25.0


def score_promotion_gap(months_since_promotion: int) -> float:
    """Rises with time since the last move, sharply past two years."""
    if months_since_promotion < 12:
        return 10.0
    if months_since_promotion < 24:
        return 35.0
    if months_since_promotion < 36:
        return 70.0
    return 100.0


def score_engagement_delta(
    employee_raw_index: float | None, department_raw_index: float | None
) -> float:
    """How far below their department's mean this person scored, on the raw 1-5 scale.

    Compared against the department rather than the company: scoring 3.0 among peers who
    average 3.1 is unremarkable, and scoring 3.0 among peers who average 4.2 is a signal.

    A missing response is NEUTRAL, not zero. Scoring silence as disengagement would put
    every new joiner near the top of the list.
    """
    if employee_raw_index is None or department_raw_index is None:
        return NEUTRAL
    # Raw scale is 1-5, so a one-point gap is large. 25 points of score per raw point puts
    # a full point below the mean at 75 and a point above at 25.
    delta = float(department_raw_index) - float(employee_raw_index)
    return _clamp(NEUTRAL + delta * 25.0)


def score_manager_attrition(
    manager_terminations: float,
    manager_headcount_months: float,
    company_terminations: float,
    company_headcount_months: float,
) -> float:
    """The manager's trailing-12-month attrition against the company's.

    A team losing people at twice the company rate is a signal about the team, whatever
    the individual's own answers say. This is the component that makes M-114's reports
    surface without anyone having named M-114.
    """
    if not manager_headcount_months or not company_headcount_months:
        return 40.0
    manager_rate = float(manager_terminations) * 12.0 / float(manager_headcount_months)
    company_rate = float(company_terminations) * 12.0 / float(company_headcount_months)
    if company_rate <= 0:
        return 40.0
    # Parity with the company scores 40; 2.5x the company rate saturates at 100.
    return _clamp(manager_rate / company_rate * 40.0)


def score_comp_percentile(comp_amount: float, band_min: float, band_max: float) -> float:
    """Position in the pay band, inverted — the bottom of the band is the risk."""
    span = float(band_max) - float(band_min)
    if span <= 0:
        return NEUTRAL
    percentile = _clamp((float(comp_amount) - float(band_min)) / span, 0.0, 1.0)
    return (1.0 - percentile) * 100.0


def band_for(score: float) -> RiskBand:
    for threshold, band in BAND_THRESHOLDS:
        if score < threshold:
            return band
    return RiskBand.HIGH


# --- Scoring ----------------------------------------------------------------


@dataclass(frozen=True)
class RiskScore:
    employee_id: str
    as_of_month: date
    score: float
    band: RiskBand
    components: dict[str, dict[str, float]]

    def explain(self) -> list[str]:
        """One plain sentence per component, ordered by how much it contributed.

        This is what the Loom reads aloud and what phase 6's narrative endpoint expands.
        """
        ordered = sorted(
            self.components.items(), key=lambda item: item[1]["contribution"], reverse=True
        )
        return [
            f"{_COMPONENT_LABELS[name]}: {values['score']:.0f}/100 "
            f"(weight {values['weight']:.0%}, contributing {values['contribution']:.1f} points)"
            for name, values in ordered
        ]


_COMPONENT_LABELS: dict[str, str] = {
    "tenure": "Tenure band",
    "promotion_gap": "Months since last promotion",
    "engagement_delta": "Engagement vs department mean",
    "manager_attrition": "Manager's team attrition",
    "comp_percentile": "Position in pay band",
}


def score_row(row: Any) -> RiskScore:
    """Score one employee from a `v_flight_risk_inputs` row."""
    raw = {
        "tenure": score_tenure(int(row["tenure_months"] or 0)),
        "promotion_gap": score_promotion_gap(int(row["months_since_promotion"] or 0)),
        "engagement_delta": score_engagement_delta(
            row["employee_raw_index"], row["department_raw_index"]
        ),
        "manager_attrition": score_manager_attrition(
            row["manager_terminations"],
            row["manager_headcount_months"],
            row["company_terminations"],
            row["company_headcount_months"],
        ),
        "comp_percentile": score_comp_percentile(
            row["comp_amount"], row["comp_band_min"], row["comp_band_max"]
        ),
    }

    components = {
        name: {
            "score": round(value, 2),
            "weight": WEIGHTS[name],
            "contribution": round(value * WEIGHTS[name], 2),
        }
        for name, value in raw.items()
    }
    total = round(sum(part["contribution"] for part in components.values()), 2)

    return RiskScore(
        employee_id=row["employee_id"],
        as_of_month=row["as_of_month"],
        score=total,
        band=band_for(total),
        components=components,
    )


def compute(db: Session) -> list[RiskScore]:
    """Score every currently-active employee. Read-only."""
    rows = db.execute(select(v_flight_risk_inputs)).mappings().all()
    return [score_row(row) for row in rows]


def persist(db: Session, scores: list[RiskScore]) -> int:
    """Replace the stored scores for the months covered by `scores`.

    Deletes by month rather than truncating, so recomputing one month cannot silently
    discard another. Writes — the only function in the metric layer that does.
    """
    if not scores:
        return 0

    months = {score.as_of_month for score in scores}
    for month in months:
        db.execute(delete(FactFlightRiskScore).where(FactFlightRiskScore.as_of_month == month))

    now = datetime.now(UTC)
    db.execute(
        insert(FactFlightRiskScore),
        [
            {
                "employee_id": score.employee_id,
                "as_of_month": score.as_of_month,
                "score": score.score,
                "band": score.band,
                "components": score.components,
                "computed_at": now,
            }
            for score in scores
        ],
    )
    db.commit()
    return len(scores)


def top_risks(
    db: Session, *, limit: int = 25, band: RiskBand | None = None
) -> list[dict[str, Any]]:
    """Highest scores first, read from the stored table.

    Reads the persisted scores rather than recomputing, so the dashboard cannot be slowed
    by a full rescore on every page load, and so the numbers on screen match the ones the
    narrative in phase 6 was generated from.
    """
    stmt = select(FactFlightRiskScore).order_by(FactFlightRiskScore.score.desc())
    if band is not None:
        stmt = stmt.where(FactFlightRiskScore.band == band)
    stmt = stmt.limit(limit)

    return [
        {
            "employee_id": row.employee_id,
            "as_of_month": row.as_of_month,
            "score": float(row.score),
            "band": row.band.value,
            "components": row.components,
        }
        for row in db.execute(stmt).scalars().all()
    ]


def band_summary(db: Session) -> list[dict[str, Any]]:
    """Population per risk band, for the KPI row."""
    from sqlalchemy import func

    stmt = (
        select(FactFlightRiskScore.band, func.count().label("employees"))
        .group_by(FactFlightRiskScore.band)
        .order_by(FactFlightRiskScore.band)
    )
    return [
        {"band": row["band"].value, "employees": int(row["employees"])}
        for row in db.execute(stmt).mappings().all()
    ]


__all__ = [
    "BAND_THRESHOLDS",
    "WEIGHTS",
    "RiskScore",
    "band_for",
    "band_summary",
    "compute",
    "persist",
    "score_comp_percentile",
    "score_engagement_delta",
    "score_manager_attrition",
    "score_promotion_gap",
    "score_row",
    "score_tenure",
    "top_risks",
]
