"""Engagement metrics against `tiny_org`, with the arithmetic shown.

Both survey waves have exactly 8 respondents, and driver values are flat or near-flat so
every mean is exact.

    Wave 1  survey 1, quarter 2024-07-01, submitted 2024-09-10
      respondents  D-900 M-901 E-001 E-002 E-003 E-004 E-007 E-008
      eNPS         10    10    9     9     8     7     6     4
      manager      5     5     4     4     4     3     3     4    sum 32 -> 4.00 raw -> 75.00
      growth       4     4     3     3     3     3     2     4    sum 26 -> 3.25 raw -> 56.25
      recognition  3 for everyone                                 sum 24 -> 3.00 raw -> 50.00
      workload     2 for everyone                                 sum 16 -> 2.00 raw -> 25.00
      belonging    4 for everyone                                 sum 32 -> 4.00 raw -> 75.00
      index = 130 / (5 x 8) = 3.25 raw -> 56.25

    Wave 2  survey 2, quarter 2025-01-01, submitted 2025-03-10
      respondents  D-900 M-901 E-001 E-002 E-003 E-005 E-007 E-008
      eNPS         8     7     6     6     5     5     4     3
      manager 3, growth 2, recognition 3, workload 2, belonging 3 for everyone
      index = 104 / 40 = 2.60 raw -> 40.00

The 0-100 conversion is `(raw - 1) / 4 * 100` throughout.
"""

from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.metrics import engagement
from app.metrics.filters import MetricFilters

WAVE_1 = MetricFilters(date_from=date(2024, 7, 1), date_to=date(2024, 7, 1))
WAVE_2 = MetricFilters(date_from=date(2025, 1, 1), date_to=date(2025, 1, 1))
ALL = MetricFilters(date_from=date(2024, 1, 1), date_to=date(2025, 6, 30))
ENG, SUP = 1, 2


def _normalized(raw: float) -> float:
    return (raw - 1.0) / 4.0 * 100.0


# --- eNPS -------------------------------------------------------------------


def test_enps_for_wave_one(db: Session) -> None:
    """Promoters 10, 10, 9, 9 = 4. Detractors 6, 4 = 2. Passives 8, 7 = 2.

    (4/8 - 2/8) * 100 = +25
    """
    result = engagement.enps(db, WAVE_1)

    assert result["responses"] == 8
    assert result["promoters"] == 4
    assert result["passives"] == 2
    assert result["detractors"] == 2
    assert result["enps"] == pytest.approx(25.0)


def test_enps_can_be_negative(db: Session) -> None:
    """Wave 2 has no promoters and six detractors: (0/8 - 6/8) * 100 = -75.

    eNPS is a signed score on a -100..+100 scale, not a percentage of anything, so a
    negative result must survive rather than clamping at zero.
    """
    result = engagement.enps(db, WAVE_2)

    assert result["promoters"] == 0
    assert result["detractors"] == 6
    assert result["enps"] == pytest.approx(-75.0)


def test_enps_is_null_with_no_responses(db: Session) -> None:
    result = engagement.enps(db, MetricFilters(date_from=date(2030, 1, 1)))

    assert result["responses"] == 0
    assert result["enps"] is None


# --- Engagement index and drivers ------------------------------------------


def test_engagement_index_for_both_waves(db: Session) -> None:
    """Wave 1: 130 raw points over 40 answers = 3.25 -> 56.25 on the 0-100 scale.
    Wave 2: 104 / 40 = 2.60 -> 40.00.
    """
    assert engagement.engagement_index(db, WAVE_1)["engagement_index"] == pytest.approx(56.25)
    assert engagement.engagement_index(db, WAVE_2)["engagement_index"] == pytest.approx(40.0)


def test_driver_breakdown_for_wave_one(db: Session) -> None:
    drivers = engagement.driver_breakdown(db, WAVE_1)

    assert drivers["manager"] == pytest.approx(75.0)
    assert drivers["growth"] == pytest.approx(56.25)
    assert drivers["recognition"] == pytest.approx(50.0)
    assert drivers["workload"] == pytest.approx(25.0)
    assert drivers["belonging"] == pytest.approx(75.0)


