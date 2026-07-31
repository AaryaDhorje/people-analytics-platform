"""The six planted scenarios, as data rather than prose.

`BUILD_PLAN.md` §3 is the source. Each scenario carries the knobs the generator
reads *and* the assertions `validate.py` recomputes from the database, so "the
signal is present" is a checked claim rather than a hope. Tuning a scenario means
changing a number here and re-running — never editing generation logic.

Two generation modes are used deliberately:

- **Sampled** — ambient patterns (department base rates, tenure effects, channel
  effects) come from relative hazard weights. This produces realistic texture.
- **Forced** — any number the Loom says out loud is exact. M-114 has precisely six
  exits with precisely four rated 4+, because "four of his six leavers were high
  performers" is a sentence spoken on camera and a sampled 5-of-7 would make the
  narration wrong.
"""

from dataclasses import dataclass, field
from datetime import date

# --- Company baselines ------------------------------------------------------
# These are pinned by BUILD_PLAN §3's stated volumes. 1,850 total records with
# 1,200 active at the end implies ~650 exits, which against an average headcount
# near 1,150 is ~18% annualized attrition. That is realistic for tech and leaves
# M-114's 2.4x at ~43% — alarming on screen without being absurd.
TOTAL_EMPLOYEES = 1_850
INITIAL_HEADCOUNT = 1_150
HIRES_DURING_WINDOW = 700
TOTAL_EXITS = 650
TARGET_ACTIVE_AT_END = 1_200

REQUISITIONS = 410
APPLICATIONS = 9_200
GOALS = 2_400
SURVEY_PARTICIPATION = 0.70
OPEN_TEXT_SHARE = 0.35
VOLUNTARY_SHARE = 0.72

#: Relative monthly attrition hazard by department. 1.0 is the company baseline;
#: these shape which departments look healthy without any one of them being a
#: planted scenario in its own right.
DEPARTMENT_HAZARD: dict[str, float] = {
    "ENG": 1.00,
    "SAL": 1.35,
    "SUP": 1.25,
    "OPS": 0.90,
    "PRD": 0.80,
    "MKT": 1.05,
    "FIN": 0.70,
    "PPL": 0.75,
}

#: Company-mean engagement driver scores on the 0-100 scale. Stored raw 1-5 in the
#: database and normalized back to 0-100 in views; these are the 0-100 anchors the
#: scenarios are written against.
DRIVER_BASELINE: dict[str, float] = {
    "manager": 72.0,
    "growth": 64.0,
    "recognition": 61.0,
    "workload": 58.0,
    "belonging": 70.0,
}

ENPS_BASELINE_MEAN = 7.2

#: Company-wide time to fill, in days. Sales deviates from this — see scenario 4.
COMPANY_TIME_TO_FILL_DAYS = 38
COMPANY_INTERVIEW_DWELL_DAYS = 12


# --- Assertion vocabulary ---------------------------------------------------


@dataclass(frozen=True)
class Target:
    """One verifiable claim about the generated data.

    `comparison` decides how `validate.py` judges it:
      within   — abs(actual - target) <= tolerance
      at_least — actual >= target - tolerance
      at_most  — actual <= target + tolerance
      exact    — actual == target
    """

    key: str
    label: str
    target: float
    tolerance: float = 0.0
    unit: str = ""
    comparison: str = "within"

    def passes(self, actual: float | None) -> bool:
        if actual is None:
            return False
        if self.comparison == "exact":
            return actual == self.target
        if self.comparison == "at_least":
            return actual >= self.target - self.tolerance
        if self.comparison == "at_most":
            return actual <= self.target + self.tolerance
        return abs(actual - self.target) <= self.tolerance


@dataclass(frozen=True)
class Scenario:
    number: int
    key: str
    title: str
    story: str
    demo_beat: str
    targets: list[Target] = field(default_factory=list)


