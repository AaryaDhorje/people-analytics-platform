"""Talent acquisition metrics against `tiny_org`, with the arithmetic shown.

The fixture's recruiting data in full:

    R-001  ENG, L1, FILLED   opened 2024-06-20, offer accepted 2024-07-15
           cost 4,000 internal + 6,000 external = 10,000, 1 hire (E-006)
           time to fill = 15 Jul - 20 Jun = 25 days
    R-002  SUP, L2, OPEN     opened 2025-04-17, no hires
           cost 2,000 + 1,000 = 3,000
           age at window end (2025-06-30) = 13 + 31 + 30 = 74 days

    app  req    source     applied      furthest    outcome
    1    R-001  REFERRAL   2024-06-25   HIRED       accepted 2024-07-15 -> E-006
    2    R-001  AGENCY     2024-06-26   OFFER       declined 2024-07-14
    3    R-001  JOBBOARD   2024-06-27   INTERVIEW   rejected 2024-07-09
    4    R-001  JOBBOARD   2024-06-28   SCREEN      rejected 2024-07-06
    5    R-001  AGENCY     2024-06-29   APPLIED     rejected 2024-07-02
    6    R-002  JOBBOARD   2025-05-01   SCREEN      in flight
    7    R-002  REFERRAL   2025-05-02   APPLIED     in flight

    R-001 funnel: 5 -> 4 -> 3 -> 2 -> 1
    all reqs:     7 -> 5 -> 3 -> 2 -> 1

Employees carrying a hire channel (only those hired inside the window):

    E-004  AGENCY    2024-02-01, left 2024-11-15, review 2024-08-01 rating 4
    E-005  JOBBOARD  2024-03-01, active,          review 2024-09-01 rating 2
    E-006  REFERRAL  2024-08-01, active,          review 2025-02-01 rating 4
"""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.metrics import acquisition
from app.metrics.filters import MetricFilters

WINDOW = MetricFilters(date_from=date(2024, 1, 1), date_to=date(2025, 6, 30))
ENG = 1
SUP = 2
REFERRAL, AGENCY, JOBBOARD = 1, 2, 3


# --- Time to fill -----------------------------------------------------------


def test_time_to_fill_is_measured_from_requisition_open(db: Session) -> None:
    """R-001: opened 2024-06-20, accepted 2024-07-15.

        June 20 -> 30 is 10 days, plus 15 in July = 25 days.

    R-002 has no accepted offer, so it contributes nothing rather than a zero.
    """
    result = acquisition.time_to_fill(db, WINDOW)

    assert result["filled_positions"] == 1
    assert result["mean_days"] == pytest.approx(25.0)


def test_time_to_fill_is_null_when_nothing_was_filled(db: Session) -> None:
    """SUP holds only the open requisition. A mean over zero fills must be null; zero
    days would claim instant hiring."""
    result = acquisition.time_to_fill(db, MetricFilters(department_id=SUP))

    assert result["filled_positions"] == 0
    assert result["mean_days"] is None


# --- Time to hire -----------------------------------------------------------


def test_time_to_hire_is_measured_from_first_application(db: Session) -> None:
    """Application 1: applied 2024-06-25, accepted 2024-07-15 = 20 days.

    Five days shorter than time to fill, because the requisition was already open when
    this candidate applied. Conflating the two is a standard reporting error.
    """
    result = acquisition.time_to_hire(db, WINDOW)

    assert result["observations"] == 1
    assert result["mean_days"] == pytest.approx(20.0)


# --- Funnel -----------------------------------------------------------------


def test_funnel_conversion_for_the_filled_requisition(db: Session) -> None:
    """ENG (R-001 only): 5 -> 4 -> 3 -> 2 -> 1.

    screen/applied    = 4/5 = 0.8
    interview/screen  = 3/4 = 0.75
    offer/interview   = 2/3 = 0.666...
    hired/offer       = 1/2 = 0.5
    """
    rows = acquisition.funnel(db, MetricFilters(department_id=ENG))
    by_stage = {row["stage"]: row for row in rows}

    assert by_stage["applied"]["applications"] == 5
    assert by_stage["screen"]["applications"] == 4
    assert by_stage["interview"]["applications"] == 3
    assert by_stage["offer"]["applications"] == 2
    assert by_stage["hired"]["applications"] == 1

    assert by_stage["applied"]["conversion_from_previous"] is None
    assert by_stage["screen"]["conversion_from_previous"] == pytest.approx(4 / 5)
    assert by_stage["interview"]["conversion_from_previous"] == pytest.approx(3 / 4)
    assert by_stage["offer"]["conversion_from_previous"] == pytest.approx(2 / 3)
    assert by_stage["hired"]["conversion_from_previous"] == pytest.approx(1 / 2)


