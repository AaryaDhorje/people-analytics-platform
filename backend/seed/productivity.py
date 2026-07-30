"""Timesheets, absence, goals, revenue, training, and performance reviews.

Hours are chosen by solving the metric definitions backwards, which is the only way
scenario 5's two targets can both hold at once:

    Overtime Rate = hours_over_40 / total_hours = 0.22  ->  total = 40 / 0.78 = 51.3
    Utilization   = billable / available       = 0.96  ->  billable = 38.4 of 40

So Support logs ~51.3 hours a week against 40 available, 38.4 of them billable.
Picking hours first and hoping the ratios landed would satisfy at most one target.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.models.enums import AbsenceType, GoalStatus
from seed import scenarios as sc
from seed.people import Person
from seed.reference import (
    COURSES,
    DEPARTMENT_IDS,
    DEPARTMENT_OUTPUT,
    REVENUE_DEPARTMENTS,
    WINDOW_END,
    WINDOW_START,
)
from seed.spine import is_workday
from seed.util import add_months, dec, iter_months, iter_quarters, iter_weeks, month_end

#: (utilization, total weekly hours) per billable department. Support's pair is
#: derived from scenario 5's overtime and utilization targets.
WORK_PROFILE: dict[str, tuple[float, float]] = {
    "ENG": (0.82, 43.0),
    "SUP": (sc.SUPPORT_UTILIZATION, 40.0 / (1.0 - sc.SUPPORT_OVERTIME_RATE)),
    "OPS": (0.79, 41.5),
}

#: Weekly output ranges per department, in that department's output unit.
OUTPUT_RANGE: dict[str, tuple[float, float]] = {
    "ENG": (7.0, 15.0),
    "SUP": (30.0, 56.0),
    "OPS": (18.0, 36.0),
}

#: Baseline unplanned absence days per employee-month.
ABSENCE_LAMBDA = 0.50
ABSENCE_DEPARTMENT_FACTOR: dict[str, float] = {
    "SUP": 1.35,
    "SAL": 1.10,
    "ENG": 0.95,
    "OPS": 1.05,
    "PRD": 0.85,
    "MKT": 0.95,
    "FIN": 0.80,
    "PPL": 0.85,
}

#: Quarterly revenue per FTE, by department, before the growth trend.
REVENUE_PER_FTE: dict[str, float] = {
    "SAL": 118_000.0,
    "ENG": 62_000.0,
    "SUP": 34_000.0,
    "OPS": 41_000.0,
    "PRD": 48_000.0,
}

GOAL_TITLES = (
    "Reduce median time to resolution",
    "Ship the reporting rewrite",
    "Grow qualified pipeline",
    "Cut onboarding time for new hires",
    "Improve release frequency",
    "Close the quarter within budget",
    "Raise CSAT on tier-two tickets",
    "Deliver the data migration",
    "Reduce manual reconciliation steps",
    "Launch the partner integration",
)


@dataclass
class ProductivityData:
    timesheets: list[dict[str, object]]
    goals: list[dict[str, object]]
    revenue: list[dict[str, object]]
    training: list[dict[str, object]]
    absences: list[dict[str, object]]
    reviews: list[dict[str, object]]


def _workdays_in_week(monday: date) -> int:
    return sum(1 for offset in range(5) if is_workday(monday + timedelta(days=offset)))


def _support_absence_multiplier(month_first: date) -> float:
    """Support's absenteeism climbs across the final months of the window."""
    ramp_start = add_months(WINDOW_END.replace(day=1), -(sc.SUPPORT_ABSENCE_CLIMB_MONTHS - 1))
    if month_first < ramp_start:
        return 1.0
    elapsed = (month_first.year - ramp_start.year) * 12 + (month_first.month - ramp_start.month)
    progress = elapsed / max(1, sc.SUPPORT_ABSENCE_CLIMB_MONTHS - 1)
    return 1.0 + (sc.SUPPORT_ABSENCE_CLIMB_FACTOR - 1.0) * progress