# --- 1. The bad-manager cluster ---------------------------------------------
# The headline demo moment: the flight-risk model and the manager heatmap surface
# the same person independently.
BAD_MANAGER_ID = "M-114"
BAD_MANAGER_DEPARTMENT = "ENG"
# Sized against measured company attrition in the final three quarters (~29%
# annualized, since the tenure cliff and the post-reorg lag both land there). Six exits
# from a team averaging ~11.5 over that window gives ~63% annualized, i.e. the 2.4x
# ratio. A larger team dilutes the ratio to parity; a smaller one would drop below the
# 8-report floor that docs/METRICS.md sets for Attrition by Manager. 14 shrinking to 8
# satisfies both, and "his team is shrinking" is the truer story anyway.
BAD_MANAGER_TEAM_SIZE = 14
BAD_MANAGER_FORCED_EXITS = 6
BAD_MANAGER_REGRETTED_EXITS = 4
BAD_MANAGER_ATTRITION_RATIO = 2.4
#: The gap the report must *measure* — this is the number in the story.
BAD_MANAGER_DRIVER_GAP = 28.0
#: The offset the generator *applies*, which has to be larger than the gap for two
#: reasons: Engineering sits above the company mean on the manager driver, and the
#: company mean itself includes this team, so lowering their score also lowers the
#: baseline being compared against. Applying a flat 28 measured only 23.
BAD_MANAGER_DRIVER_OFFSET = 33.0
#: Exits are forced into the final three complete quarters.
BAD_MANAGER_EXIT_QUARTERS: tuple[date, ...] = (
    date(2025, 10, 1),
    date(2026, 1, 1),
    date(2026, 4, 1),
)


# --- 2. Sourcing channel decay ----------------------------------------------
AGENCY_12M_RETENTION = 0.62
REFERRAL_12M_RETENTION = 0.88
AGENCY_COST_MULTIPLIER = 3.0
#: Retention at 12 months is only measurable for hires with a full 12 months of
#: window left, so forced exits apply to that eligible subset only.
RETENTION_HORIZON_MONTHS = 12


# --- 3. Post-reorg engagement dip -------------------------------------------
# Q3 2025 is "Q3 of year 2" of the window. Anchored to a calendar quarter so the
# dip lines up with a survey boundary and a chart gridline.
REORG_QUARTER = date(2025, 7, 1)
REORG_TRANSFER_SHARE = 0.22
REORG_DRIVER_DROP = 15.0
REORG_AFFECTED_DRIVERS: tuple[str, ...] = ("belonging", "growth")
#: Surveys whose scores carry the dip.
REORG_AFFECTED_QUARTERS: tuple[date, ...] = (date(2025, 7, 1), date(2025, 10, 1))
REORG_ATTRITION_LAG_QUARTERS = 2
REORG_ATTRITION_HAZARD_BUMP = 1.55

#: Individual engagement has to predict individual attrition, not just move alongside it
#: at company level. Without this, survey scores are generated independently of who leaves
#: and the engagement-quartile-versus-attrition chart shows pure noise — the first
#: measurement had the *most* engaged quartile leaving fastest, at 11.1% against 9.6%.
#:
#: Terminations are assigned before surveys are generated, so the penalty runs the honest
#: direction: someone who is about to leave answers worse beforehand. Bands are
#: (months until exit, points deducted from every driver).
#:
#: These look small, and they have to be. Per-answer noise is 12 points, but the engagement
#: index averages five drivers, so the index's own noise is only 12/sqrt(5) ~= 5.4 points.
#: A 22-point penalty was tried first and is roughly 4 sigma: it sorted every future leaver
#: into the bottom quartile and left quartiles 3 and 4 with literally zero exits, turning a
#: correlation into a step function and making the ratio undefined. Around 1 sigma produces
#: a gradient instead of a partition.
ENGAGEMENT_EXIT_PENALTY: tuple[tuple[int, float], ...] = (
    (3, 6.0),
    (6, 4.0),
    (12, 2.0),
)
#: Bottom engagement quartile should leave at least this many times faster than the top.
ENGAGEMENT_ATTRITION_GRADIENT = 1.8


# --- 4. Sales pipeline bottleneck -------------------------------------------
SALES_INTERVIEW_DWELL_DAYS = 41
SALES_TIME_TO_FILL_DAYS = 74


