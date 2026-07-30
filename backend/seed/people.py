"""Employees, employment events, and the monthly headcount snapshot.

The most intricate module in the generator, because three of the six scenarios are
attrition stories and all of them land here.

Termination assignment runs in four stages, forced before sampled:

1. **M-114's six exits** — exact, across the last three quarters, four of them
   voluntary with a forced rating of 4+.
2. **Channel retention** — exact counts of agency and referral hires exiting inside
   12 months, so 62% vs 88% is a fact rather than a hope.
3. **Tenure cliff** — exits placed in months 14-18 for the two target cohorts.
4. **Everyone else** — weighted sampling without replacement to reach exactly 650
   exits, respecting relative hazard by department, tenure, and channel.

Sampling *without replacement to an exact total* is what makes the volumes in
BUILD_PLAN §3 hold precisely while relative patterns stay realistic. A naive
per-month coin flip would give a different headcount every time the hazards were
tuned.

Two deliberate simplifications, both stated so they are not mistaken for bugs:
managers never terminate (so `manager_id` always points at an active employee and
span of control stays stable), and M-114's team is excluded from the sampling pool
so its exit count is exactly six.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from app.models.enums import EventType, TerminationType
from seed import scenarios as sc
from seed.reference import (
    DEPARTMENT_IDS,
    DEPARTMENT_MIX,
    FIRST_NAMES,
    IC_LEVEL_MIX,
    JOB_LEVEL_BY_CODE,
    JOB_LEVEL_IDS,
    LAST_NAMES,
    LOCATION_IDS,
    LOCATION_MIX,
    SOURCE_IDS,
    SOURCE_MIX,
    WINDOW_END,
    WINDOW_START,
)
from seed.util import add_months, dec, iter_months, month_end, month_start, months_between

CEO_ID = "M-101"
DEPARTMENT_HEAD_IDS = tuple(f"M-{102 + i}" for i in range(8))
FIRST_LINE_MANAGER_NUMBER = 110

VOLUNTARY_REASONS = (
    "Better opportunity",
    "Compensation",
    "Manager relationship",
    "Career growth",
    "Relocation",
    "Work-life balance",
)
INVOLUNTARY_REASONS = ("Performance", "Role eliminated", "Restructure")


@dataclass
class Change:
    """One transition on an employee's timeline."""

    day: date
    event_type: EventType
    to_department: str | None = None
    to_job_level: str | None = None
    to_manager: str | None = None
    to_comp: Decimal | None = None


@dataclass
class Person:
    employee_id: str
    display_name: str
    department: str
    location: str
    job_level: str
    manager_id: str | None
    source: str | None
    hire_date: date
    comp_amount: Decimal
    fte: Decimal
    is_manager: bool = False
    termination_date: date | None = None
    termination_type: TerminationType | None = None
    termination_reason: str | None = None
    #: Forces the final performance review's rating. Used for M-114's regretted exits.
    force_last_rating: int | None = None
    changes: list[Change] = field(default_factory=list)

    def state_at(self, day: date) -> tuple[str, str, str | None, Decimal]:
        """(department, job_level, manager_id, comp) as of `day`."""
        department, level, manager, comp = (
            self.department,
            self.job_level,
            self.manager_id,
            self.comp_amount,
        )
        for change in self.changes:
            if change.day > day:
                break
            department = change.to_department or department
            level = change.to_job_level or level
            manager = change.to_manager or manager
            comp = change.to_comp or comp
        return department, level, manager, comp

    def active_on(self, day: date) -> bool:
        if day < self.hire_date:
            return False
        return self.termination_date is None or day <= self.termination_date


def _weighted_codes(rng: np.random.Generator, mix: dict[str, float], count: int) -> list[str]:
    """Draw `count` codes according to `mix`, then shuffle so order carries no signal."""
    codes = list(mix)
    weights = np.array([mix[code] for code in codes], dtype=float)
    weights = weights / weights.sum()
    drawn = rng.choice(codes, size=count, p=weights).tolist()
    return drawn


def _comp_for(rng: np.random.Generator, level_code: str) -> Decimal:
    """Place the employee inside their band. A spread is required for the flight-risk
    component 'comp percentile vs band' to mean anything."""
    level = JOB_LEVEL_BY_CODE[level_code]
    low = float(level["comp_band_min"])  # type: ignore[arg-type]
    high = float(level["comp_band_max"])  # type: ignore[arg-type]
    percentile = float(rng.beta(2.2, 2.4))
    return dec(low + (high - low) * percentile)