def test_funnel_across_all_requisitions(db: Session) -> None:
    """Both reqs: 7 -> 5 -> 3 -> 2 -> 1. R-002's two in-flight candidates add to applied
    and screen only."""
    by_stage = {row["stage"]: row["applications"] for row in acquisition.funnel(db, WINDOW)}

    assert by_stage == {"applied": 7, "screen": 5, "interview": 3, "offer": 2, "hired": 1}


def test_funnel_is_returned_in_stage_order(db: Session) -> None:
    stages = [row["stage"] for row in acquisition.funnel(db, WINDOW)]

    assert stages == ["applied", "screen", "interview", "offer", "hired"]


def test_funnel_never_widens_as_it_descends(db: Session) -> None:
    """Counting stage-event rows instead of distinct applications would let a re-entered
    stage exceed the one above it, producing a funnel that widens downward."""
    counts = [row["applications"] for row in acquisition.funnel(db, WINDOW)]

    assert counts == sorted(counts, reverse=True)


def test_stage_dwell_excludes_candidates_still_in_stage(db: Session) -> None:
    """ENG interview dwell: 5, 5 and 2 days over three candidates = 12/3 = 4 days.

    SUP's screen stage holds application 6 with no exit date. Counting an in-flight
    candidate as zero days would drag the mean down exactly where a pipeline is slowest,
    so it is excluded from the denominator and surfaced as `still_in_stage` instead.
    """
    eng = {row["stage"]: row for row in acquisition.funnel(db, MetricFilters(department_id=ENG))}
    assert eng["interview"]["mean_dwell_days"] == pytest.approx(12 / 3)

    sup = {row["stage"]: row for row in acquisition.funnel(db, MetricFilters(department_id=SUP))}
    assert sup["screen"]["still_in_stage"] == 1
    assert sup["screen"]["mean_dwell_days"] is None


# --- Offer acceptance -------------------------------------------------------


def test_offer_acceptance_rate(db: Session) -> None:
    """Two offers extended (applications 1 and 2), one accepted.

    1 / 2 = 50%
    """
    result = acquisition.offer_acceptance(db, WINDOW)

    assert result["offers_extended"] == 2
    assert result["offers_accepted"] == 1
    assert result["acceptance_rate"] == pytest.approx(0.5)


def test_offer_acceptance_is_null_with_no_offers(db: Session) -> None:
    result = acquisition.offer_acceptance(db, MetricFilters(department_id=SUP))

    assert result["offers_extended"] == 0
    assert result["acceptance_rate"] is None


# --- Cost per hire ----------------------------------------------------------


def test_cost_per_hire_by_department_and_quarter(db: Session) -> None:
    """ENG, Q2 2024: 10,000 of cost against 1 hire.

    SUP's only requisition is still open with 3,000 spent and no hire, so its cost per
    hire is null. Reporting 0 would say hiring was free; reporting 3,000 would invent a
    hire that has not happened.
    """
    rows = {
        (row["department_id"], row["period"]): row for row in acquisition.cost_per_hire(db, WINDOW)
    }

    eng = rows[(ENG, date(2024, 4, 1))]
    assert eng["total_cost"] == pytest.approx(10_000.0)
    assert eng["hires"] == 1
    assert eng["cost_per_hire"] == pytest.approx(10_000.0)

    sup = rows[(SUP, date(2025, 4, 1))]
    assert sup["total_cost"] == pytest.approx(3_000.0)
    assert sup["hires"] == 0
    assert sup["cost_per_hire"] is None


# --- Requisition aging ------------------------------------------------------


