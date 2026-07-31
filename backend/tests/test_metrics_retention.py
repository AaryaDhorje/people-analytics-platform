"""Retention metrics against `tiny_org`, with the arithmetic shown.

Every expectation below is a hand computation over the 12-employee fixture, written out
so a reviewer can check the maths without trusting the implementation. Where a value is
a fraction it is asserted as a fraction, not as a rounded decimal — `24 / 195.5`, never
`0.1228`.

The monthly headcount the whole domain rests on, straight from the fixture:

    month     start  end   avg    hires  exits
    2024-01     9     9     9.0     0      0
    2024-02    10    10    10.0     1      0   E-004 hired on the 1st
    2024-03    11    11    11.0     1      0   E-005 hired on the 1st
    2024-04..07 11   11    11.0     0      0
    2024-08    12    12    12.0     1      0   E-006 hired on the 1st
    2024-09    12    12    12.0     0      0
    2024-10    12    12    12.0     0      0
    2024-11    12    11    11.5     0      1   E-004 left on the 15th
    2024-12    11    11    11.0     0      0
    2025-01    11    11    11.0     0      0
    2025-02    11    11    11.0     0      0
    2025-03    11    11    11.0     0      1   E-007 left on the 31st, so still
    2025-04    10    10    10.0     0      0   counted at month end
    2025-05    10    10    10.0     0      0
    2025-06    10    10    10.0     0      0

    sum of avg_headcount over the 18 months = 195.5
    sum over calendar 2024 (12 months)      = 132.5
"""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.metrics import retention
from app.metrics.filters import MetricFilters

WINDOW = MetricFilters(date_from=date(2024, 1, 1), date_to=date(2025, 6, 1))

#: Sum of each month's average headcount across the 18-month window.
HEADCOUNT_MONTHS_WINDOW = 195.5
#: Same, for calendar 2024 only.
HEADCOUNT_MONTHS_2024 = 132.5


def _by_period(rows: list[dict], key: str = "period") -> dict:
    return {row[key]: row for row in rows}


# --- Headcount --------------------------------------------------------------


def test_headcount_series_covers_every_month(db: Session) -> None:
    rows = retention.headcount_series(db, WINDOW)

    assert len(rows) == 18
    assert rows[0]["period"] == date(2024, 1, 1)
    assert rows[-1]["period"] == date(2025, 6, 1)


def test_headcount_matches_the_fixture_month_by_month(db: Session) -> None:
    series = _by_period(retention.headcount_series(db, WINDOW))

    # Month-end headcount, per docs/METRICS.md: "COUNT(active employees) at month-end".
    assert series[date(2024, 1, 1)]["headcount"] == 9
    assert series[date(2024, 2, 1)]["headcount"] == 10  # + E-004
    assert series[date(2024, 3, 1)]["headcount"] == 11  # + E-005
    assert series[date(2024, 8, 1)]["headcount"] == 12  # + E-006
    assert series[date(2024, 11, 1)]["headcount"] == 11  # - E-004
    assert series[date(2025, 3, 1)]["headcount"] == 11  # E-007 still employed on the 31st
    assert series[date(2025, 4, 1)]["headcount"] == 10
    assert series[date(2025, 6, 1)]["headcount"] == 10


def test_headcount_carries_the_average_denominator(db: Session) -> None:
    """November 2024 is the month that distinguishes the two denominators: 12 at the
    start, 11 at the end. Average headcount is 11.5, and a metric that used
    end-of-period headcount would silently report 11."""
    series = _by_period(retention.headcount_series(db, WINDOW))
    november = series[date(2024, 11, 1)]

    assert november["active_start"] == 12
    assert november["active_end"] == 11
    assert november["avg_headcount"] == pytest.approx(11.5)


