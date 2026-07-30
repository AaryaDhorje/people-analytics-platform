"""Guards on the generator's definitions and pure helpers.

No database connection: these run in the edit hook and catch a typo in 0.2s rather
than after a 35-second generation run. They deliberately do not test generated
*data* — that is what `seed/validate.py` does against the real warehouse.
"""

from datetime import date

import pytest

from seed import scenarios as sc
from seed.engagement import WORKLOAD_OFFSET
from seed.people import snapshot_flags
from seed.recruiting import APPS_PER_HIRE, EXTERNAL_COST, NON_HIRE_FINAL_STAGE
from seed.reference import (
    DEPARTMENT_IDS,
    DEPARTMENT_MIX,
    IC_LEVEL_MIX,
    JOB_LEVEL_IDS,
    LOCATION_MIX,
    SOURCE_IDS,
    SOURCE_MIX,
    SURVEY_QUARTERS,
    WINDOW_END,
    WINDOW_START,
)
from seed.scenarios import SCENARIOS, Target, scenario_by_key
from seed.spine import HOLIDAYS, is_workday, workdays_in_month
from seed.util import add_months, monday_of, month_end, months_between, quarter_start

# --- Reference data ---------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "mix"),
    [
        ("DEPARTMENT_MIX", DEPARTMENT_MIX),
        ("LOCATION_MIX", LOCATION_MIX),
        ("IC_LEVEL_MIX", IC_LEVEL_MIX),
        ("SOURCE_MIX", SOURCE_MIX),
    ],
)
def test_mixes_sum_to_one(name: str, mix: dict[str, float]) -> None:
    """A mix that does not sum to 1 silently rescales every volume in the plan."""
    assert sum(mix.values()) == pytest.approx(1.0, abs=1e-9), name


def test_mix_keys_are_real_codes() -> None:
    assert set(DEPARTMENT_MIX) == set(DEPARTMENT_IDS)
    assert set(SOURCE_MIX) == set(SOURCE_IDS)
    assert set(IC_LEVEL_MIX) <= set(JOB_LEVEL_IDS)


def test_hazard_and_offset_tables_cover_every_department() -> None:
    """A missing department silently falls back to a default, which is how a planted
    pattern quietly stops applying to one team."""
    assert set(sc.DEPARTMENT_HAZARD) == set(DEPARTMENT_IDS)
    assert set(WORKLOAD_OFFSET) == set(DEPARTMENT_IDS)


def test_support_has_the_lowest_workload_offset() -> None:
    """Scenario 5 asserts Support holds the company's lowest Workload score, so its
    offset must be strictly the lowest before any noise is added."""
    lowest = min(WORKLOAD_OFFSET, key=lambda code: WORKLOAD_OFFSET[code])
    assert lowest == sc.SUPPORT_DEPARTMENT

    others = [v for k, v in WORKLOAD_OFFSET.items() if k != sc.SUPPORT_DEPARTMENT]
    assert WORKLOAD_OFFSET[sc.SUPPORT_DEPARTMENT] < min(others) - 5.0


def test_recruiting_tables_cover_every_source() -> None:
    assert set(APPS_PER_HIRE) == set(SOURCE_IDS)
    assert set(EXTERNAL_COST) == set(SOURCE_IDS)


def test_agency_costs_more_than_referral() -> None:
    """Scenario 2's cost ratio depends on this ordering holding at the table level."""
    agency_low, _ = EXTERNAL_COST["AGENCY"]
    _, referral_high = EXTERNAL_COST["REFERRAL"]
    assert agency_low > referral_high * 2


def test_non_hire_stage_weights_sum_to_one() -> None:
    assert sum(weight for _, weight in NON_HIRE_FINAL_STAGE) == pytest.approx(1.0)


# --- Scenario definitions ---------------------------------------------------


def test_six_scenarios_with_unique_keys() -> None:
    assert len(SCENARIOS) == 6
    assert len({s.key for s in SCENARIOS}) == 6
    assert [s.number for s in SCENARIOS] == [1, 2, 3, 4, 5, 6]


def test_every_scenario_has_targets() -> None:
    for scenario in SCENARIOS:
        assert scenario.targets, f"{scenario.key} asserts nothing, so it cannot be verified"