def build_timesheets(people: list[Person], rng: np.random.Generator) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    timesheet_id = 0
    weeks = iter_weeks(WINDOW_START, WINDOW_END)

    for person in people:
        if person.is_manager:
            continue
        for monday in weeks:
            if not person.active_on(monday):
                continue
            department, _, _, _ = person.state_at(monday)
            profile = WORK_PROFILE.get(department)
            if profile is None:
                continue

            utilization_target, total_target = profile
            fte = float(person.fte)
            available = _workdays_in_week(monday) * 8.0 * fte
            if available <= 0:
                continue

            total = max(4.0, total_target * fte + float(rng.normal(0, 2.4)))
            billable = max(
                0.0, min(total, available * utilization_target + float(rng.normal(0, 2.0)))
            )
            non_billable = max(0.0, total - billable)

            low, high = OUTPUT_RANGE[department]
            output = float(rng.uniform(low, high)) * fte

            timesheet_id += 1
            rows.append(
                {
                    "timesheet_id": timesheet_id,
                    "employee_id": person.employee_id,
                    "department_id": DEPARTMENT_IDS[department],
                    "week_start": monday,
                    "billable_hours": dec(billable),
                    "non_billable_hours": dec(non_billable),
                    "available_hours": dec(available),
                    "output_units": dec(output),
                    "output_type": DEPARTMENT_OUTPUT[department],
                }
            )
    return rows


def build_absences(people: list[Person], rng: np.random.Generator) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    absence_id = 0
    months = iter_months(WINDOW_START, WINDOW_END)

    for person in people:
        for month_first in months:
            last = month_end(month_first)
            if not person.active_on(month_first) and not person.active_on(last):
                continue
            department, _, _, _ = person.state_at(month_first)

            lam = ABSENCE_LAMBDA * ABSENCE_DEPARTMENT_FACTOR.get(department, 1.0)
            if department == sc.SUPPORT_DEPARTMENT:
                lam *= _support_absence_multiplier(month_first)

            unplanned_days = int(rng.poisson(lam))
            planned_days = int(rng.poisson(0.35))

            for _ in range(unplanned_days):
                absence_id += 1
                day = month_first + timedelta(
                    days=int(rng.integers(0, (last - month_first).days + 1))
                )
                absence_type = (
                    AbsenceType.SICK if float(rng.random()) < 0.6 else AbsenceType.UNPLANNED
                )
                rows.append(
                    {
                        "absence_id": absence_id,
                        "employee_id": person.employee_id,
                        "absence_date": day,
                        "days": dec(1.0 if float(rng.random()) < 0.8 else 0.5),
                        "absence_type": absence_type,
                        "is_unplanned": True,
                    }
                )
            for _ in range(planned_days):
                absence_id += 1
                day = month_first + timedelta(
                    days=int(rng.integers(0, (last - month_first).days + 1))
                )
                rows.append(
                    {
                        "absence_id": absence_id,
                        "employee_id": person.employee_id,
                        "absence_date": day,
                        "days": dec(1.0),
                        "absence_type": AbsenceType.PTO,
                        "is_unplanned": False,
                    }
                )
    return rows


def build_reviews(people: list[Person], rng: np.random.Generator) -> list[dict[str, object]]:
    """A probation review near day 180, then annual reviews.

    The day-180 review is what makes Quality of Hire computable at all: it needs a
    rating for a new hire at exactly that milestone.
    """
    rows: list[dict[str, object]] = []
    review_id = 0

    for person in people:
        review_dates: list[tuple[date, date]] = []

        probation = person.hire_date + timedelta(days=180)
        if WINDOW_START <= probation <= WINDOW_END and person.active_on(probation):
            review_dates.append((person.hire_date, probation))

        anniversary = person.hire_date
        while anniversary <= WINDOW_END:
            anniversary = add_months(anniversary, 12)
            if WINDOW_START <= anniversary <= WINDOW_END and person.active_on(anniversary):
                review_dates.append((add_months(anniversary, -12), anniversary))

        if not review_dates:
            continue
        review_dates.sort(key=lambda pair: pair[1])

        for index, (period_start, review_date) in enumerate(review_dates):
            is_last = index == len(review_dates) - 1
            if is_last and person.force_last_rating is not None:
                rating = person.force_last_rating
            else:
                rating = int(clamp_rating(rng.normal(3.4, 0.85)))
            review_id += 1
            rows.append(
                {
                    "review_id": review_id,
                    "employee_id": person.employee_id,
                    "reviewer_id": person.manager_id,
                    "review_period_start": period_start,
                    "review_date": review_date,
                    "rating": rating,
                }
            )
    return rows


def clamp_rating(value: float) -> int:
    return int(max(1, min(5, round(value))))