def test_requisition_aging_counts_only_open_reqs_past_sixty_days(db: Session) -> None:
    """R-002 has been open 74 days at the window end, so it is the only aged req. R-001
    is filled and cannot age, however long it took."""
    rows = {row["department_id"]: row for row in acquisition.requisition_aging(db, WINDOW)}

    assert rows[SUP]["open_requisitions"] == 1
    assert rows[SUP]["aged_requisitions"] == 1
    assert rows[SUP]["max_age_days"] == 74

    assert ENG not in rows or rows[ENG]["open_requisitions"] == 0


def test_requisition_age_is_measured_to_the_window_end_not_today(db: Session) -> None:
    """Measuring to CURRENT_DATE would make this number drift every day the demo is not
    run, and change under a reviewer's feet."""
    rows = {row["department_id"]: row for row in acquisition.requisition_aging(db, WINDOW)}

    assert rows[SUP]["max_age_days"] == 74


# --- Source effectiveness ---------------------------------------------------


def test_source_effectiveness_conversion_is_application_level(db: Session) -> None:
    """Applications and hires by channel:

    REFERRAL  2 applications (1, 7), 1 hire  -> 0.5
    AGENCY    2 applications (2, 5), 0 hires -> 0.0
    JOBBOARD  3 applications (3, 4, 6), 0    -> 0.0
    """
    rows = {row["source_id"]: row for row in acquisition.source_effectiveness(db, WINDOW)}

    assert rows[REFERRAL]["applications"] == 2
    assert rows[REFERRAL]["hires"] == 1
    assert rows[REFERRAL]["conversion_rate"] == pytest.approx(0.5)

    assert rows[AGENCY]["applications"] == 2
    assert rows[AGENCY]["conversion_rate"] == pytest.approx(0.0)

    assert rows[JOBBOARD]["applications"] == 3
    assert rows[JOBBOARD]["conversion_rate"] == pytest.approx(0.0)


def test_ninety_day_retention_is_employee_level(db: Session) -> None:
    """The retention half of Source Effectiveness counts *employees*, not applications:
    E-004, E-005 and E-006 each carry a channel, and all three cleared 90 days.

    E-004 left at day 288, which is after the 90-day milestone, so they count as
    retained at 90 days. Retention milestones are not "still here now".
    """
    rows = {row["source_id"]: row for row in acquisition.source_retention(db, WINDOW)}

    for source_id in (REFERRAL, AGENCY, JOBBOARD):
        assert rows[source_id]["eligible_90d"] == 1
        assert rows[source_id]["retained_90d"] == 1
        assert rows[source_id]["retention_90d"] == pytest.approx(1.0)


# --- Quality of hire --------------------------------------------------------


def test_quality_of_hire_requires_both_survival_and_rating(db: Session) -> None:
    """All three sourced hires survived to day 180, but only two were rated 3 or better:

        AGENCY    E-004  survived, rating 4  -> quality hire
        JOBBOARD  E-005  survived, rating 2  -> NOT a quality hire
        REFERRAL  E-006  survived, rating 4  -> quality hire

    E-005 is what stops this test passing on survival alone.
    """
    rows = {row["source_id"]: row for row in acquisition.quality_of_hire(db, WINDOW)}

    assert rows[AGENCY]["eligible_180d"] == 1
    assert rows[AGENCY]["quality_hires"] == 1
    assert rows[AGENCY]["quality_rate"] == pytest.approx(1.0)

    assert rows[JOBBOARD]["eligible_180d"] == 1
    assert rows[JOBBOARD]["retained_180d"] == 1
    assert rows[JOBBOARD]["quality_hires"] == 0
    assert rows[JOBBOARD]["quality_rate"] == pytest.approx(0.0)

    assert rows[REFERRAL]["quality_hires"] == 1


# --- Filter contract -------------------------------------------------------


def test_funnel_rejects_a_manager_filter_it_cannot_honour(db: Session) -> None:
    """The funnel view carries no manager column. Returning department-wide numbers for a
    manager-scoped request would be silently wrong."""
    from app.metrics.filters import UnsupportedFilterError

    with pytest.raises(UnsupportedFilterError):
        acquisition.funnel(db, MetricFilters(manager_id="M-901"))