def _name(rng: np.random.Generator) -> str:
    return (
        f"{FIRST_NAMES[rng.integers(len(FIRST_NAMES))]} {LAST_NAMES[rng.integers(len(LAST_NAMES))]}"
    )


def _fte(rng: np.random.Generator) -> Decimal:
    roll = float(rng.random())
    if roll < 0.03:
        return dec(0.600, 3)
    if roll < 0.06:
        return dec(0.800, 3)
    return dec(1.000, 3)


# --- Org construction -------------------------------------------------------


def build_population(rng: np.random.Generator, scale: float) -> list[Person]:
    """Build the org chart, hire dates, levels, comp, and channel of hire."""
    total = max(220, round(sc.TOTAL_EMPLOYEES * scale))
    n_line_managers = max(10, round(141 * scale))
    n_ic = total - 1 - len(DEPARTMENT_HEAD_IDS) - n_line_managers
    n_hires_during = max(40, round(sc.HIRES_DURING_WINDOW * scale))

    people: list[Person] = []

    # CEO, hired well before the window.
    people.append(
        Person(
            employee_id=CEO_ID,
            display_name=_name(rng),
            department="PPL",
            location="SFO",
            job_level="L6",
            manager_id=None,
            source=None,
            hire_date=date(2017, 3, 6),
            comp_amount=_comp_for(rng, "L6"),
            fte=dec(1.000, 3),
            is_manager=True,
        )
    )

    department_codes = list(DEPARTMENT_MIX)
    for index, head_id in enumerate(DEPARTMENT_HEAD_IDS):
        people.append(
            Person(
                employee_id=head_id,
                display_name=_name(rng),
                department=department_codes[index],
                location=_weighted_codes(rng, LOCATION_MIX, 1)[0],
                job_level="L6",
                manager_id=CEO_ID,
                source=None,
                hire_date=WINDOW_START - timedelta(days=int(rng.integers(700, 2200))),
                comp_amount=_comp_for(rng, "L6"),
                fte=dec(1.000, 3),
                is_manager=True,
            )
        )

    # Line managers. M-114 is pinned to Engineering because the bad-manager scenario
    # names it and the Loom reads the id aloud.
    manager_departments = _weighted_codes(rng, DEPARTMENT_MIX, n_line_managers)
    line_managers: list[Person] = []
    for offset in range(n_line_managers):
        manager_id = f"M-{FIRST_LINE_MANAGER_NUMBER + offset}"
        department = manager_departments[offset]
        if manager_id == sc.BAD_MANAGER_ID:
            department = sc.BAD_MANAGER_DEPARTMENT
        head = next(
            p for p in people if p.is_manager and p.department == department and p.job_level == "L6"
        )
        manager = Person(
            employee_id=manager_id,
            display_name=_name(rng),
            department=department,
            location=_weighted_codes(rng, LOCATION_MIX, 1)[0],
            job_level="L5",
            manager_id=head.employee_id,
            source=None,
            hire_date=WINDOW_START - timedelta(days=int(rng.integers(200, 1900))),
            comp_amount=_comp_for(rng, "L5"),
            fte=dec(1.000, 3),
            is_manager=True,
        )
        line_managers.append(manager)
        people.append(manager)

    # M-114 is deliberately absent from the round-robin pool: their team is set to an
    # exact size by _assign_bad_manager_team below. Leaving them in meant they received
    # a round-robin share *on top of* the planted team — about 30 reports where only 14
    # carried the planted signal, which diluted the manager-driver gap from 28 points to
    # 22 and pushed the attrition ratio down to parity with the company.
    managers_by_department: dict[str, list[Person]] = {}
    for manager in line_managers:
        if manager.employee_id == sc.BAD_MANAGER_ID:
            continue
        managers_by_department.setdefault(manager.department, []).append(manager)

    # Individual contributors.
    ic_departments = _weighted_codes(rng, DEPARTMENT_MIX, n_ic)
    ic_levels = _weighted_codes(rng, IC_LEVEL_MIX, n_ic)
    ic_locations = _weighted_codes(rng, LOCATION_MIX, n_ic)

    # Hire dates: the first (n_ic - n_hires_during) are tenured, hired before the
    # window opens; the rest arrive during it, spread across the 36 months with a
    # mild upward trend so headcount grows rather than staying flat.
    n_tenured = max(0, n_ic - n_hires_during)
    hire_dates: list[date] = []
    for _ in range(n_tenured):
        hire_dates.append(WINDOW_START - timedelta(days=int(rng.integers(30, 2600))))

    window_months = iter_months(WINDOW_START, WINDOW_END)
    trend = np.linspace(0.75, 1.25, len(window_months))
    trend = trend / trend.sum()
    month_choices = rng.choice(len(window_months), size=n_hires_during, p=trend)
    for month_index in month_choices:
        first = window_months[int(month_index)]
        last = month_end(first)
        hire_dates.append(first + timedelta(days=int(rng.integers(0, (last - first).days + 1))))

    ic_sources = _weighted_codes(rng, SOURCE_MIX, n_ic)

    for index in range(n_ic):
        department = ic_departments[index]
        level = ic_levels[index]
        pool = managers_by_department.get(department) or line_managers
        manager = pool[index % len(pool)]
        hire_date = hire_dates[index]
        people.append(
            Person(
                employee_id=f"E-{index + 1:04d}",
                display_name=_name(rng),
                department=department,
                location=ic_locations[index],
                job_level=level,
                manager_id=manager.employee_id,
                # Employees who predate the window have no recorded channel.
                source=ic_sources[index] if hire_date >= WINDOW_START else None,
                hire_date=hire_date,
                comp_amount=_comp_for(rng, level),
                fte=_fte(rng),
            )
        )

    _assign_bad_manager_team(people)
    for person in people:
        person.changes.append(
            Change(
                day=person.hire_date,
                event_type=EventType.HIRE,
                to_department=person.department,
                to_job_level=person.job_level,
                to_manager=person.manager_id,
                to_comp=person.comp_amount,
            )
        )
    return people