def test_target_tolerances_and_comparisons_are_valid() -> None:
    valid = {"within", "at_least", "at_most", "exact"}
    for scenario in SCENARIOS:
        for target in scenario.targets:
            assert target.tolerance >= 0, f"{scenario.key}.{target.key}"
            assert target.comparison in valid, f"{scenario.key}.{target.key}"


def test_scenario_lookup_rejects_unknown_keys() -> None:
    assert scenario_by_key("bad_manager").number == 1
    with pytest.raises(KeyError):
        scenario_by_key("no_such_scenario")


@pytest.mark.parametrize(
    ("comparison", "actual", "expected"),
    [
        ("within", 10.0, True),
        ("within", 12.5, False),
        ("at_least", 8.5, True),
        ("at_least", 7.0, False),
        ("at_most", 11.5, True),
        ("at_most", 13.0, False),
    ],
)
def test_target_comparison_semantics(comparison: str, actual: float, expected: bool) -> None:
    target = Target("k", "label", target=10.0, tolerance=2.0, comparison=comparison)
    assert target.passes(actual) is expected


def test_target_treats_missing_actual_as_failure() -> None:
    """A query returning NULL must not read as a pass."""
    assert Target("k", "l", 1.0, 0.5).passes(None) is False


def test_bad_manager_team_stays_above_the_eight_report_floor() -> None:
    """docs/METRICS.md computes Attrition by Manager only for managers with at least 8
    reports. If the forced exits took the team below that, the headline demo moment
    would be filtered out of its own chart."""
    remaining = sc.BAD_MANAGER_TEAM_SIZE - sc.BAD_MANAGER_FORCED_EXITS
    assert remaining >= 8


def test_regretted_exits_do_not_exceed_total_exits() -> None:
    assert sc.BAD_MANAGER_REGRETTED_EXITS <= sc.BAD_MANAGER_FORCED_EXITS


def test_bad_manager_driver_offset_exceeds_the_asserted_gap() -> None:
    """The applied offset must be larger than the measured gap, because the company
    mean being compared against includes this team."""
    assert sc.BAD_MANAGER_DRIVER_OFFSET > sc.BAD_MANAGER_DRIVER_GAP


def test_bad_manager_exit_quarters_are_the_final_three() -> None:
    for quarter in sc.BAD_MANAGER_EXIT_QUARTERS:
        assert WINDOW_START <= quarter <= WINDOW_END
    assert len(sc.BAD_MANAGER_EXIT_QUARTERS) == 3


def test_surveys_straddle_the_reorg() -> None:
    """The dip needs a pre-reorg baseline to be measured against and a recovery after."""
    before = [q for q in SURVEY_QUARTERS if q < sc.REORG_QUARTER]
    during = [q for q in SURVEY_QUARTERS if q in sc.REORG_AFFECTED_QUARTERS]
    after = [q for q in SURVEY_QUARTERS if q > max(sc.REORG_AFFECTED_QUARTERS)]

    assert len(before) >= 2
    assert len(during) == 2
    assert len(after) >= 1
    assert all(WINDOW_START <= q <= WINDOW_END for q in SURVEY_QUARTERS)


def test_reorg_lag_lands_inside_the_window() -> None:
    lag = add_months(sc.REORG_QUARTER, 3 * sc.REORG_ATTRITION_LAG_QUARTERS)
    assert lag <= WINDOW_END


def test_cliff_cohorts_reach_the_cliff_before_the_window_closes() -> None:
    """A cohort hired last quarter cannot show a 14-18 month cliff. Both target cohorts
    must clear month 18 inside the window or scenario 6 is unmeasurable."""
    _, high = sc.CLIFF_MONTH_RANGE
    for cohort in sc.CLIFF_COHORT_QUARTERS:
        assert cohort >= WINDOW_START
        assert add_months(cohort, high) <= WINDOW_END


def test_volumes_are_internally_consistent() -> None:
    """Total records minus exits must equal the active population at window end."""
    assert sc.INITIAL_HEADCOUNT + sc.HIRES_DURING_WINDOW == sc.TOTAL_EMPLOYEES, (
        "initial + hires must equal total records"
    )
    assert sc.TOTAL_EMPLOYEES - sc.TOTAL_EXITS == sc.TARGET_ACTIVE_AT_END


