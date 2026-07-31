"""Productivity metrics.

Formulas from docs/METRICS.md verbatim. The theme of this domain is **denominators that
are not headcount**:

- Utilization divides by *available hours*, not by people.
- Revenue per FTE and Output per Head divide by *FTE*, so a part-timer producing
  proportionally less is not read as less productive.
- Span of Control divides by *managers who have reports*, not by everyone.
- Training divides by average headcount across the requested period, which is why
  `v_training_monthly` is monthly.

Two thresholds live in SQL rather than here, against this layer's usual rule: overtime's
40-hour line and goal attainment's 1.5 cap. Both apply per row and cannot be recovered
after aggregation — capping a team average at 1.5 is a different calculation from capping
each goal and then averaging.
"""

from typing import Any

from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.orm import Session

from app.metrics.filters import MetricFilters, apply_filters
from app.metrics.tables import (
    v_goal_attainment,
    v_revenue_per_fte,
    v_span_of_control,
    v_timesheet_weekly,
    v_training_monthly,
)

#: docs/METRICS.md: "AVG(goal_actual / goal_target) capped at 1.5". Applied per goal in
#: sql/views/43_v_goal_attainment.sql; named here so the value is greppable from Python.
GOAL_ATTAINMENT_CAP = 1.5

#: docs/METRICS.md: "hours_over_40 / total_hours". Applied per week in
#: sql/views/40_v_timesheet_weekly.sql.
OVERTIME_THRESHOLD_HOURS = 40


def _num(value: Any) -> float:
    return 0.0 if value is None else float(value)


def _ratio(numerator: Any, denominator: Any) -> float | None:
    if denominator is None or float(denominator) == 0.0:
        return None
    return float(numerator or 0) / float(denominator)


def _timesheet_totals(db: Session, filters: MetricFilters) -> dict[str, Any]:
    stmt = select(
        func.sum(cast(v_timesheet_weekly.c.billable_hours, Numeric)).label("billable_hours"),
        func.sum(cast(v_timesheet_weekly.c.non_billable_hours, Numeric)).label(
            "non_billable_hours"
        ),
        func.sum(cast(v_timesheet_weekly.c.available_hours, Numeric)).label("available_hours"),
        func.sum(cast(v_timesheet_weekly.c.total_hours, Numeric)).label("total_hours"),
        func.sum(cast(v_timesheet_weekly.c.overtime_hours, Numeric)).label("overtime_hours"),
        func.sum(cast(v_timesheet_weekly.c.output_units, Numeric)).label("output_units"),
        func.sum(cast(v_timesheet_weekly.c.fte, Numeric)).label("fte_weeks"),
        func.count().label("employee_weeks"),
    )
    stmt = apply_filters(stmt, v_timesheet_weekly, filters, period_column="week_start")
    return dict(db.execute(stmt).mappings().one())


# --- Utilization ------------------------------------------------------------


