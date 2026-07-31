"""Productivity metrics against `tiny_org`, with the arithmetic shown.

Timesheets cover Q1 2025 only: 13 Mondays from 2025-01-06 to 2025-03-31, four employees.
Hours are picked so every ratio is exact.

    ENG  E-001, E-002   billable 32, non-billable  8, available 40  -> 40 total,  0 over 40
    SUP  E-007, E-008   billable 36, non-billable 14, available 40  -> 50 total, 10 over 40

    utilization   ENG 32/40 = 80%      SUP 36/40 = 90%
                  company 1768/2080 = 85% exactly
    overtime      ENG 0/1040 = 0%      SUP 260/1300 = 20%
                  company 260/2340 = 11.11%
    output/head   ENG 10 per week      SUP 40 per week

Q1 2025 headcount: ENG 7 (D-900, M-901, E-001, E-002, E-003, E-005, E-006), SUP 4
(M-902, E-007, E-008, E-009). Revenue is set to make revenue per FTE land on round
numbers: ENG 1,400,000 / 7 = 200,000 and SUP 400,000 / 4 = 100,000.

Four Q1 goals: 90/100, 110/100, 200/100 and 50/100. Capped at 1.5 they sum to
0.90 + 1.10 + 1.50 + 0.50 = 4.00 over 4 goals = exactly 1.00. Uncapped they would
average 1.125, so this fixture proves the cap fires.
"""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.metrics import productivity
from app.metrics.filters import MetricFilters

Q1_2025 = MetricFilters(date_from=date(2025, 1, 1), date_to=date(2025, 3, 31))
ALL = MetricFilters(date_from=date(2024, 1, 1), date_to=date(2025, 6, 30))
ENG, SUP = 1, 2


# --- Utilization ------------------------------------------------------------


def test_company_utilization_is_billable_over_available(db: Session) -> None:
    """1,768 billable hours against 2,080 available = 85% exactly."""
    result = productivity.utilization(db, Q1_2025)

    assert result["billable_hours"] == pytest.approx(1768.0)
    assert result["available_hours"] == pytest.approx(2080.0)
    assert result["utilization"] == pytest.approx(0.85)


def test_utilization_by_department(db: Session) -> None:
    eng = productivity.utilization(db, MetricFilters(date_from=date(2025, 1, 1), department_id=ENG))
    sup = productivity.utilization(db, MetricFilters(date_from=date(2025, 1, 1), department_id=SUP))

    assert eng["utilization"] == pytest.approx(0.8)
    assert sup["utilization"] == pytest.approx(0.9)


def test_utilization_is_null_where_nobody_files_timesheets(db: Session) -> None:
    """Finance is not a billable department, so it has no timesheets at all. A rate over
    zero available hours must be null, not zero — zero would read as "they did nothing"."""
    result = productivity.utilization(db, MetricFilters(department_id=3))

    assert result["available_hours"] == pytest.approx(0.0)
    assert result["utilization"] is None


# --- Overtime ---------------------------------------------------------------


def test_overtime_rate_is_hours_over_forty_across_total_hours(db: Session) -> None:
    """SUP logs 50 hours a week, 10 of them over 40, across 26 employee-weeks:

        260 / 1,300 = 20%

    ENG logs exactly 40 and therefore has no overtime at all.
    """
    sup = productivity.overtime(db, MetricFilters(date_from=date(2025, 1, 1), department_id=SUP))
    eng = productivity.overtime(db, MetricFilters(date_from=date(2025, 1, 1), department_id=ENG))

    assert sup["overtime_hours"] == pytest.approx(260.0)
    assert sup["total_hours"] == pytest.approx(1300.0)
    assert sup["overtime_rate"] == pytest.approx(0.2)

    assert eng["overtime_hours"] == pytest.approx(0.0)
    assert eng["overtime_rate"] == pytest.approx(0.0)