def build_goals(
    people: list[Person], rng: np.random.Generator, scale: float
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    goal_id = 0
    quarters = iter_quarters(WINDOW_START, WINDOW_END)
    target_total = max(120, round(sc.GOALS * scale))
    per_quarter = max(4, target_total // len(quarters))

    for quarter in quarters:
        eligible = [p for p in people if p.active_on(quarter) and not p.is_manager]
        if not eligible:
            continue
        picks = rng.choice(len(eligible), size=min(per_quarter, len(eligible)), replace=False)
        for position in picks:
            person = eligible[int(position)]
            department, _, _, _ = person.state_at(quarter)
            target_value = float(rng.integers(10, 200))
            attainment = float(rng.normal(0.92, 0.24))
            actual_value = max(0.0, target_value * attainment)

            if attainment >= 1.0:
                status = GoalStatus.COMPLETE
            elif attainment >= 0.85:
                status = GoalStatus.ON_TRACK
            elif attainment >= 0.6:
                status = GoalStatus.AT_RISK
            else:
                status = GoalStatus.MISSED

            goal_id += 1
            rows.append(
                {
                    "goal_id": goal_id,
                    "employee_id": person.employee_id,
                    "department_id": DEPARTMENT_IDS[department],
                    "quarter_start": quarter,
                    "title": GOAL_TITLES[goal_id % len(GOAL_TITLES)],
                    "target_value": dec(target_value),
                    "actual_value": dec(actual_value),
                    "status": status,
                }
            )
    return rows


def build_revenue(people: list[Person], rng: np.random.Generator) -> list[dict[str, object]]:
    """Revenue per department per quarter, scaled to that quarter's actual FTE."""
    rows: list[dict[str, object]] = []
    quarters = iter_quarters(WINDOW_START, WINDOW_END)

    for index, quarter in enumerate(quarters):
        # Mild growth across the window so revenue per FTE trends rather than jitters.
        growth = 1.0 + 0.018 * index
        fte_by_department: dict[str, float] = {}
        for person in people:
            if not person.active_on(quarter):
                continue
            department, _, _, _ = person.state_at(quarter)
            if department in REVENUE_DEPARTMENTS:
                fte_by_department[department] = fte_by_department.get(department, 0.0) + float(
                    person.fte
                )

        for department, total_fte in sorted(fte_by_department.items()):
            per_fte = REVENUE_PER_FTE.get(department, 40_000.0)
            amount = total_fte * per_fte * growth * (1.0 + float(rng.normal(0, 0.045)))
            rows.append(
                {
                    "department_id": DEPARTMENT_IDS[department],
                    "quarter_start": quarter,
                    "revenue_amount": dec(max(0.0, amount)),
                }
            )
    return rows


def build_training(people: list[Person], rng: np.random.Generator) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    training_id = 0

    for person in people:
        n_courses = int(rng.integers(1, 4))
        for _ in range(n_courses):
            course = COURSES[int(rng.integers(len(COURSES)))]
            earliest = max(WINDOW_START, person.hire_date)
            latest = person.termination_date or WINDOW_END
            if earliest >= latest:
                continue
            assigned_on = earliest + timedelta(days=int(rng.integers(0, (latest - earliest).days)))

            completed = float(rng.random()) < 0.74
            completed_on = None
            hours = 0.0
            if completed:
                offset = int(rng.integers(3, 70))
                candidate = assigned_on + timedelta(days=offset)
                if candidate <= min(latest, WINDOW_END):
                    completed_on = candidate
                    hours = float(course["hours"]) * float(rng.uniform(0.8, 1.2))  # type: ignore[arg-type]
            else:
                hours = float(course["hours"]) * float(rng.uniform(0.0, 0.4))  # type: ignore[arg-type]

            training_id += 1
            rows.append(
                {
                    "training_id": training_id,
                    "employee_id": person.employee_id,
                    "course_code": course["code"],
                    "course_name": course["name"],
                    "assigned_on": assigned_on,
                    "completed_on": completed_on,
                    "hours": dec(hours),
                }
            )
    return rows


def build_productivity(
    people: list[Person], rng: np.random.Generator, scale: float
) -> ProductivityData:
    return ProductivityData(
        timesheets=build_timesheets(people, rng),
        goals=build_goals(people, rng, scale),
        revenue=build_revenue(people, rng),
        training=build_training(people, rng),
        absences=build_absences(people, rng),
        reviews=build_reviews(people, rng),
    )