def test_headcount_respects_the_department_filter(db: Session) -> None:
    # ENG at 2025-06: D-900, M-901, E-001, E-002, E-003, E-005, E-006 = 7.
    # E-009 transferred to SUP in Oct 2024, E-004 left in Nov 2024.
    eng = _by_period(
        retention.headcount_series(db, MetricFilters(date_from=date(2025, 6, 1), department_id=1))
    )
    assert eng[date(2025, 6, 1)]["headcount"] == 7

    # SUP at 2025-06: M-902, E-008, E-009 = 3. E-007 left in March.
    sup = _by_period(
        retention.headcount_series(db, MetricFilters(date_from=date(2025, 6, 1), department_id=2))
    )
    assert sup[date(2025, 6, 1)]["headcount"] == 3


# --- Attrition rate --------------------------------------------------------


def test_monthly_attrition_uses_average_headcount(db: Session) -> None:
    """November 2024: 1 exit against an average headcount of 11.5.

        annualized = 1 * 12 / 11.5 = 1.0434782...

    Against end-of-period headcount it would be 1 * 12 / 11 = 1.0909, which is the
    error docs/METRICS.md and CLAUDE.md both single out.
    """
    series = _by_period(retention.attrition_rate(db, WINDOW))

    november = series[date(2024, 11, 1)]
    assert november["terminations"] == 1
    assert november["avg_headcount"] == pytest.approx(11.5)
    assert november["annualized_rate"] == pytest.approx(12 / 11.5)


def test_months_without_exits_report_a_zero_rate_not_null(db: Session) -> None:
    """A month with no exits genuinely has a rate of 0. Returning null would render as
    a gap in the trend line and read as missing data."""
    series = _by_period(retention.attrition_rate(db, WINDOW))

    assert series[date(2024, 5, 1)]["terminations"] == 0
    assert series[date(2024, 5, 1)]["annualized_rate"] == pytest.approx(0.0)


def test_window_attrition_totals(db: Session) -> None:
    """Whole window: 2 exits, 195.5 headcount-months.

    annualized = 2 * 12 / 195.5 = 24 / 195.5 = 0.122762...
    """
    total = retention.attrition_total(db, WINDOW)

    assert total["terminations"] == 2
    assert total["headcount_months"] == pytest.approx(HEADCOUNT_MONTHS_WINDOW)
    assert total["annualized_rate"] == pytest.approx(24 / HEADCOUNT_MONTHS_WINDOW)


def test_attrition_splits_voluntary_from_involuntary(db: Session) -> None:
    """E-004 left voluntarily, E-007 involuntarily — one of each across the window."""
    total = retention.attrition_total(db, WINDOW)

    assert total["voluntary_terminations"] == 1
    assert total["involuntary_terminations"] == 1
    assert total["voluntary_share"] == pytest.approx(0.5)


# --- Regretted attrition ---------------------------------------------------


def test_regretted_attrition_counts_only_high_rated_voluntary_exits(db: Session) -> None:
    """E-004: voluntary, last rating 4 -> regretted.
    E-007: involuntary, so excluded from the denominator entirely regardless of rating.

        regretted / voluntary = 1 / 1 = 100%
    """
    result = retention.regretted_attrition(db, WINDOW)

    assert result["voluntary_exits"] == 1
    assert result["regretted_exits"] == 1
    assert result["regretted_share"] == pytest.approx(1.0)


def test_regretted_attrition_is_null_when_there_are_no_voluntary_exits(db: Session) -> None:
    """Q1 2025 holds only E-007's involuntary exit. Zero over zero must be null, not 0 —
    a fabricated zero becomes a fabricated data point on a chart."""
    result = retention.regretted_attrition(
        db, MetricFilters(date_from=date(2025, 1, 1), date_to=date(2025, 3, 31))
    )

    assert result["voluntary_exits"] == 0
    assert result["regretted_share"] is None


# --- Tenure distribution ---------------------------------------------------