def test_engagement_index_equals_the_mean_of_the_five_drivers(db: Session) -> None:
    """Both routes to the index must agree. They only do because the view sums raw points
    rather than averaging per driver and averaging again — `AVG(AVG(x))` would diverge
    here as soon as the driver means were not identical."""
    drivers = engagement.driver_breakdown(db, WAVE_1)
    index = engagement.engagement_index(db, WAVE_1)["engagement_index"]

    assert index == pytest.approx(sum(drivers.values()) / 5)


def test_driver_scores_are_normalized_to_the_zero_hundred_scale(db: Session) -> None:
    """Stored raw 1-5, reported 0-100. A driver of 3 is the midpoint, i.e. 50, not 60."""
    drivers = engagement.driver_breakdown(db, WAVE_2)

    assert drivers["manager"] == pytest.approx(_normalized(3.0))
    assert drivers["growth"] == pytest.approx(_normalized(2.0))


def test_driver_trend_shows_the_fall_between_waves(db: Session) -> None:
    """Manager 75.00 -> 50.00 and growth 56.25 -> 25.00. This is the shape the post-reorg
    dip takes in the real warehouse."""
    trend = {row["period"]: row for row in engagement.driver_trend(db, ALL)}

    assert trend[date(2024, 7, 1)]["manager"] == pytest.approx(75.0)
    assert trend[date(2025, 1, 1)]["manager"] == pytest.approx(50.0)
    assert trend[date(2024, 7, 1)]["growth"] == pytest.approx(56.25)
    assert trend[date(2025, 1, 1)]["growth"] == pytest.approx(25.0)


# --- Participation ----------------------------------------------------------


def test_participation_uses_eligible_headcount_as_the_denominator(db: Session) -> None:
    """Wave 1 closed 2024-09-30 with 12 people employed: 8 / 12 = 66.67%.
    Wave 2 closed 2025-03-31 with 11 employed: 8 / 11 = 72.73%.

    The denominator moves between waves because the org did. Using a fixed headcount
    would misreport both.
    """
    by_survey = {row["survey_id"]: row for row in engagement.participation(db, ALL)}

    assert by_survey[1]["responses"] == 8
    assert by_survey[1]["eligible_employees"] == 12
    assert by_survey[1]["participation_rate"] == pytest.approx(8 / 12)

    assert by_survey[2]["responses"] == 8
    assert by_survey[2]["eligible_employees"] == 11
    assert by_survey[2]["participation_rate"] == pytest.approx(8 / 11)


def test_participation_never_exceeds_one(db: Session) -> None:
    """A rate above 100% would mean more responses than eligible people, which is the
    signature of counting responses from people who had already left."""
    for row in engagement.participation(db, ALL):
        assert row["participation_rate"] <= 1.0


# --- Engagement to attrition -----------------------------------------------


def test_bottom_engagement_quartile_leaves_more_than_the_top(db: Session) -> None:
    """Wave 1 per-person index, ascending:

        E-007 2.8   E-004 3.0   E-001/E-002/E-003 3.2   E-008 3.4   D-900/M-901 3.6

    Bottom quartile is E-007 and E-004; top is D-900 and M-901.

    Survey 1 **closes 2024-09-30**, so the follow-up window is the quarter beginning the
    month after: October, November, December 2024. The window is anchored to the close
    date, not to the survey's quarter_start of 2024-07-01 — anchoring to the quarter would
    start it in July, three months before anyone answered, and count exposure that
    predates the response it is meant to be a consequence of.

        E-004 left 2024-11-15 -> inside the window
        E-007 left 2025-03-31 -> outside it

        bottom  headcount-months = 1.5 (E-004: full October, half November)
                                 + 3.0 (E-007) = 4.5, with 1 termination
                                 -> 1 * 12 / 4.5 = 266.7%
        top     6.0 headcount-months, 0 terminations -> 0%
    """
    rows = {row["quartile"]: row for row in engagement.engagement_attrition_link(db, WAVE_1)}

    bottom, top = rows[1], rows[4]
    assert bottom["terminations"] == 1
    assert bottom["headcount_months"] == pytest.approx(4.5)
    assert bottom["annualized_rate"] == pytest.approx(12 / 4.5)

    assert top["terminations"] == 0
    assert top["annualized_rate"] == pytest.approx(0.0)
    assert bottom["annualized_rate"] > top["annualized_rate"]


