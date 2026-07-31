"""Retention metrics.

Formulas come from docs/METRICS.md verbatim. Two rules hold throughout and are the
reason this module reads the way it does:

1. **Rate denominators are average headcount**, never end-of-period. The views expose
   `avg_headcount` and `headcount_months` precisely so the correct denominator is the
   one closest to hand.
2. **Division happens here, never in a view.** Views aggregate numerators and
   denominators; this module divides. That keeps the denominator visible in the response
   and keeps the independent SQL recomputation in phase 3's verifier comparable.

Annualization uses the identity

    annualized_rate = terminations * 12 / sum(monthly average headcount)

which is correct for any number of months, so the same expression serves a single month,
a quarter and a full window without a special case per grain.

Functions return plain dicts. Pydantic response models live in app/schemas/metrics.py
and validate at the route boundary; keeping the metric layer free of them means a test
can assert on a number without constructing a model.
"""

from datetime import date
from typing import Any

from sqlalchemy import Numeric, Select, cast, func, select
from sqlalchemy.orm import Session

from app.metrics.filters import TENURE_BANDS, MetricFilters, apply_filters
from app.metrics.tables import (
    v_cohort_survival,
    v_headcount_monthly,
    v_manager_attrition_quarterly,
    v_mobility_monthly,
    v_regretted_exits,
    v_tenure_band_monthly,
)
from seed.util import add_months

#: docs/METRICS.md: "Attrition rate where manager_id = X, min 8 reports".
MIN_REPORTS_FOR_MANAGER_ATTRITION = 8

#: Window for ranking managers against each other. Twelve months because a quarter's
#: denominator is small enough that one bad stretch outranks a genuinely failing team, and
#: because `flight_risk` already scores its manager-attrition component on a trailing year
#: — two features disagreeing about who is in trouble is worse than either being slightly
#: off.
TRAILING_MONTHS_FOR_MANAGER_RANKING = 12


def _num(value: Any) -> float | None:
    """Decimal/int from the driver to float for JSON, preserving None."""
    return None if value is None else float(value)


def _ratio(numerator: Any, denominator: Any) -> float | None:
    """Divide, returning None when the denominator is empty.

    Zero-over-zero must be None rather than 0.0: a fabricated zero becomes a fabricated
    point on a chart, indistinguishable from a real one.
    """
    if denominator is None or float(denominator) == 0.0:
        return None
    return float(numerator or 0) / float(denominator)


def _annualized(terminations: Any, headcount_months: Any) -> float | None:
    """terminations * 12 / headcount_months.

    Returns 0.0 rather than None when there were genuinely no exits over a real
    headcount — a month with nobody leaving has a rate of zero, and a null would render
    as a gap in the trend.
    """
    if headcount_months is None or float(headcount_months) == 0.0:
        return None
    return float(terminations or 0) * 12.0 / float(headcount_months)


# --- Headcount --------------------------------------------------------------


def _headcount_query(filters: MetricFilters) -> Select[Any]:
    stmt = select(
        v_headcount_monthly.c.month_start.label("period"),
        func.sum(v_headcount_monthly.c.active_start).label("active_start"),
        func.sum(v_headcount_monthly.c.active_end).label("active_end"),
        func.sum(cast(v_headcount_monthly.c.avg_headcount, Numeric)).label("avg_headcount"),
        func.sum(v_headcount_monthly.c.hires).label("hires"),
        func.sum(v_headcount_monthly.c.terminations).label("terminations"),
        func.sum(v_headcount_monthly.c.voluntary_terminations).label("voluntary_terminations"),
        func.sum(v_headcount_monthly.c.involuntary_terminations).label("involuntary_terminations"),
        func.sum(cast(v_headcount_monthly.c.total_fte, Numeric)).label("total_fte"),
    ).group_by(v_headcount_monthly.c.month_start)
    stmt = apply_filters(stmt, v_headcount_monthly, filters, period_column="month_start")
    return stmt.order_by(v_headcount_monthly.c.month_start)