def test_overtime_threshold_is_applied_per_week_not_to_the_total(db: Session) -> None:
    """The company total is 2,340 hours across 52 employee-weeks. Applying the 40-hour
    threshold to that total would give max(2340 - 40, 0) = 2,300 hours of "overtime".

    Applied per week, as docs/METRICS.md means it, the answer is 260 / 2,340 = 11.11%.
    This is why v_timesheet_weekly stays at row grain.
    """
    result = productivity.overtime(db, Q1_2025)

    assert result["total_hours"] == pytest.approx(2340.0)
    assert result["overtime_hours"] == pytest.approx(260.0)
    assert result["overtime_rate"] == pytest.approx(260 / 2340)


# --- Output per head --------------------------------------------------------


def test_output_per_head_divides_by_fte_not_headcount(db: Session) -> None:
    """ENG books 10 story points per person-week over 26 employee-weeks = 260 units.
    SUP books 40 tickets per person-week = 1,040 units.

    Everyone in the fixture is 1.0 FTE, so per-FTE equals per-week output here — but the
    denominator is FTE-weeks, so a half-timer producing half the output would not read as
    half as productive.
    """
    eng = productivity.output_per_head(
        db, MetricFilters(date_from=date(2025, 1, 1), department_id=ENG)
    )
    sup = productivity.output_per_head(
        db, MetricFilters(date_from=date(2025, 1, 1), department_id=SUP)
    )

    assert eng["output_units"] == pytest.approx(260.0)
    assert eng["fte_weeks"] == pytest.approx(26.0)
    assert eng["output_per_fte"] == pytest.approx(10.0)

    assert sup["output_units"] == pytest.approx(1040.0)
    assert sup["output_per_fte"] == pytest.approx(40.0)


# --- Revenue per FTE --------------------------------------------------------


def test_revenue_per_fte_by_department(db: Session) -> None:
    """ENG holds 7 FTE through Q1 2025 against 1,400,000 of revenue = 200,000 per FTE.
    SUP holds 4 against 400,000 = 100,000."""
    rows = {row["department_id"]: row for row in productivity.revenue_per_fte(db, Q1_2025)}

    assert rows[ENG]["revenue_amount"] == pytest.approx(1_400_000.0)
    assert rows[ENG]["avg_fte"] == pytest.approx(7.0)
    assert rows[ENG]["revenue_per_fte"] == pytest.approx(200_000.0)

    assert rows[SUP]["avg_fte"] == pytest.approx(4.0)
    assert rows[SUP]["revenue_per_fte"] == pytest.approx(100_000.0)


def test_revenue_per_fte_uses_fte_not_headcount(db: Session) -> None:
    """Everyone here is full time, so FTE equals headcount — the test pins that the
    denominator is read from the FTE column rather than a row count, which only diverges
    once part-timers exist."""
    rows = {row["department_id"]: row for row in productivity.revenue_per_fte(db, Q1_2025)}

    assert rows[ENG]["fte_months"] == pytest.approx(21.0)  # 7 FTE x 3 months
    assert rows[ENG]["months_observed"] == 3


# --- Span of control --------------------------------------------------------


def test_span_of_control_at_window_end(db: Session) -> None:
    """June 2025 has three managers holding reports:

        D-900  M-901, M-902                                  = 2
        M-901  E-001, E-002, E-003, E-005, E-006             = 5
        M-902  E-008, E-009                                  = 2

    Nine reports across three managers = 3.0. Nine of the ten active employees have a
    manager; only D-900 does not.
    """
    june = MetricFilters(date_from=date(2025, 6, 1), date_to=date(2025, 6, 1))
    result = productivity.span_of_control(db, june)

    assert result["managers"] == 3
    assert result["direct_reports"] == 9
    assert result["span"] == pytest.approx(3.0)


def test_span_of_control_ignores_people_with_no_reports(db: Session) -> None:
    """Counting all ten employees as managers of zero would give a span of 0.9 and
    describe nothing that exists."""
    june = MetricFilters(date_from=date(2025, 6, 1), date_to=date(2025, 6, 1))
    result = productivity.span_of_control(db, june)

    assert result["managers"] == 3
    assert result["span"] > 1.0