def test_tenure_distribution_at_window_end(db: Session) -> None:
    """Tenure at 2025-06-01 for the 10 active employees:

    D-900  2020-01-06 -> 64 months  5y+
    M-901  2021-03-01 -> 51         2-5y
    M-902  2022-06-01 -> 36         2-5y
    E-001  2022-01-10 -> 40         2-5y
    E-002  2023-05-15 -> 24         2-5y
    E-008  2023-02-01 -> 28         2-5y
    E-003  2023-09-01 -> 21         1-2y
    E-009  2023-07-01 -> 23         1-2y
    E-005  2024-03-01 -> 15         1-2y
    E-006  2024-08-01 -> 10         6-12m
    """
    bands = {
        row["tenure_band"]: row["headcount"]
        for row in retention.tenure_distribution(
            db, MetricFilters(date_from=date(2025, 6, 1), date_to=date(2025, 6, 1))
        )
    }

    assert bands["5y+"] == 1
    assert bands["2-5y"] == 5
    assert bands["1-2y"] == 3
    assert bands["6-12m"] == 1
    assert sum(bands.values()) == 10


def test_tenure_distribution_returns_bands_in_order(db: Session) -> None:
    """Alphabetical ordering would put "1-2y" before "6-12m", which reads as nonsense on
    a histogram."""
    rows = retention.tenure_distribution(
        db, MetricFilters(date_from=date(2025, 6, 1), date_to=date(2025, 6, 1))
    )

    order = [row["tenure_band"] for row in rows]
    assert order == [band for band in ("<6m", "6-12m", "1-2y", "2-5y", "5y+") if band in order]


# --- Cohort retention ------------------------------------------------------


def test_twelve_month_retention_by_source(db: Session) -> None:
    """Three employees were hired inside the window and therefore have a channel:

        E-004  AGENCY    2024-02-01, left 2024-11-15  -> 12mo milestone 2025-02-01, gone
        E-005  JOBBOARD  2024-03-01, still active     -> 12mo milestone 2025-03-01, kept
        E-006  REFERRAL  2024-08-01, still active     -> 12mo milestone 2025-08-01

    E-006's milestone falls beyond the window, so REFERRAL has no 12-month datapoint at
    all. That is censoring working: counting them as retained would flatter the channel,
    and counting them as lost would libel it.
    """
    rows = {row["source_id"]: row for row in retention.cohort_retention(db, WINDOW, months=12)}

    assert rows[2]["cohort_size"] == 1  # AGENCY
    assert rows[2]["still_active"] == 0
    assert rows[2]["retention_rate"] == pytest.approx(0.0)

    assert rows[3]["cohort_size"] == 1  # JOBBOARD
    assert rows[3]["still_active"] == 1
    assert rows[3]["retention_rate"] == pytest.approx(1.0)

    assert 1 not in rows, "REFERRAL has not reached 12 months and must be censored out"


def test_cohort_survival_curve_is_monotonically_non_increasing(db: Session) -> None:
    """Survival cannot rise: nobody un-leaves."""
    curve = retention.cohort_survival_curve(db, WINDOW)

    previous = None
    for row in curve:
        if previous is not None:
            assert row["survival_rate"] <= previous + 1e-9
        previous = row["survival_rate"]


# --- Attrition by manager --------------------------------------------------


def test_attrition_by_manager_suppresses_teams_under_eight_reports(db: Session) -> None:
    """docs/METRICS.md sets a floor of 8 reports. No manager in a 12-person org clears
    it — M-901 peaks at 7 — so the default result is empty. Suppressing small teams is
    the point: an attrition rate over 4 reports is noise presented as signal.
    """
    rows = retention.attrition_by_manager(db, WINDOW)

    assert rows == []


def test_attrition_by_manager_with_the_floor_lowered(db: Session) -> None:
    """M-901 in Q4 2024, with the floor dropped so the fixture can exercise the maths:

    Oct  6 reports, 6 at start, 6 at end -> 6.0
    Nov  6 at start, 5 at end (E-004 left the 15th) -> 5.5
    Dec  5, 5 -> 5.0
    headcount_months = 16.5, terminations = 1

    annualized = 1 * 12 / 16.5 = 0.727272...
    """
    rows = retention.attrition_by_manager(
        db,
        MetricFilters(date_from=date(2024, 10, 1), date_to=date(2024, 10, 1)),
        min_reports=1,
    )
    by_manager = {row["manager_id"]: row for row in rows}

    m901 = by_manager["M-901"]
    assert m901["reports"] == 6
    assert m901["terminations"] == 1
    assert m901["headcount_months"] == pytest.approx(16.5)
    assert m901["annualized_rate"] == pytest.approx(12 / 16.5)


