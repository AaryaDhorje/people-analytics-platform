"""Talent acquisition metrics.

Formulas from docs/METRICS.md verbatim. Three things about this domain are easy to get
subtly wrong, and each is handled in one place here:

**Time to fill and time to hire are different metrics.** Time to fill runs from the
requisition's `opened_date` — how long the vacancy stood open. Time to hire runs from the
candidate's `first_application_date` — how long that person waited. They come from
different views for that reason.

**Averages are computed from a day sum over an observation count**, never by averaging a
view's pre-averaged column. `AVG(AVG(x))` is not `AVG(x)` once rows are filtered or
grouped differently, and the error is invisible until someone checks by hand.

**Source Effectiveness spans two tables.** Its conversion half (hires / applications) is
application-level; its retention half is employee-level, because applications carry no
termination date. They are separate functions rather than one that silently mixes grains.
"""

from typing import Any

from sqlalchemy import Numeric, case, cast, func, select
from sqlalchemy.orm import Session

from app.metrics.filters import MetricFilters, apply_filters
from app.metrics.tables import (
    v_application_funnel,
    v_application_outcomes,
    v_requisition_metrics,
    v_source_quality,
)

#: docs/METRICS.md: "COUNT(reqs WHERE status='open' AND age_days > 60)".
AGING_THRESHOLD_DAYS = 60

#: Funnel order from docs/METRICS.md. Conversion is stage_n / stage_n-1 along this path.
FUNNEL_STAGES: tuple[str, ...] = ("applied", "screen", "interview", "offer", "hired")

_OPEN_STATUS = "open"


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _ratio(numerator: Any, denominator: Any) -> float | None:
    """None when the denominator is empty. A fabricated zero reads as a real measurement."""
    if denominator is None or float(denominator) == 0.0:
        return None
    return float(numerator or 0) / float(denominator)


# --- Time to fill -----------------------------------------------------------


