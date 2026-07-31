"""Engagement metrics.

Formulas from docs/METRICS.md verbatim. The one thing to understand about this domain is
the **scale conversion**, which happens here and nowhere else:

    stored raw 1-5  ->  reported 0-100  via  (raw - 1) / 4 * 100

Survey answers are collected on a 1-5 Likert scale, but every target, chart and narrative
speaks in 0-100 points — "Belonging dropped 15 points". Views expose raw sums and response
counts; this module divides and converts. Two places doing the conversion is how a planted
28-point gap silently reads as 23.

eNPS is deliberately *not* on that scale. It is a signed score from -100 to +100, computed
as `%promoters - %detractors`, and it can legitimately be negative.
"""

from typing import Any

from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.orm import Session

from app.metrics.filters import MetricFilters, apply_filters
from app.metrics.tables import (
    v_absenteeism_monthly,
    v_comment_themes,
    v_engagement_attrition,
    v_survey_participation,
    v_survey_scores,
)

#: The five drivers named in docs/METRICS.md.
DRIVERS: tuple[str, ...] = ("manager", "growth", "recognition", "workload", "belonging")

_RAW_MIN = 1.0
_RAW_MAX = 5.0


def normalize_driver(raw: float | None) -> float | None:
    """Convert a raw 1-5 driver score to the 0-100 scale.

    The single definition of this conversion. `seed/validate.py` implements it
    independently in SQL on purpose — that is a cross-check, not a duplicate.
    """
    if raw is None:
        return None
    return (float(raw) - _RAW_MIN) / (_RAW_MAX - _RAW_MIN) * 100.0


def _ratio(numerator: Any, denominator: Any) -> float | None:
    if denominator is None or float(denominator) == 0.0:
        return None
    return float(numerator or 0) / float(denominator)


def _annualized(terminations: Any, headcount_months: Any) -> float | None:
    if headcount_months is None or float(headcount_months) == 0.0:
        return None
    return float(terminations or 0) * 12.0 / float(headcount_months)


def _scores_query(filters: MetricFilters, *, group_by: Any = None) -> Any:
    columns = [
        func.sum(v_survey_scores.c.responses).label("responses"),
        func.sum(v_survey_scores.c.promoters).label("promoters"),
        func.sum(v_survey_scores.c.passives).label("passives"),
        func.sum(v_survey_scores.c.detractors).label("detractors"),
        func.sum(v_survey_scores.c.driver_manager_sum).label("manager_sum"),
        func.sum(v_survey_scores.c.driver_growth_sum).label("growth_sum"),
        func.sum(v_survey_scores.c.driver_recognition_sum).label("recognition_sum"),
        func.sum(v_survey_scores.c.driver_workload_sum).label("workload_sum"),
        func.sum(v_survey_scores.c.driver_belonging_sum).label("belonging_sum"),
        func.sum(v_survey_scores.c.driver_total_sum).label("driver_total_sum"),
        func.sum(v_survey_scores.c.comments).label("comments"),
    ]
    if group_by is not None:
        columns.insert(0, group_by)

    stmt = select(*columns)
    if group_by is not None:
        stmt = stmt.group_by(group_by).order_by(group_by)
    stmt = apply_filters(stmt, v_survey_scores, filters, period_column="quarter_start")
    return stmt


# --- eNPS -------------------------------------------------------------------


