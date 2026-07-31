"""A 12-employee, 18-month organization where every metric is computable by hand.

Window: **2024-01-01 to 2025-06-30**.

Values are chosen so expectations are exact fractions rather than rounded decimals.
Timesheet hours, for instance, give company utilization of exactly 1768/2080 = 85%,
and the four goals sum to exactly 4.00 capped attainment across 4 goals = 1.00 — which
also proves the 1.5 cap fires, since uncapped they would average 1.125.

The org contains everything the phase-3 prompt requires: two terminations (one
voluntary with a last rating of 4, so it is *regretted*; one involuntary), one
promotion, one lateral transfer, one filled requisition with a complete funnel, one
requisition open for 74 days, two survey waves, and a full quarter of timesheets.

`snapshot_flags` is imported from `seed.people` rather than reimplemented. Those four
booleans are the foundation of every retention metric, and a second definition here
would let the fixture and the warehouse disagree about what "active" means.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.models.enums import (
    AbsenceType,
    ApplicationStage,
    EventType,
    GoalStatus,
    OutputType,
    RequisitionStatus,
    TerminationType,
)
from seed.people import snapshot_flags
from seed.spine import is_workday
from seed.util import iter_months, month_end, month_start, months_between, quarter_start

WINDOW_START = date(2024, 1, 1)
WINDOW_END = date(2025, 6, 30)

# --- Dimensions -------------------------------------------------------------

DEPARTMENTS: list[dict[str, Any]] = [
    {
        "department_id": 1,
        "code": "ENG",
        "name": "Engineering",
        "is_billable": True,
        "carries_revenue": True,
    },
    {
        "department_id": 2,
        "code": "SUP",
        "name": "Support",
        "is_billable": True,
        "carries_revenue": True,
    },
    {
        "department_id": 3,
        "code": "FIN",
        "name": "Finance",
        "is_billable": False,
        "carries_revenue": False,
    },
]
DEPT = {row["code"]: row["department_id"] for row in DEPARTMENTS}

LOCATIONS: list[dict[str, Any]] = [
    {
        "location_id": 1,
        "code": "SFO",
        "name": "San Francisco",
        "city": "San Francisco",
        "country": "United States",
        "region": "Americas",
    },
    {
        "location_id": 2,
        "code": "LON",
        "name": "London",
        "city": "London",
        "country": "United Kingdom",
        "region": "EMEA",
    },
]
LOC = {row["code"]: row["location_id"] for row in LOCATIONS}

JOB_LEVELS: list[dict[str, Any]] = [
    {
        "job_level_id": 1,
        "code": "L1",
        "name": "Associate",
        "rank": 1,
        "comp_band_min": Decimal("52000.00"),
        "comp_band_max": Decimal("74000.00"),
        "is_manager_level": False,
    },
    {
        "job_level_id": 2,
        "code": "L2",
        "name": "Analyst",
        "rank": 2,
        "comp_band_min": Decimal("72000.00"),
        "comp_band_max": Decimal("99000.00"),
        "is_manager_level": False,
    },
    {
        "job_level_id": 3,
        "code": "L3",
        "name": "Senior",
        "rank": 3,
        "comp_band_min": Decimal("98000.00"),
        "comp_band_max": Decimal("136000.00"),
        "is_manager_level": False,
    },
    {
        "job_level_id": 4,
        "code": "L4",
        "name": "Lead",
        "rank": 4,
        "comp_band_min": Decimal("134000.00"),
        "comp_band_max": Decimal("172000.00"),
        "is_manager_level": False,
    },
    {
        "job_level_id": 5,
        "code": "L5",
        "name": "Manager",
        "rank": 5,
        "comp_band_min": Decimal("165000.00"),
        "comp_band_max": Decimal("212000.00"),
        "is_manager_level": True,
    },
    {
        "job_level_id": 6,
        "code": "L6",
        "name": "Director",
        "rank": 6,
        "comp_band_min": Decimal("205000.00"),
        "comp_band_max": Decimal("285000.00"),
        "is_manager_level": True,
    },
]
LEVEL = {row["code"]: row["job_level_id"] for row in JOB_LEVELS}

SOURCES: list[dict[str, Any]] = [
    {"source_id": 1, "code": "REFERRAL", "name": "Employee Referral", "channel_type": "referral"},
    {"source_id": 2, "code": "AGENCY", "name": "External Agency", "channel_type": "agency"},
    {"source_id": 3, "code": "JOBBOARD", "name": "Job Board", "channel_type": "job_board"},
]
SOURCE = {row["code"]: row["source_id"] for row in SOURCES}

SURVEYS: list[dict[str, Any]] = [
    {
        "survey_id": 1,
        "code": "Q3-24",
        "name": "Q3 2024 Pulse",
        "quarter_start": date(2024, 7, 1),
        "opens_on": date(2024, 9, 1),
        "closes_on": date(2024, 9, 30),
    },
    {
        "survey_id": 2,
        "code": "Q1-25",
        "name": "Q1 2025 Pulse",
        "quarter_start": date(2025, 1, 1),
        "opens_on": date(2025, 3, 1),
        "closes_on": date(2025, 3, 31),
    },
]


# --- People -----------------------------------------------------------------


@dataclass
class TinyPerson:
    employee_id: str
    department: str
    location: str
    job_level: str
    manager_id: str | None
    hire_date: date
    comp: Decimal
    source: str | None = None
    termination_date: date | None = None
    termination_type: TerminationType | None = None
    termination_reason: str | None = None
    #: (effective_date, department, job_level, manager_id) overrides applied from that date.
    changes: list[tuple[date, str | None, str | None, str | None]] = field(default_factory=list)

    def state_at(self, day: date) -> tuple[str, str, str | None]:
        department, level, manager = self.department, self.job_level, self.manager_id
        for effective, new_dept, new_level, new_manager in self.changes:
            if effective > day:
                break
            department = new_dept or department
            level = new_level or level
            manager = new_manager or manager
        return department, level, manager

    def active_on(self, day: date) -> bool:
        if day < self.hire_date:
            return False
        return self.termination_date is None or day <= self.termination_date


#: 3 managers (D-900, M-901, M-902) and 9 individual contributors.
#: M-901 holds 7 reports until E-009 transfers away in Oct 2024, then 6.
PEOPLE: list[TinyPerson] = [
    TinyPerson("D-900", "ENG", "SFO", "L6", None, date(2020, 1, 6), Decimal("240000.00")),
    TinyPerson("M-901", "ENG", "SFO", "L5", "D-900", date(2021, 3, 1), Decimal("180000.00")),
    TinyPerson("M-902", "SUP", "LON", "L5", "D-900", date(2022, 6, 1), Decimal("175000.00")),
    TinyPerson("E-001", "ENG", "SFO", "L3", "M-901", date(2022, 1, 10), Decimal("120000.00")),
    TinyPerson("E-002", "ENG", "SFO", "L2", "M-901", date(2023, 5, 15), Decimal("85000.00")),
    # Promoted L2 -> L3 on 2024-07-01. The only promotion in the fixture.
    TinyPerson(
        "E-003",
        "ENG",
        "SFO",
        "L2",
        "M-901",
        date(2023, 9, 1),
        Decimal("88000.00"),
        changes=[(date(2024, 7, 1), None, "L3", None)],
    ),
    # Voluntary exit with a last rating of 4 -> regretted attrition.
    TinyPerson(
        "E-004",
        "ENG",
        "SFO",
        "L1",
        "M-901",
        date(2024, 2, 1),
        Decimal("62000.00"),
        source="AGENCY",
        termination_date=date(2024, 11, 15),
        termination_type=TerminationType.VOLUNTARY,
        termination_reason="Better opportunity",
    ),
    TinyPerson(
        "E-005",
        "ENG",
        "LON",
        "L2",
        "M-901",
        date(2024, 3, 1),
        Decimal("79000.00"),
        source="JOBBOARD",
    ),
    # Hired through requisition R-001, the filled req with the complete funnel.
    TinyPerson(
        "E-006",
        "ENG",
        "SFO",
        "L1",
        "M-901",
        date(2024, 8, 1),
        Decimal("58000.00"),
        source="REFERRAL",
    ),
    # Involuntary exit. Not regretted, regardless of rating.
    TinyPerson(
        "E-007",
        "SUP",
        "LON",
        "L2",
        "M-902",
        date(2022, 11, 1),
        Decimal("81000.00"),
        termination_date=date(2025, 3, 31),
        termination_type=TerminationType.INVOLUNTARY,
        termination_reason="Performance",
    ),
    TinyPerson("E-008", "SUP", "LON", "L1", "M-902", date(2023, 2, 1), Decimal("60000.00")),
    # Lateral transfer ENG -> SUP on 2024-10-01. The only transfer in the fixture.
    TinyPerson(
        "E-009",
        "ENG",
        "SFO",
        "L2",
        "M-901",
        date(2023, 7, 1),
        Decimal("83000.00"),
        changes=[(date(2024, 10, 1), "SUP", None, "M-902")],
    ),
]

BY_ID = {person.employee_id: person for person in PEOPLE}


# --- Requisitions and applications ------------------------------------------

#: R-001 filled: opened 2024-06-20, offer accepted 2024-07-15 -> time to fill 25 days.
#: R-002 open since 2025-04-17, i.e. 74 days at window end -> the only aged req.
REQUISITIONS: list[dict[str, Any]] = [
    {
        "requisition_id": "R-001",
        "department_id": DEPT["ENG"],
        "location_id": LOC["SFO"],
        "job_level_id": LEVEL["L1"],
        "hiring_manager_id": "M-901",
        "status": RequisitionStatus.FILLED,
        "opened_date": date(2024, 6, 20),
        "closed_date": date(2024, 7, 15),
        "target_start_date": date(2024, 8, 1),
        "openings": 1,
        "internal_cost": Decimal("4000.00"),
        "external_cost": Decimal("6000.00"),
    },
    {
        "requisition_id": "R-002",
        "department_id": DEPT["SUP"],
        "location_id": LOC["LON"],
        "job_level_id": LEVEL["L2"],
        "hiring_manager_id": "M-902",
        "status": RequisitionStatus.OPEN,
        "opened_date": date(2025, 4, 17),
        "closed_date": None,
        "target_start_date": date(2025, 7, 1),
        "openings": 1,
        "internal_cost": Decimal("2000.00"),
        "external_cost": Decimal("1000.00"),
    },
]

#: R-001's funnel is 5 -> 4 -> 3 -> 2 -> 1, giving conversions of
#: 80%, 75%, 66.67%, 50% and an offer acceptance rate of 1/2 = 50%.
#: R-002 carries two in-flight applications with no exit dates, so the "still in stage"
#: case is covered.
_APPLICATIONS: list[dict[str, Any]] = [
    {
        "application_id": 1,
        "requisition_id": "R-001",
        "source_id": SOURCE["REFERRAL"],
        "candidate_ref": "C-000001",
        "first_application_date": date(2024, 6, 25),
        "final_stage": ApplicationStage.HIRED,
        "offer_extended_date": date(2024, 7, 10),
        "offer_accepted_date": date(2024, 7, 15),
        "offer_declined_date": None,
        "rejected_date": None,
        "hired_employee_id": "E-006",
        "stages": [
            (ApplicationStage.APPLIED, date(2024, 6, 25), date(2024, 7, 1)),
            (ApplicationStage.SCREEN, date(2024, 7, 1), date(2024, 7, 5)),
            (ApplicationStage.INTERVIEW, date(2024, 7, 5), date(2024, 7, 10)),
            (ApplicationStage.OFFER, date(2024, 7, 10), date(2024, 7, 15)),
            (ApplicationStage.HIRED, date(2024, 7, 15), None),
        ],
    },
    {
        "application_id": 2,
        "requisition_id": "R-001",
        "source_id": SOURCE["AGENCY"],
        "candidate_ref": "C-000002",
        "first_application_date": date(2024, 6, 26),
        "final_stage": ApplicationStage.OFFER,
        "offer_extended_date": date(2024, 7, 11),
        "offer_accepted_date": None,
        "offer_declined_date": date(2024, 7, 14),
        "rejected_date": None,
        "hired_employee_id": None,
        "stages": [
            (ApplicationStage.APPLIED, date(2024, 6, 26), date(2024, 7, 2)),
            (ApplicationStage.SCREEN, date(2024, 7, 2), date(2024, 7, 6)),
            (ApplicationStage.INTERVIEW, date(2024, 7, 6), date(2024, 7, 11)),
            (ApplicationStage.OFFER, date(2024, 7, 11), date(2024, 7, 14)),
        ],
    },
    {
        "application_id": 3,
        "requisition_id": "R-001",
        "source_id": SOURCE["JOBBOARD"],
        "candidate_ref": "C-000003",
        "first_application_date": date(2024, 6, 27),
        "final_stage": ApplicationStage.INTERVIEW,
        "offer_extended_date": None,
        "offer_accepted_date": None,
        "offer_declined_date": None,
        "rejected_date": date(2024, 7, 9),
        "hired_employee_id": None,
        "stages": [
            (ApplicationStage.APPLIED, date(2024, 6, 27), date(2024, 7, 3)),
            (ApplicationStage.SCREEN, date(2024, 7, 3), date(2024, 7, 7)),
            (ApplicationStage.INTERVIEW, date(2024, 7, 7), date(2024, 7, 9)),
        ],
    },
    {
        "application_id": 4,
        "requisition_id": "R-001",
        "source_id": SOURCE["JOBBOARD"],
        "candidate_ref": "C-000004",
        "first_application_date": date(2024, 6, 28),
        "final_stage": ApplicationStage.SCREEN,
        "offer_extended_date": None,
        "offer_accepted_date": None,
        "offer_declined_date": None,
        "rejected_date": date(2024, 7, 6),
        "hired_employee_id": None,
        "stages": [
            (ApplicationStage.APPLIED, date(2024, 6, 28), date(2024, 7, 4)),
            (ApplicationStage.SCREEN, date(2024, 7, 4), date(2024, 7, 6)),
        ],
    },
    {
        "application_id": 5,
        "requisition_id": "R-001",
        "source_id": SOURCE["AGENCY"],
        "candidate_ref": "C-000005",
        "first_application_date": date(2024, 6, 29),
        "final_stage": ApplicationStage.APPLIED,
        "offer_extended_date": None,
        "offer_accepted_date": None,
        "offer_declined_date": None,
        "rejected_date": date(2024, 7, 2),
        "hired_employee_id": None,
        "stages": [(ApplicationStage.APPLIED, date(2024, 6, 29), date(2024, 7, 2))],
    },
    {
        "application_id": 6,
        "requisition_id": "R-002",
        "source_id": SOURCE["JOBBOARD"],
        "candidate_ref": "C-000006",
        "first_application_date": date(2025, 5, 1),
        "final_stage": ApplicationStage.SCREEN,
        "offer_extended_date": None,
        "offer_accepted_date": None,
        "offer_declined_date": None,
        "rejected_date": None,
        "hired_employee_id": None,
        "stages": [
            (ApplicationStage.APPLIED, date(2025, 5, 1), date(2025, 5, 8)),
            (ApplicationStage.SCREEN, date(2025, 5, 8), None),
        ],
    },
    {
        "application_id": 7,
        "requisition_id": "R-002",
        "source_id": SOURCE["REFERRAL"],
        "candidate_ref": "C-000007",
        "first_application_date": date(2025, 5, 2),
        "final_stage": ApplicationStage.APPLIED,
        "offer_extended_date": None,
        "offer_accepted_date": None,
        "offer_declined_date": None,
        "rejected_date": None,
        "hired_employee_id": None,
        "stages": [(ApplicationStage.APPLIED, date(2025, 5, 2), None)],
    },
]


# --- Surveys ----------------------------------------------------------------

#: Eight respondents per wave. Driver values are chosen so every mean is exact:
#: wave 1 manager sums to 32/8 = 4.0 raw = 75.0 on the 0-100 scale, and the five driver
#: means are (75, 56.25, 50, 25, 75) giving an engagement index of exactly 56.25.
#: eNPS is 4 promoters - 2 detractors over 8 = +25.
_WAVE_1_RESPONDENTS = ("D-900", "M-901", "E-001", "E-002", "E-003", "E-004", "E-007", "E-008")
_WAVE_1_ENPS = (10, 10, 9, 9, 8, 7, 6, 4)
_WAVE_1_MANAGER = (5, 5, 4, 4, 4, 3, 3, 4)
_WAVE_1_GROWTH = (4, 4, 3, 3, 3, 3, 2, 4)

#: Wave 2 uses flat values so the drop is unambiguous: manager 3 (50.0) and growth 2
#: (25.0), i.e. a 25-point fall on manager and 31.25 on growth.
_WAVE_2_RESPONDENTS = ("D-900", "M-901", "E-001", "E-002", "E-003", "E-005", "E-007", "E-008")
_WAVE_2_ENPS = (8, 7, 6, 6, 5, 5, 4, 3)


def _survey_responses() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    response_id = 0

    for index, employee_id in enumerate(_WAVE_1_RESPONDENTS):
        response_id += 1
        rows.append(
            {
                "response_id": response_id,
                "survey_id": 1,
                "employee_id": employee_id,
                "submitted_on": date(2024, 9, 10),
                "enps_score": _WAVE_1_ENPS[index],
                "driver_manager": _WAVE_1_MANAGER[index],
                "driver_growth": _WAVE_1_GROWTH[index],
                "driver_recognition": 3,
                "driver_workload": 2,
                "driver_belonging": 4,
                # Two comments only, so theme volume is trivially checkable in phase 6.
                "open_text": "Workload has been heavy this quarter." if index < 2 else None,
            }
        )

    for index, employee_id in enumerate(_WAVE_2_RESPONDENTS):
        response_id += 1
        rows.append(
            {
                "response_id": response_id,
                "survey_id": 2,
                "employee_id": employee_id,
                "submitted_on": date(2025, 3, 10),
                "enps_score": _WAVE_2_ENPS[index],
                "driver_manager": 3,
                "driver_growth": 2,
                "driver_recognition": 3,
                "driver_workload": 2,
                "driver_belonging": 3,
                "open_text": None,
            }
        )
    return rows


# --- Timesheets, goals, revenue, absence, reviews, training -----------------

#: Q1 2025 only: 13 Mondays from 2025-01-06 to 2025-03-31.
#: ENG logs 32 billable + 8 non-billable of 40 available -> 80% utilization, no overtime.
#: SUP logs 36 + 14 of 40 -> 90% utilization, 50 total hours, 10 over 40 = 20% overtime.
#: Company: 1768/2080 = exactly 85% utilization; 260/2340 = 11.11% overtime.
_TIMESHEET_PROFILE: dict[str, tuple[Decimal, Decimal, Decimal, Decimal, OutputType]] = {
    "ENG": (
        Decimal("32.00"),
        Decimal("8.00"),
        Decimal("40.00"),
        Decimal("10.00"),
        OutputType.STORY_POINTS,
    ),
    "SUP": (
        Decimal("36.00"),
        Decimal("14.00"),
        Decimal("40.00"),
        Decimal("40.00"),
        OutputType.TICKETS,
    ),
}
_TIMESHEET_EMPLOYEES = ("E-001", "E-002", "E-007", "E-008")


def _timesheet_mondays() -> list[date]:
    mondays: list[date] = []
    cursor = date(2025, 1, 6)
    while cursor <= date(2025, 3, 31):
        mondays.append(cursor)
        cursor += timedelta(days=7)
    return mondays


#: Capped attainment sums to exactly 0.90 + 1.10 + 1.50 + 0.50 = 4.00 over 4 goals = 1.00.
#: Uncapped it would be 1.125, so this fixture proves the 1.5 cap fires.
_GOALS: list[tuple[str, str, Decimal, Decimal, GoalStatus]] = [
    ("E-001", "ENG", Decimal("100.00"), Decimal("90.00"), GoalStatus.ON_TRACK),
    ("E-002", "ENG", Decimal("100.00"), Decimal("110.00"), GoalStatus.COMPLETE),
    ("E-007", "SUP", Decimal("100.00"), Decimal("200.00"), GoalStatus.COMPLETE),
    ("E-008", "SUP", Decimal("100.00"), Decimal("50.00"), GoalStatus.MISSED),
]

#: Q1 2025 ENG holds 7 FTE and SUP 4, so these give exactly 200,000 and 100,000 per FTE.
_REVENUE: list[tuple[str, Decimal]] = [
    ("ENG", Decimal("1400000.00")),
    ("SUP", Decimal("400000.00")),
]

#: February 2025 has 20 workdays and an average headcount of 11, so available workdays
#: are 220 and absenteeism is 3/220 = 1.3636%.
_ABSENCES: list[tuple[str, date, Decimal, AbsenceType, bool]] = [
    ("E-001", date(2025, 2, 5), Decimal("1.00"), AbsenceType.SICK, True),
    ("E-001", date(2025, 2, 6), Decimal("1.00"), AbsenceType.SICK, True),
    ("E-007", date(2025, 2, 12), Decimal("1.00"), AbsenceType.UNPLANNED, True),
    ("E-002", date(2025, 2, 20), Decimal("1.00"), AbsenceType.PTO, False),
]

#: E-004's rating of 4 is what makes their voluntary exit *regretted*.
#: E-006's rating of 4 at day ~184 is what makes them a quality hire.
#: E-005 is rated 2 deliberately: they survive to day 180 but fail the rating half of
#: Quality of Hire, so the metric has something to discriminate. With every rating at 3
#: or above the test would pass without exercising the rating condition at all.
_REVIEWS: list[tuple[str, date, int]] = [
    ("E-004", date(2024, 8, 1), 4),
    ("E-005", date(2024, 9, 1), 2),
    ("E-007", date(2024, 12, 1), 2),
    ("E-001", date(2025, 1, 15), 5),
    ("E-002", date(2025, 1, 15), 3),
    ("E-006", date(2025, 2, 1), 4),
]

#: Two Claude-extracted themes over the two wave-1 comments (responses 1 and 2, both
#: "Workload has been heavy this quarter."). Phase 6 writes these in production; seeding
#: them here means the Comment Themes metric is testable now rather than deferred, and it
#: pins the shape phase 6 has to produce.
_COMMENT_THEMES: list[tuple[int, str, str, Decimal]] = [
    (1, "Workload", "negative", Decimal("0.900")),
    (2, "Workload", "negative", Decimal("0.850")),
]
COMMENT_THEME_MODEL = "claude-haiku-4-5-20251001"

#: 7.5 hours across 3 assignments, 2 of them completed -> 66.67% completion.
_TRAINING: list[tuple[str, str, str, date, date | None, Decimal]] = [
    (
        "E-001",
        "SEC-101",
        "Security Awareness",
        date(2025, 1, 6),
        date(2025, 1, 20),
        Decimal("2.00"),
    ),
    ("E-002", "SEC-101", "Security Awareness", date(2025, 1, 6), None, Decimal("0.50")),
    (
        "E-007",
        "SUP-115",
        "De-escalation Skills",
        date(2025, 2, 3),
        date(2025, 2, 17),
        Decimal("5.00"),
    ),
]


# --- Row builders -----------------------------------------------------------


def date_rows() -> list[dict[str, Any]]:
    """The spine for the 18-month window, reusing the real `is_workday`."""
    rows: list[dict[str, Any]] = []
    day = WINDOW_START
    index = 0
    while day <= WINDOW_END:
        last = month_end(day)
        rows.append(
            {
                "day": day,
                "year": day.year,
                "quarter": (day.month - 1) // 3 + 1,
                "month": day.month,
                "month_start": month_start(day),
                "month_end": last,
                "quarter_start": quarter_start(day),
                "week_start": day - timedelta(days=day.weekday()),
                "iso_week": day.isocalendar().week,
                "day_of_week": day.isoweekday(),
                "is_workday": is_workday(day),
                "is_month_end": day == last,
                "tenure_day_index": index,
            }
        )
        day += timedelta(days=1)
        index += 1
    return rows


def employee_rows() -> list[dict[str, Any]]:
    """Current state, i.e. as of termination or window end. Managers appear first so the
    self-referencing manager_id FK resolves during insert."""
    rows: list[dict[str, Any]] = []
    for person in PEOPLE:
        as_of = person.termination_date or WINDOW_END
        department, level, manager = person.state_at(as_of)
        rows.append(
            {
                "employee_id": person.employee_id,
                "display_name": f"Person {person.employee_id}",
                "manager_id": manager,
                "hire_date": person.hire_date,
                "termination_date": person.termination_date,
                "termination_type": person.termination_type,
                "termination_reason": person.termination_reason,
                "department_id": DEPT[department],
                "location_id": LOC[person.location],
                "job_level_id": LEVEL[level],
                "source_id": SOURCE[person.source] if person.source else None,
                "comp_amount": person.comp,
                "fte": Decimal("1.000"),
            }
        )
    return rows


def employment_event_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for person in PEOPLE:
        department, level, manager = person.department, person.job_level, person.manager_id
        rows.append(
            {
                "employee_id": person.employee_id,
                "event_date": person.hire_date,
                "event_type": EventType.HIRE,
                "from_department_id": None,
                "to_department_id": DEPT[department],
                "from_job_level_id": None,
                "to_job_level_id": LEVEL[level],
                "from_manager_id": None,
                "to_manager_id": manager,
                "from_comp_amount": None,
                "to_comp_amount": person.comp,
                "termination_type": None,
            }
        )
        for effective, new_dept, new_level, new_manager in person.changes:
            # A department change is a lateral transfer; a level change is a promotion.
            # Internal mobility counts exactly these two event types.
            event_type = EventType.LATERAL_TRANSFER if new_dept is not None else EventType.PROMOTION
            rows.append(
                {
                    "employee_id": person.employee_id,
                    "event_date": effective,
                    "event_type": event_type,
                    "from_department_id": DEPT[department],
                    "to_department_id": DEPT[new_dept or department],
                    "from_job_level_id": LEVEL[level],
                    "to_job_level_id": LEVEL[new_level or level],
                    "from_manager_id": manager,
                    "to_manager_id": new_manager or manager,
                    "from_comp_amount": person.comp,
                    "to_comp_amount": person.comp,
                    "termination_type": None,
                }
            )
            department = new_dept or department
            level = new_level or level
            manager = new_manager or manager

        if person.termination_date is not None:
            rows.append(
                {
                    "employee_id": person.employee_id,
                    "event_date": person.termination_date,
                    "event_type": EventType.TERMINATION,
                    "from_department_id": DEPT[department],
                    "to_department_id": DEPT[department],
                    "from_job_level_id": LEVEL[level],
                    "to_job_level_id": LEVEL[level],
                    "from_manager_id": manager,
                    "to_manager_id": manager,
                    "from_comp_amount": person.comp,
                    "to_comp_amount": person.comp,
                    "termination_type": person.termination_type,
                }
            )
    return rows


def snapshot_rows() -> list[dict[str, Any]]:
    """One row per employee per month they were on the books, using the production
    `snapshot_flags` so "active" means the same thing here as in the warehouse."""
    rows: list[dict[str, Any]] = []
    for first in iter_months(WINDOW_START, WINDOW_END):
        last = month_end(first)
        for person in PEOPLE:
            if person.hire_date > last:
                continue
            if person.termination_date is not None and person.termination_date < first:
                continue
            department, level, manager = person.state_at(last)
            rows.append(
                {
                    "month_start": first,
                    "employee_id": person.employee_id,
                    "department_id": DEPT[department],
                    "location_id": LOC[person.location],
                    "job_level_id": LEVEL[level],
                    "manager_id": manager,
                    "comp_amount": person.comp,
                    "fte": Decimal("1.000"),
                    "tenure_months": max(0, months_between(person.hire_date, first)),
                    **snapshot_flags(person.hire_date, person.termination_date, first, last),
                }
            )
    return rows


def application_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    applications: list[dict[str, Any]] = []
    stage_events: list[dict[str, Any]] = []
    stage_event_id = 0
    for row in _APPLICATIONS:
        stages = row["stages"]
        applications.append({key: value for key, value in row.items() if key != "stages"})
        for stage, entered_on, exited_on in stages:
            stage_event_id += 1
            stage_events.append(
                {
                    "stage_event_id": stage_event_id,
                    "application_id": row["application_id"],
                    "stage": stage,
                    "entered_on": entered_on,
                    "exited_on": exited_on,
                }
            )
    return applications, stage_events


def timesheet_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    timesheet_id = 0
    for monday in _timesheet_mondays():
        for employee_id in _TIMESHEET_EMPLOYEES:
            person = BY_ID[employee_id]
            if not person.active_on(monday):
                continue
            department, _, _ = person.state_at(monday)
            billable, non_billable, available, output, output_type = _TIMESHEET_PROFILE[department]
            timesheet_id += 1
            rows.append(
                {
                    "timesheet_id": timesheet_id,
                    "employee_id": employee_id,
                    "department_id": DEPT[department],
                    "week_start": monday,
                    "billable_hours": billable,
                    "non_billable_hours": non_billable,
                    "available_hours": available,
                    "output_units": output,
                    "output_type": output_type,
                }
            )
    return rows


def goal_rows() -> list[dict[str, Any]]:
    return [
        {
            "goal_id": index + 1,
            "employee_id": employee_id,
            "department_id": DEPT[department],
            "quarter_start": date(2025, 1, 1),
            "title": f"Goal {index + 1}",
            "target_value": target,
            "actual_value": actual,
            "status": status,
        }
        for index, (employee_id, department, target, actual, status) in enumerate(_GOALS)
    ]


def revenue_rows() -> list[dict[str, Any]]:
    return [
        {
            "department_id": DEPT[department],
            "quarter_start": date(2025, 1, 1),
            "revenue_amount": amount,
        }
        for department, amount in _REVENUE
    ]


def absence_rows() -> list[dict[str, Any]]:
    return [
        {
            "absence_id": index + 1,
            "employee_id": employee_id,
            "absence_date": day,
            "days": days,
            "absence_type": absence_type,
            "is_unplanned": is_unplanned,
        }
        for index, (employee_id, day, days, absence_type, is_unplanned) in enumerate(_ABSENCES)
    ]


def review_rows() -> list[dict[str, Any]]:
    return [
        {
            "review_id": index + 1,
            "employee_id": employee_id,
            "reviewer_id": BY_ID[employee_id].manager_id,
            "review_period_start": review_date - timedelta(days=365),
            "review_date": review_date,
            "rating": rating,
        }
        for index, (employee_id, review_date, rating) in enumerate(_REVIEWS)
    ]


def training_rows() -> list[dict[str, Any]]:
    return [
        {
            "training_id": index + 1,
            "employee_id": employee_id,
            "course_code": code,
            "course_name": name,
            "assigned_on": assigned_on,
            "completed_on": completed_on,
            "hours": hours,
        }
        for index, (employee_id, code, name, assigned_on, completed_on, hours) in enumerate(
            _TRAINING
        )
    ]


def comment_theme_rows() -> list[dict[str, Any]]:
    return [
        {
            "comment_theme_id": index + 1,
            "survey_response_id": response_id,
            "theme": theme,
            "sentiment": sentiment,
            "confidence": confidence,
            "model": COMMENT_THEME_MODEL,
        }
        for index, (response_id, theme, sentiment, confidence) in enumerate(_COMMENT_THEMES)
    ]


def all_rows() -> list[tuple[str, list[dict[str, Any]]]]:
    """Every table in foreign-key insert order."""
    applications, stage_events = application_rows()
    return [
        ("dim_date", date_rows()),
        ("dim_department", DEPARTMENTS),
        ("dim_location", LOCATIONS),
        ("dim_job_level", JOB_LEVELS),
        ("dim_source", SOURCES),
        ("dim_survey", SURVEYS),
        ("dim_employee", employee_rows()),
        ("fact_employment_event", employment_event_rows()),
        ("fact_monthly_headcount_snapshot", snapshot_rows()),
        ("dim_requisition", REQUISITIONS),
        ("fact_application", applications),
        ("fact_application_stage_event", stage_events),
        ("fact_survey_response", _survey_responses()),
        ("fact_comment_theme", comment_theme_rows()),
        ("fact_timesheet_week", timesheet_rows()),
        ("fact_goal", goal_rows()),
        ("fact_department_revenue", revenue_rows()),
        ("fact_absence", absence_rows()),
        ("fact_performance_review", review_rows()),
        ("fact_training", training_rows()),
    ]