def headcount_series(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Headcount at each month end, with both activity endpoints alongside it.

    docs/METRICS.md: `COUNT(active employees)` at month-end snapshot.
    """
    rows = db.execute(_headcount_query(filters)).mappings().all()
    return [
        {
            "period": row["period"],
            "headcount": int(row["active_end"] or 0),
            "active_start": int(row["active_start"] or 0),
            "active_end": int(row["active_end"] or 0),
            "avg_headcount": _num(row["avg_headcount"]),
            "hires": int(row["hires"] or 0),
            "terminations": int(row["terminations"] or 0),
            "total_fte": _num(row["total_fte"]),
        }
        for row in rows
    ]


# --- Attrition --------------------------------------------------------------


def attrition_rate(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Annualized attrition per month.

    docs/METRICS.md: `(terminations_in_month / avg_headcount_in_month) * 12`.
    """
    rows = db.execute(_headcount_query(filters)).mappings().all()
    return [
        {
            "period": row["period"],
            "terminations": int(row["terminations"] or 0),
            "voluntary_terminations": int(row["voluntary_terminations"] or 0),
            "involuntary_terminations": int(row["involuntary_terminations"] or 0),
            "avg_headcount": _num(row["avg_headcount"]),
            "annualized_rate": _annualized(row["terminations"], row["avg_headcount"]),
        }
        for row in rows
    ]


def attrition_total(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """One annualized figure for the whole filtered period.

    `headcount_months` is the sum of each month's average headcount, which is what makes
    a single expression valid across any span.
    """
    stmt = select(
        func.sum(v_headcount_monthly.c.terminations).label("terminations"),
        func.sum(v_headcount_monthly.c.voluntary_terminations).label("voluntary_terminations"),
        func.sum(v_headcount_monthly.c.involuntary_terminations).label("involuntary_terminations"),
        func.sum(cast(v_headcount_monthly.c.avg_headcount, Numeric)).label("headcount_months"),
        func.count(func.distinct(v_headcount_monthly.c.month_start)).label("months"),
    )
    stmt = apply_filters(stmt, v_headcount_monthly, filters, period_column="month_start")
    row = db.execute(stmt).mappings().one()

    terminations = int(row["terminations"] or 0)
    voluntary = int(row["voluntary_terminations"] or 0)
    involuntary = int(row["involuntary_terminations"] or 0)
    return {
        "terminations": terminations,
        "voluntary_terminations": voluntary,
        "involuntary_terminations": involuntary,
        "voluntary_share": _ratio(voluntary, terminations),
        "headcount_months": _num(row["headcount_months"]),
        "months": int(row["months"] or 0),
        "annualized_rate": _annualized(terminations, row["headcount_months"]),
    }


def regretted_attrition(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """Voluntary exits by people whose last rating was 4 or 5, over all voluntary exits.

    docs/METRICS.md: `voluntary_exits WHERE last_performance_rating >= 4 /
    total_voluntary_exits`. An involuntary exit of a high performer is a decision, not
    regret, so it is excluded from both sides.
    """
    stmt = select(
        func.sum(v_regretted_exits.c.voluntary_exits).label("voluntary_exits"),
        func.sum(v_regretted_exits.c.regretted_exits).label("regretted_exits"),
        func.sum(v_regretted_exits.c.total_exits).label("total_exits"),
    )
    stmt = apply_filters(stmt, v_regretted_exits, filters, period_column="month_start")
    row = db.execute(stmt).mappings().one()

    voluntary = int(row["voluntary_exits"] or 0)
    regretted = int(row["regretted_exits"] or 0)
    return {
        "total_exits": int(row["total_exits"] or 0),
        "voluntary_exits": voluntary,
        "regretted_exits": regretted,
        "regretted_share": _ratio(regretted, voluntary),
    }


def regretted_attrition_trend(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Regretted share per month, for the overview sparkline.

    Months with no voluntary exits yield None rather than 0 — the share is undefined,
    and a zero would draw a line at the bottom of the chart implying nobody good left.
    """
    stmt = select(
        v_regretted_exits.c.month_start.label("period"),
        func.sum(v_regretted_exits.c.voluntary_exits).label("voluntary_exits"),
        func.sum(v_regretted_exits.c.regretted_exits).label("regretted_exits"),
    ).group_by(v_regretted_exits.c.month_start)
    stmt = apply_filters(stmt, v_regretted_exits, filters, period_column="month_start")
    stmt = stmt.order_by(v_regretted_exits.c.month_start)

    return [
        {
            "period": row["period"],
            "voluntary_exits": int(row["voluntary_exits"] or 0),
            "regretted_exits": int(row["regretted_exits"] or 0),
            "regretted_share": _ratio(row["regretted_exits"], row["voluntary_exits"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Tenure -----------------------------------------------------------------


def tenure_distribution(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Headcount per tenure band, **point-in-time** at the latest month in range.

    Bands are fixed in docs/METRICS.md: <6m, 6-12m, 1-2y, 2-5y, 5y+. Results are ordered
    by `band_order` from the view, because alphabetical ordering puts "1-2y" before
    "6-12m" and makes a histogram unreadable.

    A distribution is a snapshot, not an accumulation. Summing headcount across every
    month in range produced person-months: the bands totalled 42,997 for a 1,200-person
    company, and a bar reading "15,722 employees with 5y+ tenure" invites exactly the
    question you do not want on camera. Collapsing to the last month in range gives a
    distribution that sums to actual headcount.
    """
    latest_month = select(func.max(v_tenure_band_monthly.c.month_start))
    latest_month = apply_filters(
        latest_month, v_tenure_band_monthly, filters, period_column="month_start"
    ).scalar_subquery()

    stmt = select(
        v_tenure_band_monthly.c.tenure_band,
        v_tenure_band_monthly.c.band_order,
        func.sum(v_tenure_band_monthly.c.headcount).label("headcount"),
    ).where(v_tenure_band_monthly.c.month_start == latest_month)
    stmt = stmt.group_by(v_tenure_band_monthly.c.tenure_band, v_tenure_band_monthly.c.band_order)
    stmt = apply_filters(stmt, v_tenure_band_monthly, filters, period_column="month_start")
    stmt = stmt.order_by(v_tenure_band_monthly.c.band_order)

    rows = db.execute(stmt).mappings().all()
    present = {row["tenure_band"]: int(row["headcount"] or 0) for row in rows}
    return [
        {"tenure_band": band, "headcount": present[band]}
        for band in TENURE_BANDS
        if band in present
    ]


# --- Cohort survival --------------------------------------------------------

#: docs/METRICS.md's New Hire 12-Month Retention.
DEFAULT_RETENTION_HORIZON_MONTHS = 12


def cohort_retention(
    db: Session, filters: MetricFilters, *, months: int = DEFAULT_RETENTION_HORIZON_MONTHS
) -> list[dict[str, Any]]:
    """Retention at a fixed milestone, by hire channel.

    Only cohorts that have *reached* the milestone inside the data appear. The view does
    that censoring; a cohort hired three months ago cannot inform 12-month retention, and
    including it would either flatter or libel its channel depending on which side of the
    fraction it landed on.
    """
    stmt = select(
        v_cohort_survival.c.source_id,
        func.sum(v_cohort_survival.c.cohort_size).label("cohort_size"),
        func.sum(v_cohort_survival.c.still_active).label("still_active"),
    ).where(v_cohort_survival.c.months_since_hire == months)
    stmt = apply_filters(stmt, v_cohort_survival, filters, period_column="hire_quarter")
    stmt = stmt.group_by(v_cohort_survival.c.source_id).order_by(v_cohort_survival.c.source_id)

    rows = db.execute(stmt).mappings().all()
    return [
        {
            "source_id": row["source_id"],
            "months_since_hire": months,
            "cohort_size": int(row["cohort_size"] or 0),
            "still_active": int(row["still_active"] or 0),
            "retention_rate": _ratio(row["still_active"], row["cohort_size"]),
        }
        for row in rows
    ]


def cohort_survival_curve(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Survival at every month offset, aggregated across cohorts — the curve behind the
    knee that scenario 6 plants at 14-18 months."""
    stmt = select(
        v_cohort_survival.c.months_since_hire,
        func.sum(v_cohort_survival.c.cohort_size).label("cohort_size"),
        func.sum(v_cohort_survival.c.still_active).label("still_active"),
    )
    stmt = apply_filters(stmt, v_cohort_survival, filters, period_column="hire_quarter")
    stmt = stmt.group_by(v_cohort_survival.c.months_since_hire).order_by(
        v_cohort_survival.c.months_since_hire
    )

    rows = db.execute(stmt).mappings().all()
    return [
        {
            "months_since_hire": int(row["months_since_hire"]),
            "cohort_size": int(row["cohort_size"] or 0),
            "still_active": int(row["still_active"] or 0),
            "survival_rate": _ratio(row["still_active"], row["cohort_size"]) or 0.0,
        }
        for row in rows
    ]


# --- Attrition by manager ---------------------------------------------------


def attrition_by_manager(
    db: Session,
    filters: MetricFilters,
    *,
    min_reports: int = MIN_REPORTS_FOR_MANAGER_ATTRITION,
) -> list[dict[str, Any]]:
    """Annualized attrition per manager per quarter, above a report-count floor.

    docs/METRICS.md requires a minimum of 8 reports. The threshold exists because an
    attrition rate over four people is noise dressed as signal — one departure reads as
    25%. `min_reports` is a parameter only so tests can exercise the arithmetic on a
    12-person fixture where nobody clears the real floor.

    The floor is applied to **average** team size, not to the count of distinct people who
    passed through the team. A manager with 9 distinct reports across a quarter can have
    averaged 6, and three exits from a team of six annualizes to 189% — precisely the
    small-team artefact the floor exists to suppress. Filtering on the distinct count
    admitted 161 of 952 manager-quarters whose real span was under 8, and put one of them
    at the top of the heatmap.
    """
    stmt = select(
        v_manager_attrition_quarterly.c.quarter_start.label("period"),
        v_manager_attrition_quarterly.c.manager_id,
        v_manager_attrition_quarterly.c.department_id,
        v_manager_attrition_quarterly.c.reports,
        v_manager_attrition_quarterly.c.avg_reports,
        v_manager_attrition_quarterly.c.terminations,
        v_manager_attrition_quarterly.c.voluntary_terminations,
        v_manager_attrition_quarterly.c.headcount_months,
    ).where(v_manager_attrition_quarterly.c.avg_reports >= min_reports)
    stmt = apply_filters(
        stmt, v_manager_attrition_quarterly, filters, period_column="quarter_start"
    )
    stmt = stmt.order_by(
        v_manager_attrition_quarterly.c.quarter_start,
        v_manager_attrition_quarterly.c.manager_id,
    )

    rows = db.execute(stmt).mappings().all()
    return [
        {
            "period": row["period"],
            "manager_id": row["manager_id"],
            "department_id": row["department_id"],
            "reports": int(row["reports"] or 0),
            "avg_reports": _num(row["avg_reports"]),
            "terminations": int(row["terminations"] or 0),
            "voluntary_terminations": int(row["voluntary_terminations"] or 0),
            "headcount_months": _num(row["headcount_months"]),
            "annualized_rate": _annualized(row["terminations"], row["headcount_months"]),
        }
        for row in rows
    ]


def attrition_by_manager_trailing(
    db: Session,
    filters: MetricFilters,
    *,
    months: int = TRAILING_MONTHS_FOR_MANAGER_RANKING,
    min_reports: int = MIN_REPORTS_FOR_MANAGER_ATTRITION,
) -> list[dict[str, Any]]:
    """One row per manager, aggregated over a trailing window, worst rate first.

    `attrition_by_manager` is grained by (quarter, manager) because that is what
    docs/METRICS.md defines and what a heatmap over time needs. Ranking those rows,
    however, ranks *noise*: four exits from an 8.7-person team in a single quarter
    annualizes to 184%, and the top of the list fills with managers who had one bad
    three-month stretch. Widening to a year roughly quadruples every denominator, which is
    the only thing that actually suppresses small-sample rate inflation.

    It also answers the more useful question. A three-year average hides a team that was
    fine for two years and is collapsing now — precisely the shape of the planted
    bad-manager scenario, whose exits all fall in the final three quarters. Over the full
    span that manager ranks 31st of 55; over the trailing year, 2nd.

    Deliberately the same definition `flight_risk` uses for its manager-attrition
    component, so the two features cannot disagree about who is in trouble.

    The window anchors to the latest quarter **in the data**, not to `date.today()`. The
    warehouse covers a fixed span, and a clock-anchored window empties the card the day
    after the demo.
    """
    anchor_stmt = select(func.max(v_manager_attrition_quarterly.c.quarter_start))
    anchor_stmt = apply_filters(
        anchor_stmt, v_manager_attrition_quarterly, filters, period_column="quarter_start"
    )
    anchor: date | None = db.execute(anchor_stmt).scalar_one_or_none()
    if anchor is None:
        return []

    # Exclusive lower bound: with a 12-month window and quarterly grain this admits the
    # four quarters ending at the anchor, which is 12 months of coverage.
    window_from = add_months(anchor, -months)

    stmt = select(
        v_manager_attrition_quarterly.c.manager_id,
        func.max(v_manager_attrition_quarterly.c.department_id).label("department_id"),
        func.min(v_manager_attrition_quarterly.c.quarter_start).label("window_from"),
        func.count().label("quarters"),
        func.sum(v_manager_attrition_quarterly.c.months_observed).label("months_observed"),
        func.sum(v_manager_attrition_quarterly.c.terminations).label("terminations"),
        func.sum(v_manager_attrition_quarterly.c.voluntary_terminations).label(
            "voluntary_terminations"
        ),
        func.sum(v_manager_attrition_quarterly.c.headcount_months).label("headcount_months"),
        func.max(v_manager_attrition_quarterly.c.reports).label("peak_reports"),
    ).where(v_manager_attrition_quarterly.c.quarter_start > window_from)
    stmt = apply_filters(
        stmt, v_manager_attrition_quarterly, filters, period_column="quarter_start"
    )
    stmt = stmt.group_by(v_manager_attrition_quarterly.c.manager_id)

    rows = db.execute(stmt).mappings().all()
    if not rows:
        return []

    # The baseline covers every managed employee in the window, including the small teams
    # the floor suppresses below — they are still part of the company, and excluding them
    # would compare each manager against a population that excludes their own peers.
    company_rate = _annualized(
        sum(int(row["terminations"] or 0) for row in rows),
        sum(_num(row["headcount_months"]) for row in rows),
    )
    window_to = anchor
    earliest = min(row["window_from"] for row in rows)

    ranked: list[dict[str, Any]] = []
    for row in rows:
        headcount_months = _num(row["headcount_months"])
        observed = int(row["months_observed"] or 0)
        # The floor applies to the window average, not to any single quarter. Filtering
        # quarters first would discard the months a shrinking team spent below the line —
        # flattering exactly the manager whose team is collapsing.
        avg_reports = headcount_months / observed if observed else 0.0
        if avg_reports < min_reports:
            continue
        ranked.append(
            {
                "manager_id": row["manager_id"],
                "department_id": row["department_id"],
                "window_from": earliest,
                "window_to": window_to,
                "months": months,
                "quarters": int(row["quarters"] or 0),
                "months_observed": observed,
                "peak_reports": int(row["peak_reports"] or 0),
                "avg_reports": avg_reports,
                "terminations": int(row["terminations"] or 0),
                "voluntary_terminations": int(row["voluntary_terminations"] or 0),
                "headcount_months": headcount_months,
                "annualized_rate": _annualized(row["terminations"], headcount_months),
                "company_annualized_rate": company_rate,
            }
        )

    # Worst first, then by exits so two managers on the same rate are separated by the one
    # carrying more people out of the door. Manager id last, to keep the order stable.
    ranked.sort(
        key=lambda r: (-(r["annualized_rate"] or 0.0), -r["terminations"], r["manager_id"])
    )
    return ranked


# --- Internal mobility ------------------------------------------------------


def internal_mobility(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """(promotions + lateral transfers) / average headcount.

    docs/METRICS.md counts exactly those two event types. Hires and terminations are
    movement but not mobility; including them would multiply the rate several-fold.

    Average headcount is `sum of monthly headcount / months in the requested period`, and
    the month count is computed here rather than read from the view. **A pre-divided
    average can only be re-aggregated along the dimensions it was not divided by.** An
    earlier version summed a per-year average across years, which is how the whole-window
    call came to report an average headcount of 4,760 for a company of 1,194 — and to emit
    that number through the API as a field the frontend would have rendered.

    The rate is annualized so a partial-year window stays comparable with a full one.
    """
    stmt = select(
        func.sum(v_mobility_monthly.c.promotions).label("promotions"),
        func.sum(v_mobility_monthly.c.lateral_transfers).label("lateral_transfers"),
        func.sum(cast(v_mobility_monthly.c.avg_headcount, Numeric)).label("headcount_months"),
        func.count(func.distinct(v_mobility_monthly.c.month_start)).label("months"),
    )
    stmt = apply_filters(stmt, v_mobility_monthly, filters, period_column="month_start")
    row = db.execute(stmt).mappings().one()

    return _mobility_result(row)


def _mobility_result(row: Any, *, year: int | None = None) -> dict[str, Any]:
    """Shared shaping for the whole-window and per-year mobility results."""
    promotions = int(row["promotions"] or 0)
    transfers = int(row["lateral_transfers"] or 0)
    events = promotions + transfers
    months = int(row["months"] or 0)
    avg_headcount = _ratio(row["headcount_months"], months)

    result: dict[str, Any] = {
        "promotions": promotions,
        "lateral_transfers": transfers,
        "mobility_events": events,
        "headcount_months": _num(row["headcount_months"]),
        "months": months,
        "avg_headcount": avg_headcount,
        "mobility_rate": (
            None if not avg_headcount or not months else events * (12.0 / months) / avg_headcount
        ),
    }
    if year is not None:
        return {"year": year, **result}
    return result


def mobility_by_year(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Internal mobility broken out per year, for the trend chart.

    Months are counted within each year, so a partial year at either end of the window
    annualizes correctly instead of reading as a slow year.
    """
    stmt = select(
        v_mobility_monthly.c.year,
        func.sum(v_mobility_monthly.c.promotions).label("promotions"),
        func.sum(v_mobility_monthly.c.lateral_transfers).label("lateral_transfers"),
        func.sum(cast(v_mobility_monthly.c.avg_headcount, Numeric)).label("headcount_months"),
        func.count(func.distinct(v_mobility_monthly.c.month_start)).label("months"),
    ).group_by(v_mobility_monthly.c.year)
    stmt = apply_filters(stmt, v_mobility_monthly, filters, period_column="month_start")
    stmt = stmt.order_by(v_mobility_monthly.c.year)

    return [
        _mobility_result(row, year=int(row["year"])) for row in db.execute(stmt).mappings().all()
    ]


__all__ = [
    "attrition_by_manager",
    "attrition_rate",
    "attrition_total",
    "cohort_retention",
    "cohort_survival_curve",
    "headcount_series",
    "internal_mobility",
    "mobility_by_year",
    "regretted_attrition",
    "tenure_distribution",
]