def enps(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """%promoters (9-10) minus %detractors (0-6), on a -100..+100 scale.

    Not a percentage of anything, so a negative result is meaningful and must not be
    clamped. Passives count toward the denominator but neither numerator.
    """
    row = db.execute(_scores_query(filters)).mappings().one()
    responses = int(row["responses"] or 0)
    promoters = int(row["promoters"] or 0)
    detractors = int(row["detractors"] or 0)

    score = None
    if responses:
        score = (promoters / responses - detractors / responses) * 100.0

    return {
        "responses": responses,
        "promoters": promoters,
        "passives": int(row["passives"] or 0),
        "detractors": detractors,
        "enps": score,
    }


def enps_trend(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """eNPS per survey quarter, for the trend chart."""
    stmt = _scores_query(filters, group_by=v_survey_scores.c.quarter_start)
    rows = db.execute(stmt).mappings().all()

    trend: list[dict[str, Any]] = []
    for row in rows:
        responses = int(row["responses"] or 0)
        promoters = int(row["promoters"] or 0)
        detractors = int(row["detractors"] or 0)
        trend.append(
            {
                "period": row["quarter_start"],
                "responses": responses,
                "promoters": promoters,
                "detractors": detractors,
                "enps": None
                if not responses
                else (promoters / responses - detractors / responses) * 100.0,
            }
        )
    return trend


# --- Engagement index and drivers ------------------------------------------


def engagement_index(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """Mean of the five driver scores, normalized 0-100.

    Computed as one division of total raw points by (responses x 5), not as the mean of
    five separately-computed driver means. The two agree here, and a test asserts it, but
    only because the view sums raw points rather than pre-averaging.
    """
    row = db.execute(_scores_query(filters)).mappings().one()
    responses = int(row["responses"] or 0)
    answers = responses * len(DRIVERS)

    raw_mean = _ratio(row["driver_total_sum"], answers)
    return {
        "responses": responses,
        "engagement_index": normalize_driver(raw_mean),
    }


def driver_breakdown(db: Session, filters: MetricFilters) -> dict[str, float | None]:
    """Mean score per driver on the 0-100 scale."""
    row = db.execute(_scores_query(filters)).mappings().one()
    responses = int(row["responses"] or 0)

    return {driver: normalize_driver(_ratio(row[f"{driver}_sum"], responses)) for driver in DRIVERS}


def driver_trend(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Driver means per survey quarter — the shape the post-reorg dip takes."""
    stmt = _scores_query(filters, group_by=v_survey_scores.c.quarter_start)
    rows = db.execute(stmt).mappings().all()

    trend: list[dict[str, Any]] = []
    for row in rows:
        responses = int(row["responses"] or 0)
        entry: dict[str, Any] = {"period": row["quarter_start"], "responses": responses}
        for driver in DRIVERS:
            entry[driver] = normalize_driver(_ratio(row[f"{driver}_sum"], responses))
        entry["engagement_index"] = normalize_driver(
            _ratio(row["driver_total_sum"], responses * len(DRIVERS))
        )
        trend.append(entry)
    return trend


def driver_breakdown_by_department(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Driver means per department, for the radar chart in phase 5."""
    stmt = _scores_query(filters, group_by=v_survey_scores.c.department_id)
    rows = db.execute(stmt).mappings().all()

    breakdown: list[dict[str, Any]] = []
    for row in rows:
        responses = int(row["responses"] or 0)
        entry: dict[str, Any] = {
            "department_id": row["department_id"],
            "responses": responses,
        }
        for driver in DRIVERS:
            entry[driver] = normalize_driver(_ratio(row[f"{driver}_sum"], responses))
        entry["engagement_index"] = normalize_driver(
            _ratio(row["driver_total_sum"], responses * len(DRIVERS))
        )
        breakdown.append(entry)
    return breakdown


# --- Participation ----------------------------------------------------------


def participation(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """responses / eligible_employees, per survey.

    Eligibility is headcount at the month the survey closed, so the denominator moves
    with the organization rather than being pinned to a single point in time.
    """
    stmt = select(
        v_survey_participation.c.survey_id,
        v_survey_participation.c.quarter_start,
        func.sum(v_survey_participation.c.responses).label("responses"),
        func.sum(v_survey_participation.c.eligible_employees).label("eligible_employees"),
    ).group_by(v_survey_participation.c.survey_id, v_survey_participation.c.quarter_start)
    stmt = apply_filters(stmt, v_survey_participation, filters, period_column="quarter_start")
    stmt = stmt.order_by(v_survey_participation.c.survey_id)

    return [
        {
            "survey_id": row["survey_id"],
            "period": row["quarter_start"],
            "responses": int(row["responses"] or 0),
            "eligible_employees": int(row["eligible_employees"] or 0),
            "participation_rate": _ratio(row["responses"], row["eligible_employees"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Engagement to attrition -----------------------------------------------


def engagement_attrition_link(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Attrition of each engagement quartile in the six months after the survey.

    docs/METRICS.md asks for bottom quartile against top. All four are returned so the
    relationship can be seen to be monotonic rather than just showing the two extremes —
    a bottom-vs-top gap with a scrambled middle is not the story it appears to be.
    """
    stmt = select(
        v_engagement_attrition.c.quartile,
        # Respondent-survey observations, not distinct people: someone who answered four
        # surveys contributes four. Named honestly because the raw count reads like a
        # headcount and is roughly 3.4x larger than the real respondent population.
        func.sum(v_engagement_attrition.c.employees).label("respondent_observations"),
        func.sum(v_engagement_attrition.c.terminations).label("terminations"),
        func.sum(cast(v_engagement_attrition.c.headcount_months, Numeric)).label(
            "headcount_months"
        ),
    ).group_by(v_engagement_attrition.c.quartile)
    stmt = apply_filters(stmt, v_engagement_attrition, filters, period_column="quarter_start")
    stmt = stmt.order_by(v_engagement_attrition.c.quartile)

    return [
        {
            "quartile": int(row["quartile"]),
            "respondent_observations": int(row["respondent_observations"] or 0),
            "terminations": int(row["terminations"] or 0),
            "headcount_months": float(row["headcount_months"] or 0),
            "annualized_rate": _annualized(row["terminations"], row["headcount_months"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Absenteeism ------------------------------------------------------------


def absenteeism(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """unplanned_absence_days / available_workdays.

    Available workdays is headcount x workdays in the month, so the rate is comparable
    between a team of 4 and a team of 400. Planned leave is excluded from the numerator.
    """
    stmt = select(
        func.sum(cast(v_absenteeism_monthly.c.unplanned_days, Numeric)).label("unplanned_days"),
        func.sum(cast(v_absenteeism_monthly.c.planned_days, Numeric)).label("planned_days"),
        func.sum(cast(v_absenteeism_monthly.c.total_absence_days, Numeric)).label(
            "total_absence_days"
        ),
        func.sum(cast(v_absenteeism_monthly.c.available_workdays, Numeric)).label(
            "available_workdays"
        ),
        func.sum(cast(v_absenteeism_monthly.c.avg_headcount, Numeric)).label("avg_headcount"),
        func.max(v_absenteeism_monthly.c.workdays).label("workdays"),
    )
    stmt = apply_filters(stmt, v_absenteeism_monthly, filters, period_column="month_start")
    row = db.execute(stmt).mappings().one()

    return {
        "unplanned_days": float(row["unplanned_days"] or 0),
        "planned_days": float(row["planned_days"] or 0),
        "total_absence_days": float(row["total_absence_days"] or 0),
        "avg_headcount": float(row["avg_headcount"] or 0),
        "workdays": int(row["workdays"]) if row["workdays"] is not None else None,
        "available_workdays": float(row["available_workdays"] or 0),
        "absenteeism_rate": _ratio(row["unplanned_days"], row["available_workdays"]),
    }


def absenteeism_trend(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Absenteeism per month — the climb that scenario 5 plants in Support."""
    stmt = select(
        v_absenteeism_monthly.c.month_start.label("period"),
        func.sum(cast(v_absenteeism_monthly.c.unplanned_days, Numeric)).label("unplanned_days"),
        func.sum(cast(v_absenteeism_monthly.c.available_workdays, Numeric)).label(
            "available_workdays"
        ),
    ).group_by(v_absenteeism_monthly.c.month_start)
    stmt = apply_filters(stmt, v_absenteeism_monthly, filters, period_column="month_start")
    stmt = stmt.order_by(v_absenteeism_monthly.c.month_start)

    return [
        {
            "period": row["period"],
            "unplanned_days": float(row["unplanned_days"] or 0),
            "available_workdays": float(row["available_workdays"] or 0),
            "absenteeism_rate": _ratio(row["unplanned_days"], row["available_workdays"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Comment themes ---------------------------------------------------------


def comment_themes(db: Session, filters: MetricFilters, *, limit: int = 20) -> list[dict[str, Any]]:
    """Claude-extracted themes with sentiment and volume.

    Returns an empty list before phase 6 populates `fact_comment_theme`. That is the
    correct behaviour, not an error: the dashboard has to render in the meantime, and an
    exception here would take the whole Engagement page down over a feature that has not
    shipped yet.
    """
    stmt = select(
        v_comment_themes.c.theme,
        v_comment_themes.c.sentiment,
        func.sum(v_comment_themes.c.volume).label("volume"),
        func.avg(cast(v_comment_themes.c.mean_confidence, Numeric)).label("mean_confidence"),
    ).group_by(v_comment_themes.c.theme, v_comment_themes.c.sentiment)
    stmt = apply_filters(stmt, v_comment_themes, filters, period_column="quarter_start")
    stmt = stmt.order_by(func.sum(v_comment_themes.c.volume).desc()).limit(limit)

    return [
        {
            "theme": row["theme"],
            "sentiment": row["sentiment"],
            "volume": int(row["volume"] or 0),
            "mean_confidence": float(row["mean_confidence"]) if row["mean_confidence"] else None,
        }
        for row in db.execute(stmt).mappings().all()
    ]


__all__ = [
    "DRIVERS",
    "absenteeism",
    "absenteeism_trend",
    "comment_themes",
    "driver_breakdown",
    "driver_breakdown_by_department",
    "driver_trend",
    "engagement_attrition_link",
    "engagement_index",
    "enps",
    "enps_trend",
    "normalize_driver",
    "participation",
]