# --- Goal attainment --------------------------------------------------------


def test_goal_attainment_caps_each_goal_at_one_point_five(db: Session) -> None:
    """0.90 + 1.10 + 1.50 + 0.50 = 4.00 over 4 goals = exactly 1.00.

    The third goal actually delivered 200% and is capped. Without the cap the average
    would be 1.125, so this assertion fails loudly if the cap is ever moved after the
    average instead of before it.
    """
    result = productivity.goal_attainment(db, Q1_2025)

    assert result["goals"] == 4
    assert result["capped_attainment_sum"] == pytest.approx(4.0)
    assert result["attainment"] == pytest.approx(1.0)
    assert result["attainment"] != pytest.approx(1.125)


def test_goal_attainment_by_department(db: Session) -> None:
    rows = {
        row["department_id"]: row for row in productivity.goal_attainment_by_department(db, Q1_2025)
    }

    # ENG: 0.90 + 1.10 = 2.00 over 2 goals.  SUP: 1.50 (capped from 2.00) + 0.50 = 2.00.
    assert rows[ENG]["attainment"] == pytest.approx(1.0)
    assert rows[SUP]["attainment"] == pytest.approx(1.0)
    assert rows[SUP]["completed_goals"] == 1


# --- Training ---------------------------------------------------------------


def test_training_hours_per_head_for_2025(db: Session) -> None:
    """7.5 hours across three assignments. Headcount over the six months of 2025 in the
    window is 11, 11, 11, 10, 10, 10 = 63 headcount-months, so average headcount is 10.5.

        7.5 / 10.5 = 0.714 hours per head
    """
    year_2025 = MetricFilters(date_from=date(2025, 1, 1), date_to=date(2025, 6, 30))
    result = productivity.training(db, year_2025)

    assert result["training_hours"] == pytest.approx(7.5)
    assert result["avg_headcount"] == pytest.approx(10.5)
    assert result["hours_per_head"] == pytest.approx(7.5 / 10.5)


def test_training_completion_rate(db: Session) -> None:
    """Three assigned, two completed. E-002 never finished theirs."""
    year_2025 = MetricFilters(date_from=date(2025, 1, 1), date_to=date(2025, 6, 30))
    result = productivity.training(db, year_2025)

    assert result["assigned"] == 3
    assert result["completed"] == 2
    assert result["completion_rate"] == pytest.approx(2 / 3)


def test_training_headcount_denominator_spans_the_whole_period(db: Session) -> None:
    """Support holds 4 people for three months and 3 for the next three, so its average
    across the half-year is 3.5 — not 4.

    This is why the view is grained monthly. A yearly view dividing each group's
    headcount-months by that group's *own* observed months would report E-007's London L2
    slot as a full-period presence when they left in March.
    """
    year_2025 = MetricFilters(date_from=date(2025, 1, 1), date_to=date(2025, 6, 30))

    sup = productivity.training(
        db, MetricFilters(date_from=date(2025, 1, 1), date_to=date(2025, 6, 30), department_id=SUP)
    )
    eng = productivity.training(
        db, MetricFilters(date_from=date(2025, 1, 1), date_to=date(2025, 6, 30), department_id=ENG)
    )

    assert sup["avg_headcount"] == pytest.approx(3.5)
    assert sup["training_hours"] == pytest.approx(5.0)
    assert sup["hours_per_head"] == pytest.approx(5 / 3.5)

    assert eng["avg_headcount"] == pytest.approx(7.0)
    assert eng["hours_per_head"] == pytest.approx(2.5 / 7)

    assert productivity.training(db, year_2025)["avg_headcount"] == pytest.approx(10.5)


# --- Filter contract -------------------------------------------------------


def test_goal_attainment_rejects_a_manager_filter_it_cannot_honour(db: Session) -> None:
    from app.metrics.filters import UnsupportedFilterError

    with pytest.raises(UnsupportedFilterError):
        productivity.goal_attainment(db, MetricFilters(manager_id="M-901"))
