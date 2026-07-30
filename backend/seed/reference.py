"""Fixed reference data: the window, the dimension rows, and name/text pools.

Pure data, no logic and no randomness. Everything the generator treats as "the
shape of the company" lives here so it can be changed without touching
generation code.
"""

from datetime import date

from app.models.enums import ChannelType, OutputType
from seed.util import add_months, iter_quarters, month_end

# --- The 36-month window ----------------------------------------------------
# Ends at the current month so the dashboard's "latest" period is now, not a date
# in the past that makes the demo look stale.
WINDOW_START = date(2023, 8, 1)
WINDOW_END = date(2026, 7, 31)

#: Calendar quarters covered by the window (12 of them).
WINDOW_QUARTERS: list[date] = iter_quarters(WINDOW_START, WINDOW_END)


# --- Departments ------------------------------------------------------------
# `is_billable` departments file timesheets, so utilization and overtime apply to
# them only. `carries_revenue` gates revenue per FTE.
DEPARTMENTS: list[dict[str, object]] = [
    {"code": "ENG", "name": "Engineering", "is_billable": True, "carries_revenue": True},
    {"code": "SAL", "name": "Sales", "is_billable": False, "carries_revenue": True},
    {"code": "SUP", "name": "Support", "is_billable": True, "carries_revenue": True},
    {"code": "OPS", "name": "Operations", "is_billable": True, "carries_revenue": True},
    {"code": "PRD", "name": "Product", "is_billable": False, "carries_revenue": True},
    {"code": "MKT", "name": "Marketing", "is_billable": False, "carries_revenue": False},
    {"code": "FIN", "name": "Finance", "is_billable": False, "carries_revenue": False},
    {"code": "PPL", "name": "People", "is_billable": False, "carries_revenue": False},
]

#: Share of headcount per department. Sums to 1.0 — asserted in tests.
DEPARTMENT_MIX: dict[str, float] = {
    "ENG": 0.34,
    "SAL": 0.16,
    "SUP": 0.14,
    "OPS": 0.10,
    "PRD": 0.08,
    "MKT": 0.07,
    "FIN": 0.06,
    "PPL": 0.05,
}

#: What each billable department's Output per Head is counted in.
DEPARTMENT_OUTPUT: dict[str, OutputType] = {
    "ENG": OutputType.STORY_POINTS,
    "SUP": OutputType.TICKETS,
    "OPS": OutputType.TICKETS,
}


# --- Locations --------------------------------------------------------------
LOCATIONS: list[dict[str, str]] = [
    {
        "code": "SFO",
        "name": "San Francisco",
        "city": "San Francisco",
        "country": "United States",
        "region": "Americas",
    },
    {
        "code": "AUS",
        "name": "Austin",
        "city": "Austin",
        "country": "United States",
        "region": "Americas",
    },
    {
        "code": "LON",
        "name": "London",
        "city": "London",
        "country": "United Kingdom",
        "region": "EMEA",
    },
    {
        "code": "BLR",
        "name": "Bengaluru",
        "city": "Bengaluru",
        "country": "India",
        "region": "APAC",
    },
]

LOCATION_MIX: dict[str, float] = {"SFO": 0.30, "AUS": 0.26, "LON": 0.22, "BLR": 0.22}


# --- Job levels -------------------------------------------------------------
# Comp bands feed the flight-risk component "comp percentile vs band", so the
# spread has to be wide enough for a percentile to be meaningful.
JOB_LEVELS: list[dict[str, object]] = [
    {
        "code": "L1",
        "name": "Associate",
        "rank": 1,
        "comp_band_min": 52_000,
        "comp_band_max": 74_000,
        "is_manager_level": False,
    },
    {
        "code": "L2",
        "name": "Analyst",
        "rank": 2,
        "comp_band_min": 72_000,
        "comp_band_max": 99_000,
        "is_manager_level": False,
    },
    {
        "code": "L3",
        "name": "Senior",
        "rank": 3,
        "comp_band_min": 98_000,
        "comp_band_max": 136_000,
        "is_manager_level": False,
    },
    {
        "code": "L4",
        "name": "Lead",
        "rank": 4,
        "comp_band_min": 134_000,
        "comp_band_max": 172_000,
        "is_manager_level": False,
    },
    {
        "code": "L5",
        "name": "Manager",
        "rank": 5,
        "comp_band_min": 165_000,
        "comp_band_max": 212_000,
        "is_manager_level": True,
    },
    {
        "code": "L6",
        "name": "Director",
        "rank": 6,
        "comp_band_min": 205_000,
        "comp_band_max": 285_000,
        "is_manager_level": True,
    },
]

