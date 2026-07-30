"""Requisitions, applications, and funnel stage events.

Dates are built **backwards from the hire date**, which is the only way to make
time-to-fill land on an exact target. Forward construction would accumulate noise
across five stages and Sales' 74-day target would drift by a fortnight.

Each requisition is single-channel. That is a simplification of real recruiting,
but it is what makes "agency cost per hire is 3x referral" measurable at all: cost
lives on the requisition, so a mixed-channel req would have no attributable cost
per channel.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.models.enums import ApplicationStage, RequisitionStatus
from seed import scenarios as sc
from seed.people import Person
from seed.reference import (
    DEPARTMENT_IDS,
    JOB_LEVEL_IDS,
    LOCATION_IDS,
    SOURCE_IDS,
    WINDOW_END,
    WINDOW_START,
)
from seed.util import dec

#: Applications needed per hire, by channel. Referrals convert efficiently; job
#: boards and inbound do not. This spread is what gives Source Effectiveness
#: something to show — a flat rate across channels would make the metric useless.
APPS_PER_HIRE: dict[str, int] = {
    "REFERRAL": 6,
    "AGENCY": 9,
    "JOBBOARD": 16,
    "INBOUND": 20,
    "CAMPUS": 12,
    "INTERNAL": 3,
}

#: External spend per requisition by channel. Agency fees dominate; the referral
#: figure is a bonus payment.
EXTERNAL_COST: dict[str, tuple[int, int]] = {
    "REFERRAL": (3_000, 5_000),
    "AGENCY": (20_000, 28_000),
    "JOBBOARD": (1_500, 3_500),
    "INBOUND": (400, 1_200),
    "CAMPUS": (2_000, 4_200),
    "INTERNAL": (0, 500),
}

#: Where non-hired candidates stop. Applied-only dominates, as in real funnels.
NON_HIRE_FINAL_STAGE: tuple[tuple[ApplicationStage, float], ...] = (
    (ApplicationStage.APPLIED, 0.60),
    (ApplicationStage.SCREEN, 0.26),
    (ApplicationStage.INTERVIEW, 0.11),
    (ApplicationStage.OFFER, 0.03),
)

OPEN_REQUISITIONS = 45
AGED_OPEN_REQUISITIONS = 28
CANCELLED_REQUISITIONS = 25


@dataclass
class RecruitingData:
    requisitions: list[dict[str, object]]
    applications: list[dict[str, object]]
    stage_events: list[dict[str, object]]


def _interview_dwell(rng: np.random.Generator, department: str) -> int:
    """The Sales bottleneck lives here."""
    if department == "SAL":
        return int(round(sc.SALES_INTERVIEW_DWELL_DAYS + rng.normal(0, 3.0)))
    return max(4, int(round(sc.COMPANY_INTERVIEW_DWELL_DAYS + rng.normal(0, 2.5))))


def _time_to_fill(rng: np.random.Generator, department: str) -> int:
    if department == "SAL":
        return int(round(sc.SALES_TIME_TO_FILL_DAYS + rng.normal(0, 4.0)))
    return max(14, int(round(sc.COMPANY_TIME_TO_FILL_DAYS + rng.normal(0, 3.5))))


def _hired_timeline(
    rng: np.random.Generator, hire: Person
) -> tuple[date, date, list[tuple[ApplicationStage, date, date | None]]]:
    """Build one winning candidate's stage timeline backwards from their start date.

    Returns (first_application_date, offer_accepted_date, stages).
    """
    notice_days = int(rng.integers(14, 29))
    offer_accepted = hire.hire_date - timedelta(days=notice_days)

    offer_days = int(rng.integers(5, 11))
    dwell = _interview_dwell(rng, hire.department)
    screen_days = int(rng.integers(4, 9))
    applied_days = int(rng.integers(2, 7))

    offer_entered = offer_accepted - timedelta(days=offer_days)
    interview_entered = offer_entered - timedelta(days=dwell)
    screen_entered = interview_entered - timedelta(days=screen_days)
    applied_on = screen_entered - timedelta(days=applied_days)

    stages = [
        (ApplicationStage.APPLIED, applied_on, screen_entered),
        (ApplicationStage.SCREEN, screen_entered, interview_entered),
        (ApplicationStage.INTERVIEW, interview_entered, offer_entered),
        (ApplicationStage.OFFER, offer_entered, offer_accepted),
        (ApplicationStage.HIRED, offer_accepted, None),
    ]
    return applied_on, offer_accepted, stages


def _non_hire_timeline(
    rng: np.random.Generator, department: str, opened: date, ceiling: date
) -> tuple[ApplicationStage, list[tuple[ApplicationStage, date, date | None]], date | None]:
    """A losing candidate: stages up to wherever they stopped."""
    stages_pool = [stage for stage, _ in NON_HIRE_FINAL_STAGE]
    weights = np.array([weight for _, weight in NON_HIRE_FINAL_STAGE], dtype=float)
    weights = weights / weights.sum()
    final = stages_pool[int(rng.choice(len(stages_pool), p=weights))]

    span = max(1, (ceiling - opened).days)
    applied_on = opened + timedelta(days=int(rng.integers(0, span)))

    order = [
        ApplicationStage.APPLIED,
        ApplicationStage.SCREEN,
        ApplicationStage.INTERVIEW,
        ApplicationStage.OFFER,
    ]
    durations = {
        ApplicationStage.APPLIED: int(rng.integers(2, 8)),
        ApplicationStage.SCREEN: int(rng.integers(4, 12)),
        ApplicationStage.INTERVIEW: _interview_dwell(rng, department),
        ApplicationStage.OFFER: int(rng.integers(4, 12)),
    }

    stages: list[tuple[ApplicationStage, date, date | None]] = []
    cursor = applied_on
    reached = order[: order.index(final) + 1]
    for index, stage in enumerate(reached):
        exits = cursor + timedelta(days=durations[stage])
        is_last = index == len(reached) - 1
        stages.append((stage, cursor, None if is_last else exits))
        cursor = exits

    # The last stage they reached is where they were rejected, or declined an offer.
    outcome_date = min(cursor, WINDOW_END)
    return final, stages, outcome_date


def build_recruiting(
    people: list[Person], rng: np.random.Generator, scale: float
) -> RecruitingData:
    """Group window hires into single-channel requisitions, then build the funnel."""
    window_hires = [p for p in people if p.hire_date >= WINDOW_START and p.source]

    # Group by (department, channel) so cost attribution per channel is unambiguous.
    grouped: dict[tuple[str, str], list[Person]] = {}
    for hire in window_hires:
        grouped.setdefault((hire.department, str(hire.source)), []).append(hire)

    requisitions: list[dict[str, object]] = []
    applications: list[dict[str, object]] = []
    stage_events: list[dict[str, object]] = []

    req_number = 0
    application_id = 0
    stage_event_id = 0

    def next_req_id() -> str:
        nonlocal req_number
        req_number += 1
        return f"R-{req_number:04d}"

    for (department, source), hires in sorted(grouped.items()):
        hires.sort(key=lambda person: person.hire_date)
        index = 0
        while index < len(hires):
            # One opening per requisition. Multi-opening reqs were tried first and
            # broke time to fill: consecutive same-department, same-channel hires are
            # typically weeks apart, so batching them dragged `opened_date` back far
            # enough that mean TTF measured 183 days against a 74-day target. Time to
            # fill is an asserted scenario number; the plan's "410 requisitions" was an
            # unasserted volume estimate, so the requisition count gives way instead.
            batch = hires[index : index + 1]
            index += 1

            requisition_id = next_req_id()
            timelines = [_hired_timeline(rng, hire) for hire in batch]
            earliest_applied = min(applied for applied, _, _ in timelines)
            latest_accepted = max(accepted for _, accepted, _ in timelines)

            opened = latest_accepted - timedelta(days=_time_to_fill(rng, department))
            opened = min(opened, earliest_applied - timedelta(days=1))
            low, high = EXTERNAL_COST[source]

            requisitions.append(
                {
                    "requisition_id": requisition_id,
                    "department_id": DEPARTMENT_IDS[department],
                    "location_id": LOCATION_IDS[batch[0].location],
                    "job_level_id": JOB_LEVEL_IDS[batch[0].job_level],
                    "hiring_manager_id": batch[0].manager_id,
                    "status": RequisitionStatus.FILLED,
                    "opened_date": opened,
                    "closed_date": latest_accepted,
                    "target_start_date": batch[0].hire_date,
                    "openings": len(batch),
                    "internal_cost": dec(int(rng.integers(3_000, 7_200))),
                    "external_cost": dec(int(rng.integers(low, high + 1))),
                }
            )

            # The winning candidates.
            for hire, (applied_on, accepted_on, stages) in zip(batch, timelines, strict=True):
                application_id += 1
                offer_entered = next(
                    entered for stage, entered, _ in stages if stage == ApplicationStage.OFFER
                )
                applications.append(
                    {
                        "application_id": application_id,
                        "requisition_id": requisition_id,
                        "source_id": SOURCE_IDS[source],
                        "candidate_ref": f"C-{application_id:06d}",
                        "first_application_date": applied_on,
                        "final_stage": ApplicationStage.HIRED,
                        "offer_extended_date": offer_entered,
                        "offer_accepted_date": accepted_on,
                        "offer_declined_date": None,
                        "rejected_date": None,
                        "hired_employee_id": hire.employee_id,
                    }
                )
                for stage, entered, exited in stages:
                    stage_event_id += 1
                    stage_events.append(
                        {
                            "stage_event_id": stage_event_id,
                            "application_id": application_id,
                            "stage": stage,
                            "entered_on": entered,
                            "exited_on": exited,
                        }
                    )

            # The losing candidates, sized so this channel's conversion rate holds.
            extra = max(0, APPS_PER_HIRE[source] * len(batch) - len(batch))
            for _ in range(extra):
                application_id += 1
                final, stages, outcome = _non_hire_timeline(
                    rng, department, opened, latest_accepted
                )
                declined = final == ApplicationStage.OFFER
                offer_entered = next(
                    (entered for stage, entered, _ in stages if stage == ApplicationStage.OFFER),
                    None,
                )
                applications.append(
                    {
                        "application_id": application_id,
                        "requisition_id": requisition_id,
                        "source_id": SOURCE_IDS[source],
                        "candidate_ref": f"C-{application_id:06d}",
                        "first_application_date": stages[0][1],
                        "final_stage": final,
                        "offer_extended_date": offer_entered,
                        "offer_accepted_date": None,
                        "offer_declined_date": outcome if declined else None,
                        "rejected_date": None if declined else outcome,
                        "hired_employee_id": None,
                    }
                )
                for stage, entered, exited in stages:
                    stage_event_id += 1
                    stage_events.append(
                        {
                            "stage_event_id": stage_event_id,
                            "application_id": application_id,
                            "stage": stage,
                            "entered_on": entered,
                            "exited_on": exited,
                        }
                    )

    # --- Open and cancelled requisitions ------------------------------------
    # Requisition aging counts open reqs older than 60 days, so a deliberate share
    # of these are aged past that line.
    departments = list(DEPARTMENT_IDS)
    n_open = max(6, round(OPEN_REQUISITIONS * scale))
    n_aged = max(4, round(AGED_OPEN_REQUISITIONS * scale))
    n_cancelled = max(3, round(CANCELLED_REQUISITIONS * scale))

    for position in range(n_open):
        department = departments[position % len(departments)]
        age_days = int(rng.integers(61, 190)) if position < n_aged else int(rng.integers(5, 59))
        opened = WINDOW_END - timedelta(days=age_days)
        requisition_id = next_req_id()
        source = "JOBBOARD" if position % 2 else "AGENCY"
        low, high = EXTERNAL_COST[source]
        requisitions.append(
            {
                "requisition_id": requisition_id,
                "department_id": DEPARTMENT_IDS[department],
                "location_id": LOCATION_IDS[list(LOCATION_IDS)[position % len(LOCATION_IDS)]],
                "job_level_id": JOB_LEVEL_IDS[f"L{1 + position % 4}"],
                "hiring_manager_id": None,
                "status": RequisitionStatus.OPEN,
                "opened_date": opened,
                "closed_date": None,
                "target_start_date": opened + timedelta(days=60),
                "openings": 1,
                "internal_cost": dec(int(rng.integers(2_000, 6_000))),
                "external_cost": dec(int(rng.integers(low, high + 1))),
            }
        )
        for _ in range(int(rng.integers(4, 14))):
            application_id += 1
            final, stages, outcome = _non_hire_timeline(rng, department, opened, WINDOW_END)
            applications.append(
                {
                    "application_id": application_id,
                    "requisition_id": requisition_id,
                    "source_id": SOURCE_IDS[source],
                    "candidate_ref": f"C-{application_id:06d}",
                    "first_application_date": stages[0][1],
                    "final_stage": final,
                    "offer_extended_date": None,
                    "offer_accepted_date": None,
                    "offer_declined_date": None,
                    "rejected_date": None,
                    "hired_employee_id": None,
                }
            )
            for stage, entered, exited in stages:
                stage_event_id += 1
                stage_events.append(
                    {
                        "stage_event_id": stage_event_id,
                        "application_id": application_id,
                        "stage": stage,
                        "entered_on": entered,
                        # Still in flight: the current stage has no exit, which is what
                        # makes an open pipeline distinguishable from a closed one.
                        "exited_on": exited,
                    }
                )

    for position in range(n_cancelled):
        department = departments[position % len(departments)]
        opened = WINDOW_END - timedelta(days=int(rng.integers(120, 700)))
        requisition_id = next_req_id()
        requisitions.append(
            {
                "requisition_id": requisition_id,
                "department_id": DEPARTMENT_IDS[department],
                "location_id": LOCATION_IDS[list(LOCATION_IDS)[position % len(LOCATION_IDS)]],
                "job_level_id": JOB_LEVEL_IDS[f"L{1 + position % 4}"],
                "hiring_manager_id": None,
                "status": RequisitionStatus.CANCELLED,
                "opened_date": opened,
                "closed_date": opened + timedelta(days=int(rng.integers(20, 90))),
                "target_start_date": None,
                "openings": 1,
                "internal_cost": dec(int(rng.integers(1_000, 4_000))),
                "external_cost": dec(0),
            }
        )

    return RecruitingData(
        requisitions=requisitions, applications=applications, stage_events=stage_events
    )