# --- Pure helpers -----------------------------------------------------------


def test_months_between_requires_the_day_to_be_reached() -> None:
    assert months_between(date(2024, 1, 15), date(2024, 2, 14)) == 0
    assert months_between(date(2024, 1, 15), date(2024, 2, 15)) == 1
    assert months_between(date(2024, 1, 15), date(2025, 1, 15)) == 12
    assert months_between(date(2024, 3, 1), date(2024, 1, 1)) == -2


def test_add_months_clamps_to_the_shorter_month() -> None:
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # leap year
    assert add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert add_months(date(2024, 12, 15), 1) == date(2025, 1, 15)
    assert add_months(date(2024, 1, 15), -1) == date(2023, 12, 15)


def test_month_end_and_quarter_start() -> None:
    assert month_end(date(2024, 2, 10)) == date(2024, 2, 29)
    assert month_end(date(2024, 12, 1)) == date(2024, 12, 31)
    assert quarter_start(date(2025, 8, 14)) == date(2025, 7, 1)
    assert quarter_start(date(2025, 1, 1)) == date(2025, 1, 1)


def test_monday_of_returns_the_week_start() -> None:
    wednesday = date(2026, 7, 29)
    assert monday_of(wednesday) == date(2026, 7, 27)
    assert monday_of(date(2026, 7, 27)) == date(2026, 7, 27)


def test_is_workday_excludes_weekends_and_holidays() -> None:
    assert is_workday(date(2026, 7, 29))  # Wednesday
    assert not is_workday(date(2026, 7, 25))  # Saturday
    assert not is_workday(date(2026, 7, 26))  # Sunday

    holiday = next(iter(sorted(HOLIDAYS)))
    assert not is_workday(holiday)


def test_workdays_in_month_is_plausible() -> None:
    for month in (date(2025, 2, 1), date(2025, 7, 1), date(2025, 12, 1)):
        assert 17 <= workdays_in_month(month) <= 23


# --- Snapshot flags ---------------------------------------------------------
# These four booleans are the foundation of every retention metric. Average headcount
# is (SUM(start) + SUM(end)) / 2, so an error here corrupts every rate downstream.

FIRST = date(2025, 6, 1)
LAST = date(2025, 6, 30)


def test_snapshot_flags_for_a_full_month_employee() -> None:
    flags = snapshot_flags(date(2020, 1, 1), None, FIRST, LAST)
    assert flags == {
        "active_at_month_start": True,
        "active_at_month_end": True,
        "terminated_in_month": False,
        "hired_in_month": False,
    }


def test_snapshot_flags_for_a_mid_month_hire() -> None:
    flags = snapshot_flags(date(2025, 6, 16), None, FIRST, LAST)
    assert flags["active_at_month_start"] is False
    assert flags["active_at_month_end"] is True
    assert flags["hired_in_month"] is True
    assert flags["terminated_in_month"] is False


def test_snapshot_flags_for_a_mid_month_leaver() -> None:
    flags = snapshot_flags(date(2020, 1, 1), date(2025, 6, 16), FIRST, LAST)
    assert flags["active_at_month_start"] is True
    assert flags["active_at_month_end"] is False
    assert flags["terminated_in_month"] is True


def test_snapshot_flags_when_termination_is_the_last_day() -> None:
    """Termination date is inclusive: someone leaving on the 30th was employed on it."""
    flags = snapshot_flags(date(2020, 1, 1), LAST, FIRST, LAST)
    assert flags["active_at_month_end"] is True
    assert flags["terminated_in_month"] is True


def test_snapshot_flags_for_hire_and_leave_in_the_same_month() -> None:
    flags = snapshot_flags(date(2025, 6, 5), date(2025, 6, 20), FIRST, LAST)
    assert flags["active_at_month_start"] is False
    assert flags["active_at_month_end"] is False
    assert flags["hired_in_month"] is True
    assert flags["terminated_in_month"] is True


def test_snapshot_flags_after_termination() -> None:
    flags = snapshot_flags(date(2020, 1, 1), date(2025, 5, 10), FIRST, LAST)
    assert not any(flags.values())