def test_engagement_attrition_reports_all_four_quartiles(db: Session) -> None:
    quartiles = {row["quartile"] for row in engagement.engagement_attrition_link(db, WAVE_1)}

    assert quartiles == {1, 2, 3, 4}


# --- Absenteeism ------------------------------------------------------------


def test_absenteeism_rate_for_february_2025(db: Session) -> None:
    """Three unplanned days (E-001 twice, E-007 once). E-002's PTO day is planned and
    excluded.

        February 2025 has 20 workdays; average headcount is 11.
        available workdays = 11 x 20 = 220
        rate = 3 / 220 = 1.36%
    """
    february = MetricFilters(date_from=date(2025, 2, 1), date_to=date(2025, 2, 1))
    result = engagement.absenteeism(db, february)

    assert result["unplanned_days"] == pytest.approx(3.0)
    assert result["workdays"] == 20
    assert result["available_workdays"] == pytest.approx(220.0)
    assert result["absenteeism_rate"] == pytest.approx(3 / 220)


def test_absenteeism_excludes_planned_leave(db: Session) -> None:
    """Booked leave is a plan, not absenteeism. Four absence days exist in February but
    only three are unplanned."""
    february = MetricFilters(date_from=date(2025, 2, 1), date_to=date(2025, 2, 1))
    result = engagement.absenteeism(db, february)

    assert result["total_absence_days"] == pytest.approx(4.0)
    assert result["planned_days"] == pytest.approx(1.0)
    assert result["unplanned_days"] == pytest.approx(3.0)


def test_absenteeism_denominator_scales_with_headcount(db: Session) -> None:
    """ENG holds 7 people in February and SUP holds 4, against the same 20 workdays.

        ENG  2 unplanned / (7 x 20) = 2/140 = 1.43%
        SUP  1 unplanned / (4 x 20) = 1/80  = 1.25%

    SUP has half the absence days of ENG but a comparable rate, which is the entire point
    of dividing by capacity rather than by day count.
    """
    february = MetricFilters(date_from=date(2025, 2, 1), date_to=date(2025, 2, 1))

    eng = engagement.absenteeism(db, replace(february, department_id=ENG))
    sup = engagement.absenteeism(db, replace(february, department_id=SUP))

    assert eng["available_workdays"] == pytest.approx(140.0)
    assert eng["absenteeism_rate"] == pytest.approx(2 / 140)
    assert sup["available_workdays"] == pytest.approx(80.0)
    assert sup["absenteeism_rate"] == pytest.approx(1 / 80)


# --- Comment themes ---------------------------------------------------------


def test_comment_themes_aggregate_volume_and_confidence(db: Session) -> None:
    """Two wave-1 comments were classified as Workload/negative with confidence 0.90 and
    0.85, giving volume 2 and mean confidence 0.875."""
    rows = engagement.comment_themes(db, WAVE_1)

    assert len(rows) == 1
    theme = rows[0]
    assert theme["theme"] == "Workload"
    assert theme["sentiment"] == "negative"
    assert theme["volume"] == 2
    assert theme["mean_confidence"] == pytest.approx(0.875)


def test_comment_themes_are_empty_rather_than_erroring_before_phase_six(db: Session) -> None:
    """Wave 2's comments are unclassified. An unpopulated theme table must read as "no
    themes yet", not as a failure — phase 6 fills it, and the dashboard has to render
    before then."""
    assert engagement.comment_themes(db, WAVE_2) == []


# --- Filter contract -------------------------------------------------------


def test_absenteeism_rejects_a_manager_filter_it_cannot_honour(db: Session) -> None:
    from app.metrics.filters import UnsupportedFilterError

    with pytest.raises(UnsupportedFilterError):
        engagement.absenteeism(db, MetricFilters(manager_id="M-901"))
