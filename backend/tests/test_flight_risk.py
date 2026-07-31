"""Flight risk scoring.

Most of these need no database: the component functions are pure, which is the point of
keeping the weighting in Python rather than in SQL. A score that has to be explained live
on camera should be testable by reading it.

The integration tests at the bottom run against `tiny_org` and check structure — that
every active employee is scored, that contributions reconcile to the total, and that
persistence round-trips — rather than pinning a specific person's score, which would be a
brittle restatement of the weights.
"""

import pytest
from sqlalchemy.orm import Session

from app.metrics import flight_risk as fr
from app.models.enums import RiskBand

# --- Weights and banding ----------------------------------------------------


def test_weights_sum_to_one() -> None:
    """A drifting total silently rescales every score without changing any component, so
    the error would show up as "everyone got riskier" with no visible cause."""
    assert sum(fr.WEIGHTS.values()) == pytest.approx(1.0)


def test_every_weight_is_positive() -> None:
    for name, weight in fr.WEIGHTS.items():
        assert weight > 0, f"{name} contributes nothing"


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, RiskBand.LOW),
        (24.9, RiskBand.LOW),
        (25.0, RiskBand.MODERATE),
        (49.9, RiskBand.MODERATE),
        (50.0, RiskBand.ELEVATED),
        (69.9, RiskBand.ELEVATED),
        (70.0, RiskBand.HIGH),
        (100.0, RiskBand.HIGH),
    ],
)
def test_band_boundaries(score: float, expected: RiskBand) -> None:
    """70 is the boundary that matters: only HIGH earns the reserved accent colour, so it
    decides what a viewer reads as urgent."""
    assert fr.band_for(score) is expected


# --- Tenure -----------------------------------------------------------------


def test_tenure_risk_peaks_between_one_and_two_years() -> None:
    """New joiners are still invested in a decision they just made; people past four years
    have chosen to stay. The peak sits where the original reasons have worn off."""
    peak = fr.score_tenure(18)

    assert peak == 100.0
    assert fr.score_tenure(3) < peak
    assert fr.score_tenure(36) < peak
    assert fr.score_tenure(60) < fr.score_tenure(36)


def test_tenure_scores_stay_in_range() -> None:
    for months in (0, 5, 6, 11, 12, 23, 24, 47, 48, 200):
        assert 0.0 <= fr.score_tenure(months) <= 100.0


# --- Promotion gap ----------------------------------------------------------


def test_promotion_gap_rises_monotonically() -> None:
    scores = [fr.score_promotion_gap(m) for m in (0, 6, 12, 18, 24, 30, 36, 48)]

    assert scores == sorted(scores)
    assert scores[-1] == 100.0


# --- Engagement delta -------------------------------------------------------


def test_engagement_delta_is_measured_against_the_department() -> None:
    """Scoring 3.0 where peers average 3.1 is unremarkable; scoring 3.0 where peers
    average 4.0 is a signal. The same absolute score gives very different risk."""
    unremarkable = fr.score_engagement_delta(3.0, 3.1)
    concerning = fr.score_engagement_delta(3.0, 4.0)

    assert concerning > unremarkable
    assert unremarkable == pytest.approx(52.5)  # 50 + 0.1 * 25
    assert concerning == pytest.approx(75.0)  # 50 + 1.0 * 25


def test_scoring_above_the_department_mean_lowers_risk() -> None:
    assert fr.score_engagement_delta(4.5, 3.5) == pytest.approx(25.0)


def test_a_missing_survey_response_is_neutral_not_zero() -> None:
    """Never having answered a survey is not evidence of disengagement. Scoring silence as
    a zero would put every new joiner near the top of the list."""
    assert fr.score_engagement_delta(None, 3.5) == fr.NEUTRAL
    assert fr.score_engagement_delta(3.5, None) == fr.NEUTRAL


def test_engagement_delta_is_clamped() -> None:
    assert fr.score_engagement_delta(1.0, 5.0) == 100.0
    assert fr.score_engagement_delta(5.0, 1.0) == 0.0


# --- Manager attrition ------------------------------------------------------


def test_manager_at_company_rate_scores_forty() -> None:
    assert fr.score_manager_attrition(10, 100, 10, 100) == pytest.approx(40.0)


def test_manager_at_double_the_company_rate_scores_higher() -> None:
    """This is the component that makes a bad manager's reports surface without anyone
    having named the manager."""
    doubled = fr.score_manager_attrition(20, 100, 10, 100)

    assert doubled == pytest.approx(80.0)
    assert doubled > fr.score_manager_attrition(10, 100, 10, 100)


def test_manager_attrition_saturates_rather_than_exceeding_one_hundred() -> None:
    assert fr.score_manager_attrition(100, 100, 10, 100) == 100.0


def test_manager_with_no_history_is_assumed_average() -> None:
    """A brand-new manager has no record. Assuming the worst would be unfair; assuming
    the best would hide risk. Company-average is the honest default."""
    assert fr.score_manager_attrition(0, 0, 10, 100) == 40.0