def _assign_bad_manager_team(people: list[Person]) -> None:
    """Give M-114 exactly BAD_MANAGER_TEAM_SIZE reports, all tenured enough to have
    a 3-quarter exit history."""
    cutoff = add_months(WINDOW_END, -18)
    candidates = [
        person
        for person in people
        if not person.is_manager
        and person.department == sc.BAD_MANAGER_DEPARTMENT
        and person.hire_date <= cutoff
    ]
    for person in candidates[: sc.BAD_MANAGER_TEAM_SIZE]:
        person.manager_id = sc.BAD_MANAGER_ID


def bad_manager_team(people: list[Person]) -> list[Person]:
    return [p for p in people if p.manager_id == sc.BAD_MANAGER_ID and not p.is_manager]


# --- Hazard model -----------------------------------------------------------

_TENURE_CURVE = ((6, 0.80), (12, 1.10), (24, 1.30), (48, 1.00))
_SOURCE_HAZARD = {
    "REFERRAL": 0.75,
    "AGENCY": 1.40,
    "JOBBOARD": 1.10,
    "INBOUND": 1.00,
    "CAMPUS": 1.15,
    "INTERNAL": 0.70,
}


def _tenure_hazard(tenure_months: int) -> float:
    for threshold, value in _TENURE_CURVE:
        if tenure_months < threshold:
            return value
    return 0.60


def _reorg_hazard(month_first: date) -> float:
    """Attrition rises a fixed number of quarters after the reorg."""
    lag_start = add_months(sc.REORG_QUARTER, 3 * sc.REORG_ATTRITION_LAG_QUARTERS)
    lag_end = add_months(lag_start, 3)
    return sc.REORG_ATTRITION_HAZARD_BUMP if lag_start <= month_first < lag_end else 1.0