# --- 5. Burnout in Support --------------------------------------------------
SUPPORT_DEPARTMENT = "SUP"
SUPPORT_OVERTIME_RATE = 0.22
SUPPORT_UTILIZATION = 0.96
SUPPORT_WORKLOAD_DRIVER_OFFSET = -22.0
#: Absenteeism climbs across the final six months of the window.
SUPPORT_ABSENCE_CLIMB_MONTHS = 6
SUPPORT_ABSENCE_CLIMB_FACTOR = 2.3


# --- 6. Tenure cliff --------------------------------------------------------
# "The two most recent hire cohorts" has to mean the two most recent that have
# *reached* 14-18 months inside the window — a cohort hired last quarter cannot
# show a 14-month cliff. These two clear month 18 before the window closes.
CLIFF_COHORT_QUARTERS: tuple[date, ...] = (date(2024, 7, 1), date(2024, 10, 1))
CLIFF_MONTH_RANGE: tuple[int, int] = (14, 18)
CLIFF_HAZARD_MULTIPLIER = 3.4
CLIFF_MIN_RATIO = 1.8


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        number=1,
        key="bad_manager",
        title=f"The bad-manager cluster ({BAD_MANAGER_ID}, Engineering)",
        story=(
            f"{BAD_MANAGER_ID} runs a {BAD_MANAGER_TEAM_SIZE}-person Engineering team with "
            f"{BAD_MANAGER_ATTRITION_RATIO}x company attrition over the last three quarters, "
            f"a manager-driver score {BAD_MANAGER_DRIVER_GAP:.0f} points below the company "
            f"mean, and {BAD_MANAGER_REGRETTED_EXITS} of {BAD_MANAGER_FORCED_EXITS} exits "
            "rated 4 or above."
        ),
        demo_beat="Manager heatmap and flight-risk table surface the same person independently.",
        targets=[
            Target(
                "attrition_ratio",
                f"{BAD_MANAGER_ID} attrition vs company, last 3 quarters",
                BAD_MANAGER_ATTRITION_RATIO,
                0.35,
                "x",
                "at_least",
            ),
            Target(
                "driver_gap",
                "Manager-driver points below company mean",
                BAD_MANAGER_DRIVER_GAP,
                4.0,
                "pts",
            ),
            Target(
                "forced_exits",
                "Exits from this team in the last 3 quarters",
                BAD_MANAGER_FORCED_EXITS,
                0,
                "exits",
                "exact",
            ),
            Target(
                "regretted_exits",
                "Of those, voluntary with last rating >= 4",
                BAD_MANAGER_REGRETTED_EXITS,
                0,
                "exits",
                "exact",
            ),
        ],
    ),
    Scenario(
        number=2,
        key="sourcing_decay",
        title="Sourcing channel decay (agency vs referral)",
        story=(
            f"Agency hires retain at {AGENCY_12M_RETENTION:.0%} over 12 months against "
            f"{REFERRAL_12M_RETENTION:.0%} for referrals, while agency cost per hire runs "
            f"{AGENCY_COST_MULTIPLIER:.0f}x higher."
        ),
        demo_beat="Cost per hire and quality of hire disagree — the insight HR actually wants.",
        targets=[
            Target(
                "agency_retention",
                "Agency 12-month retention",
                AGENCY_12M_RETENTION * 100,
                4.0,
                "%",
            ),
            Target(
                "referral_retention",
                "Referral 12-month retention",
                REFERRAL_12M_RETENTION * 100,
                4.0,
                "%",
            ),
            Target(
                "cost_ratio",
                "Agency cost per hire vs referral",
                AGENCY_COST_MULTIPLIER,
                0.6,
                "x",
                "at_least",
            ),
        ],
    ),
    Scenario(
        number=3,
        key="post_reorg_dip",
        title="Post-reorg engagement dip (Q3 2025)",
        story=(
            f"A reorg in {REORG_QUARTER:%b %Y} moves {REORG_TRANSFER_SHARE:.0%} of staff "
            f"between teams, drops Belonging and Growth by {REORG_DRIVER_DROP:.0f} points for "
            f"two quarters, and is followed by an attrition rise "
            f"{REORG_ATTRITION_LAG_QUARTERS} quarters later."
        ),
        demo_beat="Proves the engagement-to-attrition lag on the chart.",
        targets=[
            Target(
                "belonging_drop",
                "Belonging drop vs pre-reorg surveys",
                REORG_DRIVER_DROP,
                4.0,
                "pts",
            ),
            Target(
                "growth_drop",
                "Growth drop vs pre-reorg surveys",
                REORG_DRIVER_DROP,
                4.0,
                "pts",
            ),
            Target(
                "lagged_attrition_rise",
                "Attrition rise 2 quarters after the reorg",
                1.0,
                0.0,
                "x",
                "at_least",
            ),
            Target(
                "engagement_attrition_gradient",
                "Bottom engagement quartile attrition vs top quartile",
                ENGAGEMENT_ATTRITION_GRADIENT,
                0.3,
                "x",
                "at_least",
            ),
        ],
    ),
    Scenario(
        number=4,
        key="sales_bottleneck",
        title="Sales pipeline bottleneck (Interview stage)",
        story=(
            f"Sales requisitions sit {SALES_INTERVIEW_DWELL_DAYS} days at Interview against "
            f"{COMPANY_INTERVIEW_DWELL_DAYS} days elsewhere, giving a time to fill of "
            f"{SALES_TIME_TO_FILL_DAYS} days against a company average of "
            f"{COMPANY_TIME_TO_FILL_DAYS}."
        ),
        demo_beat="The funnel chart has an obvious pinch point.",
        targets=[
            Target(
                "sales_dwell",
                "Sales mean Interview dwell",
                SALES_INTERVIEW_DWELL_DAYS,
                5.0,
                "days",
            ),
            Target(
                "other_dwell",
                "Non-Sales mean Interview dwell",
                COMPANY_INTERVIEW_DWELL_DAYS,
                4.0,
                "days",
            ),
            Target("sales_ttf", "Sales mean time to fill", SALES_TIME_TO_FILL_DAYS, 8.0, "days"),
            Target(
                "company_ttf",
                "Company mean time to fill",
                COMPANY_TIME_TO_FILL_DAYS,
                6.0,
                "days",
            ),
        ],
    ),
    Scenario(
        number=5,
        key="support_burnout",
        title="Burnout in Support",
        story=(
            f"Support runs {SUPPORT_OVERTIME_RATE:.0%} overtime and "
            f"{SUPPORT_UTILIZATION:.0%} utilization, with absenteeism climbing across the "
            f"final {SUPPORT_ABSENCE_CLIMB_MONTHS} months and the lowest Workload driver "
            "score in the company."
        ),
        demo_beat="Cross-domain story linking Productivity and Engagement.",
        targets=[
            Target(
                "overtime_rate",
                "Support overtime rate",
                SUPPORT_OVERTIME_RATE * 100,
                3.0,
                "%",
            ),
            Target(
                "utilization",
                "Support utilization",
                SUPPORT_UTILIZATION * 100,
                3.0,
                "%",
                "at_least",
            ),
            Target(
                "workload_is_lowest",
                "Support has the company's lowest Workload driver (1 = yes)",
                1,
                0,
                "",
                "exact",
            ),
            Target(
                "absence_climb",
                "Final-month absence rate vs six months earlier",
                1.6,
                0.4,
                "x",
                "at_least",
            ),
        ],
    ),
    Scenario(
        number=6,
        key="tenure_cliff",
        title="Tenure cliff at 14-18 months",
        story=(
            f"The {CLIFF_COHORT_QUARTERS[0]:%b %Y} and {CLIFF_COHORT_QUARTERS[1]:%b %Y} hire "
            f"cohorts show elevated attrition between months {CLIFF_MONTH_RANGE[0]} and "
            f"{CLIFF_MONTH_RANGE[1]}."
        ),
        demo_beat="The cohort survival curve shows a visible knee.",
        targets=[
            Target(
                "cliff_ratio",
                "Attrition in months 14-18 vs adjacent tenure bands",
                CLIFF_MIN_RATIO,
                0.3,
                "x",
                "at_least",
            ),
            Target(
                "cliff_exits",
                "Exits inside the cliff window for those cohorts",
                8,
                0,
                "exits",
                "at_least",
            ),
        ],
    ),
)


def scenario_by_key(key: str) -> Scenario:
    for scenario in SCENARIOS:
        if scenario.key == key:
            return scenario
    raise KeyError(f"unknown scenario: {key}")