# --- Comp percentile --------------------------------------------------------


def test_bottom_of_band_is_maximum_risk() -> None:
    assert fr.score_comp_percentile(50_000, 50_000, 100_000) == pytest.approx(100.0)


def test_top_of_band_is_minimum_risk() -> None:
    assert fr.score_comp_percentile(100_000, 50_000, 100_000) == pytest.approx(0.0)


def test_midpoint_of_band_is_fifty() -> None:
    assert fr.score_comp_percentile(75_000, 50_000, 100_000) == pytest.approx(50.0)


def test_comp_outside_the_band_is_clamped() -> None:
    assert fr.score_comp_percentile(120_000, 50_000, 100_000) == pytest.approx(0.0)
    assert fr.score_comp_percentile(10_000, 50_000, 100_000) == pytest.approx(100.0)


def test_a_zero_width_band_is_neutral() -> None:
    """A misconfigured band must not produce a divide-by-zero or a fabricated extreme."""
    assert fr.score_comp_percentile(80_000, 80_000, 80_000) == fr.NEUTRAL


# --- Composition ------------------------------------------------------------


def test_a_maximally_risky_profile_scores_one_hundred() -> None:
    """Every component at its worst must total exactly 100, which is only true if the
    weights sum to 1."""
    row = {
        "employee_id": "E-0001",
        "as_of_month": None,
        "tenure_months": 18,  # peak band
        "months_since_promotion": 48,
        "employee_raw_index": 1.0,
        "department_raw_index": 5.0,
        "manager_terminations": 100,
        "manager_headcount_months": 100,
        "company_terminations": 10,
        "company_headcount_months": 100,
        "comp_amount": 50_000,
        "comp_band_min": 50_000,
        "comp_band_max": 100_000,
    }
    score = fr.score_row(row)

    assert score.score == pytest.approx(100.0)
    assert score.band is RiskBand.HIGH


def test_contributions_reconcile_to_the_total() -> None:
    row = {
        "employee_id": "E-0002",
        "as_of_month": None,
        "tenure_months": 30,
        "months_since_promotion": 14,
        "employee_raw_index": 3.4,
        "department_raw_index": 3.6,
        "manager_terminations": 3,
        "manager_headcount_months": 60,
        "company_terminations": 10,
        "company_headcount_months": 100,
        "comp_amount": 82_000,
        "comp_band_min": 72_000,
        "comp_band_max": 99_000,
    }
    score = fr.score_row(row)

    total = sum(part["contribution"] for part in score.components.values())
    assert score.score == pytest.approx(total, abs=0.02)
    assert set(score.components) == set(fr.WEIGHTS)


def test_explain_returns_one_sentence_per_component_worst_first() -> None:
    """The expandable reason table in phase 5 and the narrative in phase 6 both read this,
    so the ordering has to put the driving factor first."""
    row = {
        "employee_id": "E-0003",
        "as_of_month": None,
        "tenure_months": 18,
        "months_since_promotion": 6,
        "employee_raw_index": 3.5,
        "department_raw_index": 3.5,
        "manager_terminations": 0,
        "manager_headcount_months": 50,
        "company_terminations": 10,
        "company_headcount_months": 100,
        "comp_amount": 95_000,
        "comp_band_min": 72_000,
        "comp_band_max": 99_000,
    }
    lines = fr.score_row(row).explain()

    assert len(lines) == len(fr.WEIGHTS)
    assert lines[0].startswith("Tenure band")  # the only component at 100 here


# --- Against tiny_org -------------------------------------------------------


def test_every_active_employee_is_scored(db: Session) -> None:
    """Ten of the twelve fixture employees are active at the window end."""
    scores = fr.compute(db)

    assert len(scores) == 10
    assert all(0.0 <= score.score <= 100.0 for score in scores)
    assert all(set(score.components) == set(fr.WEIGHTS) for score in scores)


def test_terminated_employees_are_not_scored(db: Session) -> None:
    """E-004 and E-007 have left. Scoring the departed would be both useless and, on a
    screen labelled "flight risk", misleading."""
    scored = {score.employee_id for score in fr.compute(db)}

    assert "E-004" not in scored
    assert "E-007" not in scored


def test_scores_persist_and_read_back(db: Session) -> None:
    scores = fr.compute(db)
    written = fr.persist(db, scores)

    assert written == 10

    top = fr.top_risks(db, limit=3)
    assert len(top) == 3
    assert top[0]["score"] >= top[-1]["score"]
    assert set(top[0]["components"]) == set(fr.WEIGHTS)


def test_persist_replaces_rather_than_duplicating(db: Session) -> None:
    """Recomputing must not accumulate. Two runs of the same month leave one row each."""
    scores = fr.compute(db)
    fr.persist(db, scores)
    fr.persist(db, scores)

    assert len(fr.top_risks(db, limit=100)) == 10