def _month_hazard(person: Person, month_first: date) -> float:
    tenure = months_between(person.hire_date, month_first)
    weight = sc.DEPARTMENT_HAZARD.get(person.department, 1.0)
    weight *= _tenure_hazard(tenure)
    weight *= _SOURCE_HAZARD.get(person.source or "", 0.85)
    weight *= _reorg_hazard(month_first)
    if person.hire_date >= WINDOW_START:
        cohort = date(person.hire_date.year, 3 * ((person.hire_date.month - 1) // 3) + 1, 1)
        low, high = sc.CLIFF_MONTH_RANGE
        if cohort in sc.CLIFF_COHORT_QUARTERS and low <= tenure <= high:
            weight *= sc.CLIFF_HAZARD_MULTIPLIER
    return weight


def _eligible_months(person: Person) -> list[date]:
    """Months in which this person could plausibly exit.

    A minimum of three months' tenure keeps the data free of same-quarter
    hire-and-leave noise that would distort new-hire retention.
    """
    earliest = max(month_start(WINDOW_START), month_start(add_months(person.hire_date, 3)))
    return [m for m in iter_months(earliest, WINDOW_END) if m >= earliest]


#: Channels whose 12-month retention is an asserted scenario target.
_RETENTION_ASSERTED_SOURCES = ("AGENCY", "REFERRAL")


def _sampling_months(person: Person, horizon_cutoff: date) -> list[date]:
    """Months stage 4 may draw from.

    Stage 2 already forced the exact number of agency and referral hires that exit
    inside 12 months. If stage 4 could add more exits inside that same horizon, the
    62% / 88% retention figures would drift below target — which is precisely what
    happened on the first run: agency retention came out at 33%. So for measured
    cohorts, sampling is confined to months after the retention horizon closes.
    """
    months = _eligible_months(person)
    if (
        person.source in _RETENTION_ASSERTED_SOURCES
        and person.hire_date >= WINDOW_START
        and person.hire_date <= horizon_cutoff
    ):
        guard = add_months(person.hire_date, sc.RETENTION_HORIZON_MONTHS)
        months = [m for m in months if m > guard]
    return months


def _terminate(
    person: Person,
    rng: np.random.Generator,
    day: date,
    *,
    force_voluntary: bool = False,
    force_rating: int | None = None,
) -> None:
    voluntary = force_voluntary or float(rng.random()) < sc.VOLUNTARY_SHARE
    person.termination_date = day
    person.termination_type = (
        TerminationType.VOLUNTARY if voluntary else TerminationType.INVOLUNTARY
    )
    reasons = VOLUNTARY_REASONS if voluntary else INVOLUNTARY_REASONS
    person.termination_reason = reasons[int(rng.integers(len(reasons)))]
    person.force_last_rating = force_rating
    person.changes.append(Change(day=day, event_type=EventType.TERMINATION))


def _random_day_in_quarter(rng: np.random.Generator, quarter: date) -> date:
    last = month_end(add_months(quarter, 2))
    return quarter + timedelta(days=int(rng.integers(0, (last - quarter).days + 1)))


def assign_terminations(people: list[Person], rng: np.random.Generator, scale: float) -> None:
    """Forced scenario exits first, then weighted sampling to the exact total."""
    target_total = max(60, round(sc.TOTAL_EXITS * scale))
    terminated: set[str] = set()

    # --- Stage 1: M-114's six exits, four of them regretted -----------------
    team = bad_manager_team(people)
    quarters = sc.BAD_MANAGER_EXIT_QUARTERS
    for index in range(min(sc.BAD_MANAGER_FORCED_EXITS, len(team))):
        person = team[index]
        quarter = quarters[index % len(quarters)]
        regretted = index < sc.BAD_MANAGER_REGRETTED_EXITS
        _terminate(
            person,
            rng,
            _random_day_in_quarter(rng, quarter),
            force_voluntary=regretted,
            force_rating=4 + (index % 2) if regretted else None,
        )
        terminated.add(person.employee_id)

    # --- Stage 2: channel retention at 12 months ----------------------------
    horizon_cutoff = add_months(WINDOW_END, -sc.RETENTION_HORIZON_MONTHS)
    for source_code, retention in (
        ("AGENCY", sc.AGENCY_12M_RETENTION),
        ("REFERRAL", sc.REFERRAL_12M_RETENTION),
    ):
        cohort = [
            p
            for p in people
            if p.source == source_code
            and p.hire_date >= WINDOW_START
            and p.hire_date <= horizon_cutoff
            and p.employee_id not in terminated
        ]
        n_exits = round(len(cohort) * (1.0 - retention))
        for person in cohort[:n_exits]:
            # Inside 12 months of hire, and never in the first three.
            offset_months = int(rng.integers(3, sc.RETENTION_HORIZON_MONTHS))
            exit_month = add_months(person.hire_date, offset_months)
            day = min(exit_month, WINDOW_END)
            _terminate(person, rng, day)
            terminated.add(person.employee_id)

    # --- Stage 3: the tenure cliff -----------------------------------------
    low, high = sc.CLIFF_MONTH_RANGE
    cliff_pool = [
        p
        for p in people
        if not p.is_manager
        and p.hire_date >= WINDOW_START
        and p.employee_id not in terminated
        and date(p.hire_date.year, 3 * ((p.hire_date.month - 1) // 3) + 1, 1)
        in sc.CLIFF_COHORT_QUARTERS
        and add_months(p.hire_date, high) <= WINDOW_END
    ]
    n_cliff = max(8, round(len(cliff_pool) * 0.22))
    for person in cliff_pool[:n_cliff]:
        offset = int(rng.integers(low, high + 1))
        _terminate(person, rng, min(add_months(person.hire_date, offset), WINDOW_END))
        terminated.add(person.employee_id)

    # --- Stage 4: sample the remainder to the exact total -------------------
    # Managers never terminate, and M-114's team is excluded so its exit count stays
    # exactly six — both stated in the module docstring.
    excluded = {p.employee_id for p in team}
    pool = [
        p
        for p in people
        if not p.is_manager and p.employee_id not in terminated and p.employee_id not in excluded
    ]
    month_options: list[list[date]] = []
    cumulative: list[float] = []
    for person in pool:
        months = _sampling_months(person, horizon_cutoff)
        month_options.append(months)
        cumulative.append(sum(_month_hazard(person, m) for m in months))

    remaining = target_total - len(terminated)
    if remaining > 0 and pool:
        weights = np.array(cumulative, dtype=float)
        if weights.sum() <= 0:
            weights = np.ones(len(pool), dtype=float)
        weights = weights / weights.sum()
        take = min(remaining, int((weights > 0).sum()))
        chosen = rng.choice(len(pool), size=take, replace=False, p=weights)
        for position in chosen:
            person = pool[int(position)]
            months = month_options[int(position)]
            if not months:
                continue
            month_weights = np.array([_month_hazard(person, m) for m in months], dtype=float)
            month_weights = month_weights / month_weights.sum()
            month_first = months[int(rng.choice(len(months), p=month_weights))]
            last = min(month_end(month_first), WINDOW_END)
            day = month_first + timedelta(days=int(rng.integers(0, (last - month_first).days + 1)))
            if day < person.hire_date:
                day = person.hire_date + timedelta(days=30)
            _terminate(person, rng, min(day, WINDOW_END))
            terminated.add(person.employee_id)


# --- Mobility ---------------------------------------------------------------


def assign_mobility(people: list[Person], rng: np.random.Generator) -> None:
    """Promotions and lateral transfers, including the reorg wave.

    Internal mobility rate counts exactly these two event types, so they are the
    only non-hire, non-termination events generated.
    """
    managers_by_department: dict[str, list[str]] = {}
    for person in people:
        if person.is_manager and person.job_level == "L5":
            managers_by_department.setdefault(person.department, []).append(person.employee_id)

    protected = {p.employee_id for p in bad_manager_team(people)}
    window_months = iter_months(WINDOW_START, WINDOW_END)

    for person in people:
        if person.is_manager:
            continue
        level_rank = int(JOB_LEVEL_BY_CODE[person.job_level]["rank"])  # type: ignore[arg-type]

        # Promotions: ~8% per year, capped at L4 for individual contributors.
        for month_first in window_months:
            if not person.active_on(month_first) or level_rank >= 4:
                continue
            if float(rng.random()) < 0.08 / 12:
                level_rank += 1
                new_level = f"L{level_rank}"
                person.changes.append(
                    Change(
                        day=month_first + timedelta(days=int(rng.integers(0, 27))),
                        event_type=EventType.PROMOTION,
                        to_job_level=new_level,
                        to_comp=_comp_for(rng, new_level),
                    )
                )

        # The reorg wave: a fixed share of active staff change department and manager
        # in the reorg month. M-114's team is held stable so that story stays clean.
        if (
            person.employee_id not in protected
            and person.active_on(sc.REORG_QUARTER)
            and float(rng.random()) < sc.REORG_TRANSFER_SHARE
        ):
            options = [d for d in managers_by_department if d != person.department]
            if options:
                new_department = options[int(rng.integers(len(options)))]
                # M-114 is never a transfer *destination*. On the first run the reorg
                # moved outsiders onto that team, which made its exit count 7 instead
                # of the forced 6 and diluted the manager-driver gap from 28 to 23.
                new_manager_pool = [
                    m for m in managers_by_department[new_department] if m != sc.BAD_MANAGER_ID
                ] or managers_by_department[new_department]
                person.changes.append(
                    Change(
                        day=sc.REORG_QUARTER + timedelta(days=int(rng.integers(0, 28))),
                        event_type=EventType.LATERAL_TRANSFER,
                        to_department=new_department,
                        to_manager=new_manager_pool[int(rng.integers(len(new_manager_pool)))],
                    )
                )

    for person in people:
        person.changes.sort(key=lambda change: change.day)


# --- Row builders -----------------------------------------------------------


def employee_rows(people: list[Person]) -> list[dict[str, object]]:
    """dim_employee holds CURRENT state — i.e. state as of termination or window end."""
    rows: list[dict[str, object]] = []
    for person in people:
        as_of = person.termination_date or WINDOW_END
        department, level, manager, comp = person.state_at(as_of)
        rows.append(
            {
                "employee_id": person.employee_id,
                "display_name": person.display_name,
                "manager_id": manager,
                "hire_date": person.hire_date,
                "termination_date": person.termination_date,
                "termination_type": person.termination_type,
                "termination_reason": person.termination_reason,
                "department_id": DEPARTMENT_IDS[department],
                "location_id": LOCATION_IDS[person.location],
                "job_level_id": JOB_LEVEL_IDS[level],
                "source_id": SOURCE_IDS[person.source] if person.source else None,
                "comp_amount": comp,
                "fte": person.fte,
            }
        )
    return rows


def employment_event_rows(people: list[Person]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for person in people:
        department, level, manager, comp = (
            person.department,
            person.job_level,
            person.manager_id,
            person.comp_amount,
        )
        for change in person.changes:
            row: dict[str, object] = {
                "employee_id": person.employee_id,
                "event_date": change.day,
                "event_type": change.event_type,
                "from_department_id": DEPARTMENT_IDS[department],
                "to_department_id": DEPARTMENT_IDS[change.to_department or department],
                "from_job_level_id": JOB_LEVEL_IDS[level],
                "to_job_level_id": JOB_LEVEL_IDS[change.to_job_level or level],
                "from_manager_id": manager,
                "to_manager_id": change.to_manager or manager,
                "from_comp_amount": comp,
                "to_comp_amount": change.to_comp or comp,
                "termination_type": (
                    person.termination_type if change.event_type == EventType.TERMINATION else None
                ),
            }
            if change.event_type == EventType.HIRE:
                # A hire has no prior state; leaving from_* populated would imply one.
                row.update(
                    from_department_id=None,
                    from_job_level_id=None,
                    from_manager_id=None,
                    from_comp_amount=None,
                )
            rows.append(row)
            department = change.to_department or department
            level = change.to_job_level or level
            manager = change.to_manager or manager
            comp = change.to_comp or comp
    return rows


def snapshot_flags(
    hire_date: date, termination_date: date | None, first: date, last: date
) -> dict[str, bool]:
    """The four activity flags for one employee-month.

    Derived in exactly one place. `active_at_month_start` and `active_at_month_end`
    are what make average headcount — (SUM(start) + SUM(end)) / 2 — exact, and
    getting these wrong would corrupt every rate metric downstream.
    """
    end_bound = termination_date

    def employed_on(day: date) -> bool:
        if day < hire_date:
            return False
        return end_bound is None or day <= end_bound

    return {
        "active_at_month_start": employed_on(first),
        "active_at_month_end": employed_on(last),
        "terminated_in_month": end_bound is not None and first <= end_bound <= last,
        "hired_in_month": first <= hire_date <= last,
    }


def snapshot_rows(people: list[Person]) -> list[dict[str, object]]:
    """One row per employee per month in which they were on the books at all."""
    rows: list[dict[str, object]] = []
    all_months = iter_months(WINDOW_START, WINDOW_END)
    for person in people:
        for first in all_months:
            last = month_end(first)
            if person.hire_date > last:
                continue
            if person.termination_date is not None and person.termination_date < first:
                continue
            department, level, manager, comp = person.state_at(last)
            flags = snapshot_flags(person.hire_date, person.termination_date, first, last)
            rows.append(
                {
                    "month_start": first,
                    "employee_id": person.employee_id,
                    "department_id": DEPARTMENT_IDS[department],
                    "location_id": LOCATION_IDS[person.location],
                    "job_level_id": JOB_LEVEL_IDS[level],
                    "manager_id": manager,
                    "comp_amount": comp,
                    "fte": person.fte,
                    "tenure_months": max(0, months_between(person.hire_date, first)),
                    **flags,
                }
            )
    return rows