def utilization(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """billable_hours / available_hours.

    Null rather than zero where nobody files timesheets — a non-billable department has no
    utilization, which is different from having utilization of nothing.
    """
    row = _timesheet_totals(db, filters)
    return {
        "billable_hours": _num(row["billable_hours"]),
        "non_billable_hours": _num(row["non_billable_hours"]),
        "available_hours": _num(row["available_hours"]),
        "employee_weeks": int(row["employee_weeks"] or 0),
        "utilization": _ratio(row["billable_hours"], row["available_hours"]),
    }


def utilization_by_week(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Weekly utilization, for the heatmap in phase 5."""
    stmt = select(
        v_timesheet_weekly.c.week_start.label("period"),
        v_timesheet_weekly.c.department_id,
        func.sum(cast(v_timesheet_weekly.c.billable_hours, Numeric)).label("billable_hours"),
        func.sum(cast(v_timesheet_weekly.c.available_hours, Numeric)).label("available_hours"),
    ).group_by(v_timesheet_weekly.c.week_start, v_timesheet_weekly.c.department_id)
    stmt = apply_filters(stmt, v_timesheet_weekly, filters, period_column="week_start")
    stmt = stmt.order_by(v_timesheet_weekly.c.week_start, v_timesheet_weekly.c.department_id)

    return [
        {
            "period": row["period"],
            "department_id": row["department_id"],
            "billable_hours": _num(row["billable_hours"]),
            "available_hours": _num(row["available_hours"]),
            "utilization": _ratio(row["billable_hours"], row["available_hours"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Overtime ---------------------------------------------------------------


def overtime(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """hours_over_40 / total_hours.

    `overtime_hours` was computed per week in the view. Summing weekly overtime is valid;
    applying the 40-hour threshold to a summed total is not, and would report 2,300 hours
    of overtime on a 2,340-hour quarter.
    """
    row = _timesheet_totals(db, filters)
    return {
        "total_hours": _num(row["total_hours"]),
        "overtime_hours": _num(row["overtime_hours"]),
        "threshold_hours": OVERTIME_THRESHOLD_HOURS,
        "overtime_rate": _ratio(row["overtime_hours"], row["total_hours"]),
    }


def overtime_by_month(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    stmt = select(
        v_timesheet_weekly.c.month_start.label("period"),
        v_timesheet_weekly.c.department_id,
        func.sum(cast(v_timesheet_weekly.c.total_hours, Numeric)).label("total_hours"),
        func.sum(cast(v_timesheet_weekly.c.overtime_hours, Numeric)).label("overtime_hours"),
    ).group_by(v_timesheet_weekly.c.month_start, v_timesheet_weekly.c.department_id)
    stmt = apply_filters(stmt, v_timesheet_weekly, filters, period_column="month_start")
    stmt = stmt.order_by(v_timesheet_weekly.c.month_start, v_timesheet_weekly.c.department_id)

    return [
        {
            "period": row["period"],
            "department_id": row["department_id"],
            "total_hours": _num(row["total_hours"]),
            "overtime_hours": _num(row["overtime_hours"]),
            "overtime_rate": _ratio(row["overtime_hours"], row["total_hours"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Output per head --------------------------------------------------------


def output_per_head(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """Output units per FTE-week.

    docs/METRICS.md grains this by team and sprint; a sprint maps to the timesheet week,
    fixed in phase 2.
    """
    row = _timesheet_totals(db, filters)
    return {
        "output_units": _num(row["output_units"]),
        "fte_weeks": _num(row["fte_weeks"]),
        "employee_weeks": int(row["employee_weeks"] or 0),
        "output_per_fte": _ratio(row["output_units"], row["fte_weeks"]),
    }


# --- Revenue per FTE --------------------------------------------------------


def revenue_per_fte(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """revenue_in_period / avg_FTE, by department and quarter."""
    stmt = select(
        v_revenue_per_fte.c.department_id,
        v_revenue_per_fte.c.quarter_start.label("period"),
        func.sum(cast(v_revenue_per_fte.c.revenue_amount, Numeric)).label("revenue_amount"),
        func.sum(cast(v_revenue_per_fte.c.fte_months, Numeric)).label("fte_months"),
        func.max(v_revenue_per_fte.c.months_observed).label("months_observed"),
    ).group_by(v_revenue_per_fte.c.department_id, v_revenue_per_fte.c.quarter_start)
    stmt = apply_filters(stmt, v_revenue_per_fte, filters, period_column="quarter_start")
    stmt = stmt.order_by(v_revenue_per_fte.c.quarter_start, v_revenue_per_fte.c.department_id)

    rows: list[dict[str, Any]] = []
    for row in db.execute(stmt).mappings().all():
        months = int(row["months_observed"] or 0)
        avg_fte = _ratio(row["fte_months"], months)
        rows.append(
            {
                "department_id": row["department_id"],
                "period": row["period"],
                "revenue_amount": _num(row["revenue_amount"]),
                "fte_months": _num(row["fte_months"]),
                "months_observed": months,
                "avg_fte": avg_fte,
                "revenue_per_fte": _ratio(row["revenue_amount"], avg_fte),
            }
        )
    return rows


# --- Span of control --------------------------------------------------------


def span_of_control(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """AVG(direct reports per manager).

    Only managers who hold reports are counted. Treating every employee as a manager of
    zero would pull the company average below 1 and describe nobody.
    """
    stmt = select(
        func.sum(v_span_of_control.c.managers).label("managers"),
        func.sum(v_span_of_control.c.direct_reports).label("direct_reports"),
        func.max(v_span_of_control.c.largest_team).label("largest_team"),
    )
    stmt = apply_filters(stmt, v_span_of_control, filters, period_column="month_start")
    row = db.execute(stmt).mappings().one()

    return {
        "managers": int(row["managers"] or 0),
        "direct_reports": int(row["direct_reports"] or 0),
        "largest_team": int(row["largest_team"]) if row["largest_team"] is not None else None,
        "span": _ratio(row["direct_reports"], row["managers"]),
    }


def span_of_control_by_level(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    """Span grained by the manager's own department and level."""
    stmt = select(
        v_span_of_control.c.department_id,
        v_span_of_control.c.job_level_id,
        func.sum(v_span_of_control.c.managers).label("managers"),
        func.sum(v_span_of_control.c.direct_reports).label("direct_reports"),
    ).group_by(v_span_of_control.c.department_id, v_span_of_control.c.job_level_id)
    stmt = apply_filters(stmt, v_span_of_control, filters, period_column="month_start")
    stmt = stmt.order_by(v_span_of_control.c.department_id, v_span_of_control.c.job_level_id)

    return [
        {
            "department_id": row["department_id"],
            "job_level_id": row["job_level_id"],
            "managers": int(row["managers"] or 0),
            "direct_reports": int(row["direct_reports"] or 0),
            "span": _ratio(row["direct_reports"], row["managers"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Goal attainment --------------------------------------------------------


def goal_attainment(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """AVG(actual / target), each goal capped at 1.5 before averaging."""
    stmt = select(
        func.sum(v_goal_attainment.c.goals).label("goals"),
        func.sum(v_goal_attainment.c.goals_with_target).label("goals_with_target"),
        func.sum(cast(v_goal_attainment.c.capped_attainment_sum, Numeric)).label(
            "capped_attainment_sum"
        ),
        func.sum(v_goal_attainment.c.completed_goals).label("completed_goals"),
        func.sum(v_goal_attainment.c.missed_goals).label("missed_goals"),
    )
    stmt = apply_filters(stmt, v_goal_attainment, filters, period_column="quarter_start")
    row = db.execute(stmt).mappings().one()

    return {
        "goals": int(row["goals"] or 0),
        "goals_with_target": int(row["goals_with_target"] or 0),
        "capped_attainment_sum": _num(row["capped_attainment_sum"]),
        "completed_goals": int(row["completed_goals"] or 0),
        "missed_goals": int(row["missed_goals"] or 0),
        "cap": GOAL_ATTAINMENT_CAP,
        "attainment": _ratio(row["capped_attainment_sum"], row["goals_with_target"]),
    }


def goal_attainment_by_department(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    stmt = select(
        v_goal_attainment.c.department_id,
        func.sum(v_goal_attainment.c.goals_with_target).label("goals_with_target"),
        func.sum(cast(v_goal_attainment.c.capped_attainment_sum, Numeric)).label(
            "capped_attainment_sum"
        ),
        func.sum(v_goal_attainment.c.completed_goals).label("completed_goals"),
    ).group_by(v_goal_attainment.c.department_id)
    stmt = apply_filters(stmt, v_goal_attainment, filters, period_column="quarter_start")
    stmt = stmt.order_by(v_goal_attainment.c.department_id)

    return [
        {
            "department_id": row["department_id"],
            "goals_with_target": int(row["goals_with_target"] or 0),
            "completed_goals": int(row["completed_goals"] or 0),
            "attainment": _ratio(row["capped_attainment_sum"], row["goals_with_target"]),
        }
        for row in db.execute(stmt).mappings().all()
    ]


# --- Training ---------------------------------------------------------------


def training(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """SUM(training_hours) / average headcount, plus completion rate.

    Average headcount is `sum of monthly headcount / number of months in the period`. The
    month count comes from the query rather than from the view, because only the caller
    knows how many months were asked for — a team present for three months of a six-month
    window must average 0.5 of its size, not its full size.
    """
    stmt = select(
        func.sum(cast(v_training_monthly.c.training_hours, Numeric)).label("training_hours"),
        func.sum(v_training_monthly.c.assigned).label("assigned"),
        func.sum(v_training_monthly.c.completed).label("completed"),
        func.sum(cast(v_training_monthly.c.avg_headcount, Numeric)).label("headcount_months"),
        func.count(func.distinct(v_training_monthly.c.month_start)).label("months"),
    )
    stmt = apply_filters(stmt, v_training_monthly, filters, period_column="month_start")
    row = db.execute(stmt).mappings().one()

    months = int(row["months"] or 0)
    avg_headcount = _ratio(row["headcount_months"], months)

    return {
        "training_hours": _num(row["training_hours"]),
        "assigned": int(row["assigned"] or 0),
        "completed": int(row["completed"] or 0),
        "completion_rate": _ratio(row["completed"], row["assigned"]),
        "headcount_months": _num(row["headcount_months"]),
        "months": months,
        "avg_headcount": avg_headcount,
        "hours_per_head": _ratio(row["training_hours"], avg_headcount),
    }


def training_by_department(db: Session, filters: MetricFilters) -> list[dict[str, Any]]:
    stmt = select(
        v_training_monthly.c.department_id,
        func.sum(cast(v_training_monthly.c.training_hours, Numeric)).label("training_hours"),
        func.sum(v_training_monthly.c.assigned).label("assigned"),
        func.sum(v_training_monthly.c.completed).label("completed"),
        func.sum(cast(v_training_monthly.c.avg_headcount, Numeric)).label("headcount_months"),
        func.count(func.distinct(v_training_monthly.c.month_start)).label("months"),
    ).group_by(v_training_monthly.c.department_id)
    stmt = apply_filters(stmt, v_training_monthly, filters, period_column="month_start")
    stmt = stmt.order_by(v_training_monthly.c.department_id)

    rows: list[dict[str, Any]] = []
    for row in db.execute(stmt).mappings().all():
        avg_headcount = _ratio(row["headcount_months"], int(row["months"] or 0))
        rows.append(
            {
                "department_id": row["department_id"],
                "training_hours": _num(row["training_hours"]),
                "assigned": int(row["assigned"] or 0),
                "completed": int(row["completed"] or 0),
                "completion_rate": _ratio(row["completed"], row["assigned"]),
                "avg_headcount": avg_headcount,
                "hours_per_head": _ratio(row["training_hours"], avg_headcount),
            }
        )
    return rows


__all__ = [
    "GOAL_ATTAINMENT_CAP",
    "OVERTIME_THRESHOLD_HOURS",
    "goal_attainment",
    "goal_attainment_by_department",
    "output_per_head",
    "overtime",
    "overtime_by_month",
    "revenue_per_fte",
    "span_of_control",
    "span_of_control_by_level",
    "training",
    "training_by_department",
    "utilization",
    "utilization_by_week",
]