def test_attrition_by_manager_returns_one_row_per_manager_per_quarter(db: Session) -> None:
    """The view is grained by (quarter, manager) precisely so a manager cannot be split
    across department or location rows — a per-manager threshold cannot survive that."""
    rows = retention.attrition_by_manager(
        db,
        MetricFilters(date_from=date(2024, 10, 1), date_to=date(2024, 10, 1)),
        min_reports=1,
    )

    keys = [(row["period"], row["manager_id"]) for row in rows]
    assert len(keys) == len(set(keys))


# --- Attrition by manager, trailing window ----------------------------------
#
# The quarterly grain answers "which manager-quarter was worst", and on three years of
# real data the answer is always a small team having one bad quarter: 4 exits from an
# 8.7-person team annualizes to 184%, which is arithmetic, not a management problem. This
# ranking answers the question a reader actually has — "whose team is bleeding *now*" —
# by widening the denominator to a year. It is the same definition `flight_risk` already
# uses for its manager-attrition component, so the two agree by construction.

#: tiny_org's last quarter is 2025-04-01, so a 12-month window covers the four quarters
#: 2024-07, 2024-10, 2025-01 and 2025-04.
_TRAILING_WINDOW_QUARTERS = (
    date(2024, 7, 1),
    date(2024, 10, 1),
    date(2025, 1, 1),
    date(2025, 4, 1),
)


def test_manager_trailing_window_anchors_to_the_data_not_the_clock(db: Session) -> None:
    """tiny_org ends in June 2025. Anchored to `today` the window would be empty and the
    card would render blank — the same trap the overview hit in phase 4."""
    rows = retention.attrition_by_manager_trailing(db, WINDOW, min_reports=1)

    assert rows, "expected managers in the trailing window"
    assert rows[0]["window_to"] == _TRAILING_WINDOW_QUARTERS[-1]
    assert rows[0]["window_from"] == _TRAILING_WINDOW_QUARTERS[0]
    assert {row["months"] for row in rows} == {12}
    assert {row["quarters"] for row in rows} == {len(_TRAILING_WINDOW_QUARTERS)}


def test_manager_trailing_window_returns_one_row_per_manager(db: Session) -> None:
    """The whole point of the aggregation: the quarterly endpoint returns a manager once
    per quarter, this one returns each manager exactly once."""
    ids = [
        row["manager_id"]
        for row in retention.attrition_by_manager_trailing(db, WINDOW, min_reports=1)
    ]

    assert len(ids) == len(set(ids))


def test_manager_trailing_window_aggregates_quarters_before_dividing(db: Session) -> None:
    """M-901 across the four quarters in the window:

        2024-07  headcount_months 20.0, 0 exits
        2024-10  headcount_months 16.5, 1 exit   (E-004 left 15 Nov)
        2025-01  headcount_months 15.0, 0 exits
        2025-04  headcount_months 15.0, 0 exits

        headcount_months = 66.5 over 12 observed months
        avg_reports      = 66.5 / 12 = 5.5416666...
        annualized       = 1 * 12 / 66.5 = 0.1804511...

    Note this is far below the 72.7% that same exit produces at quarterly grain. Both are
    correct; only one of them describes the team.
    """
    rows = retention.attrition_by_manager_trailing(db, WINDOW, min_reports=1)
    by_manager = {row["manager_id"]: row for row in rows}

    m901 = by_manager["M-901"]
    assert m901["terminations"] == 1
    assert m901["voluntary_terminations"] == 1
    assert m901["months_observed"] == 12
    assert m901["headcount_months"] == pytest.approx(66.5)
    assert m901["avg_reports"] == pytest.approx(66.5 / 12)
    assert m901["annualized_rate"] == pytest.approx(12 / 66.5)