#: Level distribution for individual contributors (L1-L4 only).
IC_LEVEL_MIX: dict[str, float] = {"L1": 0.18, "L2": 0.31, "L3": 0.34, "L4": 0.17}


# --- Sources ----------------------------------------------------------------
SOURCES: list[dict[str, object]] = [
    {"code": "REFERRAL", "name": "Employee Referral", "channel_type": ChannelType.REFERRAL},
    {"code": "AGENCY", "name": "External Agency", "channel_type": ChannelType.AGENCY},
    {"code": "JOBBOARD", "name": "Job Board", "channel_type": ChannelType.JOB_BOARD},
    {"code": "INBOUND", "name": "Inbound Application", "channel_type": ChannelType.INBOUND},
    {"code": "CAMPUS", "name": "Campus Hiring", "channel_type": ChannelType.CAMPUS},
    {"code": "INTERNAL", "name": "Internal Transfer", "channel_type": ChannelType.INTERNAL},
]

#: Share of hires per channel. Sums to 1.0 — asserted in tests.
SOURCE_MIX: dict[str, float] = {
    "REFERRAL": 0.24,
    "AGENCY": 0.17,
    "JOBBOARD": 0.22,
    "INBOUND": 0.19,
    "CAMPUS": 0.11,
    "INTERNAL": 0.07,
}


# --- Surveys ----------------------------------------------------------------
#: Six consecutive quarterly surveys. Deliberately spanning the reorg: two before
#: it, the two affected quarters, and two after, so the dip has a baseline to be
#: measured against and a recovery to show.
SURVEY_QUARTERS: list[date] = [
    date(2025, 1, 1),
    date(2025, 4, 1),
    date(2025, 7, 1),
    date(2025, 10, 1),
    date(2026, 1, 1),
    date(2026, 4, 1),
]


def survey_rows() -> list[dict[str, object]]:
    """Six surveys, each opening in the last month of its quarter."""
    rows: list[dict[str, object]] = []
    for index, quarter in enumerate(SURVEY_QUARTERS, start=1):
        opens = add_months(quarter, 2)
        rows.append(
            {
                "survey_id": index,
                "code": f"Q{(quarter.month - 1) // 3 + 1}-{quarter.year % 100:02d}",
                "name": f"Q{(quarter.month - 1) // 3 + 1} {quarter.year} Engagement Pulse",
                "quarter_start": quarter,
                "opens_on": opens,
                "closes_on": month_end(opens),
            }
        )
    return rows


# --- Training catalog -------------------------------------------------------
COURSES: list[dict[str, object]] = [
    {"code": "SEC-101", "name": "Security Awareness", "hours": 2.0},
    {"code": "MGR-201", "name": "First-Time Manager", "hours": 12.0},
    {"code": "DEI-101", "name": "Inclusive Collaboration", "hours": 3.0},
    {"code": "TECH-310", "name": "System Design Fundamentals", "hours": 16.0},
    {"code": "COMM-140", "name": "Written Communication", "hours": 6.0},
    {"code": "DATA-220", "name": "Analytics for Decisions", "hours": 10.0},
    {"code": "SUP-115", "name": "De-escalation Skills", "hours": 5.0},
    {"code": "SAL-260", "name": "Consultative Selling", "hours": 14.0},
]