def time_to_fill(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """AVG(offer_accepted_date - requisition_opened_date).

    Requisitions with nothing accepted contribute to neither side, so an unfilled req
    cannot pull the mean toward zero.
    """
    stmt = select(
        func.sum(v_requisition_metrics.c.time_to_fill_day_sum).label("day_sum"),
        func.sum(v_requisition_metrics.c.filled_positions).label("filled_positions"),
        func.count().label("requisitions"),
    )
    stmt = apply_filters(stmt, v_requisition_metrics, filters, period_column="opened_date")
    row = db.execute(stmt).mappings().one()

    return {
        "requisitions": int(row["requisitions"] or 0),
        "filled_positions": int(row["filled_positions"] or 0),
        "day_sum": int(row["day_sum"] or 0),
        "mean_days": _ratio(row["day_sum"], row["filled_positions"]),
    }


def time_to_fill_by_month(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Time to fill by the month the requisition opened, for the trend chart."""
    stmt = select(
        v_requisition_metrics.c.opened_month.label("period"),
        func.sum(v_requisition_metrics.c.time_to_fill_day_sum).label("day_sum"),
        func.sum(v_requisition_metrics.c.filled_positions).label("filled_positions"),
    ).group_by(v_requisition_metrics.c.opened_month)
    stmt = apply_filters(stmt, v_requisition_metrics, filters, period_column="opened_month")
    stmt = stmt.order_by(v_requisition_metrics.c.opened_month)

    return [
        {
            "period": row["period"],
            "filled_positions": int(row["filled_positions"] or 0),
            "mean_days": _ratio(row["day_sum"], row["filled_positions"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Time to hire -----------------------------------------------------------


def time_to_hire(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """AVG(offer_accepted_date - first_application_date)."""
    stmt = select(
        func.sum(v_application_outcomes.c.time_to_hire_day_sum).label("day_sum"),
        func.sum(v_application_outcomes.c.time_to_hire_observations).label("observations"),
    )
    stmt = apply_filters(stmt, v_application_outcomes, filters, period_column="applied_month")
    row = db.execute(stmt).mappings().one()

    return {
        "observations": int(row["observations"] or 0),
        "day_sum": int(row["day_sum"] or 0),
        "mean_days": _ratio(row["day_sum"], row["observations"]),
    }


# --- Funnel -----------------------------------------------------------------


def funnel(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Stage counts with conversion from the stage above, plus dwell per stage.

    docs/METRICS.md: `stage_n_count / stage_n-1_count` across
    Applied -> Screen -> Interview -> Offer -> Hired.

    Conversion is computed here rather than in SQL because it needs the *previous* row,
    and a window function in the view would compute it before the caller's filters were
    applied — giving conversion rates for a slice nobody asked for.
    """
    stmt = select(
        v_application_funnel.c.stage,
        v_application_funnel.c.stage_order,
        func.sum(v_application_funnel.c.applications).label("applications"),
        func.sum(v_application_funnel.c.dwell_day_sum).label("dwell_day_sum"),
        func.sum(v_application_funnel.c.dwell_observations).label("dwell_observations"),
        func.sum(v_application_funnel.c.still_in_stage).label("still_in_stage"),
    ).group_by(v_application_funnel.c.stage, v_application_funnel.c.stage_order)
    stmt = apply_filters(stmt, v_application_funnel, filters, period_column="entered_month")
    stmt = stmt.order_by(v_application_funnel.c.stage_order)

    by_stage = {row["stage"]: row for row in db.execute(stmt).mappings().all()}

    rows: list[dict[str, Any]] = []
    previous: int | None = None
    for stage in FUNNEL_STAGES:
        row = by_stage.get(stage)
        applications = int(row["applications"] or 0) if row else 0
        if row is None and previous is None:
            # No data at all for this slice at or above this stage.
            continue
        rows.append(
            {
                "stage": stage,
                "applications": applications,
                "conversion_from_previous": None
                if previous is None
                else _ratio(applications, previous),
                "mean_dwell_days": _ratio(
                    row["dwell_day_sum"] if row else None,
                    row["dwell_observations"] if row else None,
                ),
                "still_in_stage": int(row["still_in_stage"] or 0) if row else 0,
            }
        )
        previous = applications
    return rows


# --- Offer acceptance -------------------------------------------------------


def offer_acceptance(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """offers_accepted / offers_extended."""
    stmt = select(
        func.sum(v_application_outcomes.c.offers_extended).label("offers_extended"),
        func.sum(v_application_outcomes.c.offers_accepted).label("offers_accepted"),
        func.sum(v_application_outcomes.c.offers_declined).label("offers_declined"),
    )
    stmt = apply_filters(stmt, v_application_outcomes, filters, period_column="applied_month")
    row = db.execute(stmt).mappings().one()

    extended = int(row["offers_extended"] or 0)
    accepted = int(row["offers_accepted"] or 0)
    return {
        "offers_extended": extended,
        "offers_accepted": accepted,
        "offers_declined": int(row["offers_declined"] or 0),
        "acceptance_rate": _ratio(accepted, extended),
    }


def offer_acceptance_by_month(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Acceptance rate per month, for the overview sparkline."""
    stmt = select(
        v_application_outcomes.c.applied_month.label("period"),
        func.sum(v_application_outcomes.c.offers_extended).label("offers_extended"),
        func.sum(v_application_outcomes.c.offers_accepted).label("offers_accepted"),
    ).group_by(v_application_outcomes.c.applied_month)
    stmt = apply_filters(stmt, v_application_outcomes, filters, period_column="applied_month")
    stmt = stmt.order_by(v_application_outcomes.c.applied_month)

    return [
        {
            "period": row["period"],
            "offers_extended": int(row["offers_extended"] or 0),
            "offers_accepted": int(row["offers_accepted"] or 0),
            "acceptance_rate": _ratio(row["offers_accepted"], row["offers_extended"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Cost per hire ----------------------------------------------------------


def cost_per_hire(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """(internal_cost + external_cost) / hires_in_period, by department and quarter.

    A quarter with spend but no hires returns null, not the raw spend and not zero.
    Zero would claim hiring was free; the raw spend would invent a hire.
    """
    stmt = select(
        v_requisition_metrics.c.department_id,
        v_requisition_metrics.c.opened_quarter.label("period"),
        func.sum(cast(v_requisition_metrics.c.total_cost, Numeric)).label("total_cost"),
        func.sum(cast(v_requisition_metrics.c.internal_cost, Numeric)).label("internal_cost"),
        func.sum(cast(v_requisition_metrics.c.external_cost, Numeric)).label("external_cost"),
        func.sum(v_requisition_metrics.c.hires).label("hires"),
    ).group_by(v_requisition_metrics.c.department_id, v_requisition_metrics.c.opened_quarter)
    stmt = apply_filters(stmt, v_requisition_metrics, filters, period_column="opened_quarter")
    stmt = stmt.order_by(
        v_requisition_metrics.c.opened_quarter, v_requisition_metrics.c.department_id
    )

    return [
        {
            "department_id": row["department_id"],
            "period": row["period"],
            "total_cost": _num(row["total_cost"]),
            "internal_cost": _num(row["internal_cost"]),
            "external_cost": _num(row["external_cost"]),
            "hires": int(row["hires"] or 0),
            "cost_per_hire": _ratio(row["total_cost"], row["hires"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Requisition aging ------------------------------------------------------


def requisition_aging(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Open requisitions, and how many have been open beyond the threshold.

    `age_days` comes from the view measured to the last day in the date spine, not to
    CURRENT_DATE. The warehouse is a fixed window, so wall-clock ageing would drift every
    day the demo was not run.
    """
    # CASE rather than a cast: PostgreSQL refuses `boolean -> numeric` outright
    # ("cannot coerce type boolean to numeric"), so summing a predicate needs an
    # explicit 1/0 projection.
    aged = func.sum(
        case((v_requisition_metrics.c.age_days > AGING_THRESHOLD_DAYS, 1), else_=0)
    ).label("aged_requisitions")

    stmt = (
        select(
            v_requisition_metrics.c.department_id,
            func.count().label("open_requisitions"),
            aged,
            func.max(v_requisition_metrics.c.age_days).label("max_age_days"),
        )
        .where(v_requisition_metrics.c.status == _OPEN_STATUS)
        .group_by(v_requisition_metrics.c.department_id)
    )
    stmt = apply_filters(stmt, v_requisition_metrics, filters, period_column="opened_date")
    stmt = stmt.order_by(v_requisition_metrics.c.department_id)

    return [
        {
            "department_id": row["department_id"],
            "open_requisitions": int(row["open_requisitions"] or 0),
            "aged_requisitions": int(row["aged_requisitions"] or 0),
            "max_age_days": int(row["max_age_days"]) if row["max_age_days"] is not None else None,
            "threshold_days": AGING_THRESHOLD_DAYS,
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Source effectiveness ---------------------------------------------------


def source_effectiveness(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """hires_from_source / applications_from_source — the application-level half.

    See `source_retention` for the other half. Keeping them separate is deliberate: an
    application has no termination date, so retention cannot be computed from this grain.
    """
    stmt = select(
        v_application_outcomes.c.source_id,
        func.sum(v_application_outcomes.c.applications).label("applications"),
        func.sum(v_application_outcomes.c.hires).label("hires"),
        func.sum(v_application_outcomes.c.offers_extended).label("offers_extended"),
    ).group_by(v_application_outcomes.c.source_id)
    stmt = apply_filters(stmt, v_application_outcomes, filters, period_column="applied_month")
    stmt = stmt.order_by(v_application_outcomes.c.source_id)

    return [
        {
            "source_id": row["source_id"],
            "applications": int(row["applications"] or 0),
            "offers_extended": int(row["offers_extended"] or 0),
            "hires": int(row["hires"] or 0),
            "conversion_rate": _ratio(row["hires"], row["applications"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


def source_retention(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """90-day retention of hires by channel — the employee-level half.

    "Retained at 90 days" means employed *at that milestone*, not employed today. Someone
    who left at day 288 counts as retained at 90 and at 180. Milestone retention and
    current headcount are different questions.
    """
    stmt = select(
        v_source_quality.c.source_id,
        func.sum(v_source_quality.c.hires).label("hires"),
        func.sum(v_source_quality.c.eligible_90d).label("eligible_90d"),
        func.sum(v_source_quality.c.retained_90d).label("retained_90d"),
        func.sum(v_source_quality.c.eligible_180d).label("eligible_180d"),
        func.sum(v_source_quality.c.retained_180d).label("retained_180d"),
    ).group_by(v_source_quality.c.source_id)
    stmt = apply_filters(stmt, v_source_quality, filters, period_column="hire_quarter")
    stmt = stmt.order_by(v_source_quality.c.source_id)

    return [
        {
            "source_id": row["source_id"],
            "hires": int(row["hires"] or 0),
            "eligible_90d": int(row["eligible_90d"] or 0),
            "retained_90d": int(row["retained_90d"] or 0),
            "retention_90d": _ratio(row["retained_90d"], row["eligible_90d"]),
            "eligible_180d": int(row["eligible_180d"] or 0),
            "retained_180d": int(row["retained_180d"] or 0),
            "retention_180d": _ratio(row["retained_180d"], row["eligible_180d"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Quality of hire --------------------------------------------------------


def quality_of_hire(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """% of new hires still employed at day 180 AND rated 3 or better.

    Both conditions are required. Survival alone is attendance; a rating alone says
    nothing about whether the hire stuck. The denominator is `eligible_180d` — hires that
    have actually reached day 180 inside the window — not all hires.
    """
    stmt = select(
        v_source_quality.c.source_id,
        v_source_quality.c.manager_id,
        func.sum(v_source_quality.c.eligible_180d).label("eligible_180d"),
        func.sum(v_source_quality.c.retained_180d).label("retained_180d"),
        func.sum(v_source_quality.c.quality_hires).label("quality_hires"),
    ).group_by(v_source_quality.c.source_id, v_source_quality.c.manager_id)
    stmt = apply_filters(stmt, v_source_quality, filters, period_column="hire_quarter")
    stmt = stmt.order_by(v_source_quality.c.source_id)

    grouped: dict[int, dict[str, Any]] = {}
    for row in db.execute(stmt).mappings().all():
        entry = grouped.setdefault(
            row["source_id"],
            {
                "source_id": row["source_id"],
                "eligible_180d": 0,
                "retained_180d": 0,
                "quality_hires": 0,
            },
        )
        entry["eligible_180d"] += int(row["eligible_180d"] or 0)
        entry["retained_180d"] += int(row["retained_180d"] or 0)
        entry["quality_hires"] += int(row["quality_hires"] or 0)

    return [
        {**entry, "quality_rate": _ratio(entry["quality_hires"], entry["eligible_180d"])}
        for entry in sorted(grouped.values(), key=lambda item: item["source_id"])
    ]


def quality_of_hire_by_manager(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Quality of hire grained by hiring manager, per docs/METRICS.md's second grain."""
    stmt = select(
        v_source_quality.c.manager_id,
        func.sum(v_source_quality.c.eligible_180d).label("eligible_180d"),
        func.sum(v_source_quality.c.quality_hires).label("quality_hires"),
    ).group_by(v_source_quality.c.manager_id)
    stmt = apply_filters(stmt, v_source_quality, filters, period_column="hire_quarter")
    stmt = stmt.order_by(v_source_quality.c.manager_id)

    return [
        {
            "manager_id": row["manager_id"],
            "eligible_180d": int(row["eligible_180d"] or 0),
            "quality_hires": int(row["quality_hires"] or 0),
            "quality_rate": _ratio(row["quality_hires"], row["eligible_180d"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


__all__ = [
    "AGING_THRESHOLD_DAYS",
    "FUNNEL_STAGES",
    "cost_per_hire",
    "funnel",
    "offer_acceptance",
    "quality_of_hire",
    "quality_of_hire_by_manager",
    "requisition_aging",
    "source_effectiveness",
    "source_retention",
    "time_to_fill",
    "time_to_fill_by_month",
    "time_to_hire",
]