def test_manager_trailing_window_ranks_worst_first(db: Session) -> None:
    """M-902: headcount_months 6.0 + 9.0 + 9.0 + 6.0 = 30.0, 1 exit -> 12 / 30 = 0.4,
    which is worse than M-901's 0.1805, so it leads. D-900 has no exits and comes last."""
    rows = retention.attrition_by_manager_trailing(db, WINDOW, min_reports=1)

    assert [row["manager_id"] for row in rows] == ["M-902", "M-901", "D-900"]
    assert rows[0]["annualized_rate"] == pytest.approx(12 / 30.0)
    assert rows[-1]["annualized_rate"] == pytest.approx(0.0)


def test_manager_trailing_window_carries_the_company_rate_for_comparison(db: Session) -> None:
    """A manager's rate means nothing without the baseline beside it. The baseline covers
    every managed employee in the same window with no report floor, so it is not skewed by
    the very filter that selects the managers shown:

        exits            = 1 (M-901) + 1 (M-902) + 0 (D-900) = 2
        headcount_months = 66.5 + 30.0 + 24.0 = 120.5
        company rate     = 2 * 12 / 120.5 = 0.1991701...
    """
    rows = retention.attrition_by_manager_trailing(db, WINDOW, min_reports=1)

    assert rows[0]["company_annualized_rate"] == pytest.approx(24 / 120.5)
    # Identical on every row: it describes the window, not the manager.
    assert len({row["company_annualized_rate"] for row in rows}) == 1


def test_manager_trailing_window_applies_the_floor_to_the_window_average(db: Session) -> None:
    """The floor must be applied *after* aggregating, to the window's average team size.
    Applied per quarter first it would drop the quarters in which a failing team shrank —
    which is exactly when its people were leaving — and flatter the manager."""
    assert retention.attrition_by_manager_trailing(db, WINDOW) == []

    lowered = retention.attrition_by_manager_trailing(db, WINDOW, min_reports=3)

    # M-901 averages 5.54 and clears 3; M-902 averages 2.5 and D-900 averages 2.0.
    assert [row["manager_id"] for row in lowered] == ["M-901"]


# --- Internal mobility -----------------------------------------------------


def test_internal_mobility_rate_for_2024(db: Session) -> None:
    """One promotion (E-003, L2->L3 in July) and one lateral transfer (E-009, ENG->SUP
    in October) — the only two mobility events in the fixture.

        avg headcount 2024 = 132.5 / 12 = 11.041666...
        rate = 2 / 11.041666... = 0.181132...
    """
    result = retention.internal_mobility(
        db, MetricFilters(date_from=date(2024, 1, 1), date_to=date(2024, 12, 31))
    )

    assert result["promotions"] == 1
    assert result["lateral_transfers"] == 1
    assert result["mobility_events"] == 2
    assert result["avg_headcount"] == pytest.approx(HEADCOUNT_MONTHS_2024 / 12)
    assert result["mobility_rate"] == pytest.approx(2 / (HEADCOUNT_MONTHS_2024 / 12))


def test_internal_mobility_excludes_hires_and_terminations(db: Session) -> None:
    """The fixture has 12 hires and 2 terminations in its event log. Counting any of them
    as mobility would multiply the rate several-fold; only promotions and lateral
    transfers qualify."""
    result = retention.internal_mobility(
        db, MetricFilters(date_from=date(2024, 1, 1), date_to=date(2024, 12, 31))
    )

    assert result["mobility_events"] == 2


# --- Filter contract -------------------------------------------------------


def test_unsupported_filter_raises_rather_than_being_ignored(db: Session) -> None:
    """Internal mobility is grained by (year, department) and carries no manager column.
    A manager_id filter must fail loudly: silently returning company-wide numbers for a
    manager-scoped request is worse than an error."""
    from app.metrics.filters import UnsupportedFilterError

    with pytest.raises(UnsupportedFilterError):
        retention.internal_mobility(
            db, MetricFilters(date_from=date(2024, 1, 1), manager_id="M-901")
        )