# --- Name pools -------------------------------------------------------------
FIRST_NAMES: list[str] = [
    "Amara",
    "Noor",
    "Diego",
    "Priya",
    "Elena",
    "Kwame",
    "Yuki",
    "Rohan",
    "Sofia",
    "Marcus",
    "Leila",
    "Tobias",
    "Ines",
    "Hiro",
    "Fatima",
    "Andre",
    "Mei",
    "Jonas",
    "Zara",
    "Emeka",
    "Clara",
    "Ravi",
    "Anja",
    "Luca",
    "Nadia",
    "Omar",
    "Freya",
    "Samuel",
    "Aiko",
    "Bruno",
    "Tanvi",
    "Isaac",
    "Camila",
    "Dmitri",
    "Esther",
    "Farid",
    "Greta",
    "Hassan",
    "Iris",
    "Javier",
    "Keiko",
    "Liam",
    "Maya",
    "Nikolai",
    "Oona",
    "Pablo",
    "Qi",
    "Rosa",
    "Sanjay",
    "Thea",
    "Ulf",
    "Vera",
    "Wanjiru",
    "Xander",
    "Yara",
    "Zoltan",
    "Adaeze",
    "Bao",
    "Cecile",
    "Dario",
]

# --- Surrogate key maps -----------------------------------------------------
# Dimension rows are inserted with explicit sequential ids in list order, so these
# maps are stable across runs. Every generator module resolves a code to an id
# through here rather than querying the database mid-generation.
DEPARTMENT_IDS: dict[str, int] = {
    str(row["code"]): index for index, row in enumerate(DEPARTMENTS, start=1)
}
LOCATION_IDS: dict[str, int] = {row["code"]: index for index, row in enumerate(LOCATIONS, start=1)}
JOB_LEVEL_IDS: dict[str, int] = {
    str(row["code"]): index for index, row in enumerate(JOB_LEVELS, start=1)
}
SOURCE_IDS: dict[str, int] = {str(row["code"]): index for index, row in enumerate(SOURCES, start=1)}

JOB_LEVEL_BY_CODE: dict[str, dict[str, object]] = {str(row["code"]): row for row in JOB_LEVELS}
DEPARTMENT_BY_CODE: dict[str, dict[str, object]] = {str(row["code"]): row for row in DEPARTMENTS}

BILLABLE_DEPARTMENTS: tuple[str, ...] = tuple(
    str(row["code"]) for row in DEPARTMENTS if row["is_billable"]
)
REVENUE_DEPARTMENTS: tuple[str, ...] = tuple(
    str(row["code"]) for row in DEPARTMENTS if row["carries_revenue"]
)


LAST_NAMES: list[str] = [
    "Okonkwo",
    "Haddad",
    "Moreau",
    "Sharma",
    "Kovacs",
    "Mensah",
    "Tanaka",
    "Iyer",
    "Rossi",
    "Bennett",
    "Aziz",
    "Lindqvist",
    "Ferreira",
    "Yamada",
    "Cisse",
    "Duarte",
    "Chen",
    "Weber",
    "Ahmadi",
    "Nwosu",
    "Novak",
    "Pillai",
    "Berg",
    "Marchetti",
    "Rahimi",
    "Faraj",
    "Solberg",
    "Adeyemi",
    "Kondo",
    "Silva",
    "Desai",
    "Fischer",
    "Alvarez",
    "Petrov",
    "Cohen",
    "Boulos",
    "Schmidt",
    "Karim",
    "Murphy",
    "Ortega",
    "Nakamura",
    "Doyle",
    "Reyes",
    "Volkov",
    "Laine",
    "Castillo",
    "Zhang",
    "Ibarra",
    "Menon",
    "Nilsson",
    "Bergstrom",
    "Costa",
    "Kamau",
    "Whitfield",
    "Ozturk",
    "Varga",
    "Eze",
    "Nguyen",
    "Dubois",
    "Ricci",
]
