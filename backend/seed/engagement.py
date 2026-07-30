"""Survey responses: eNPS, the five drivers, and open-text comments.

Driver scores are written on the 0-100 scale the scenarios are expressed in, then
converted to the raw 1-5 integers the column stores. Rounding to an integer is
unbiased *because* per-response noise is wide (sigma ~12 points, i.e. ~0.5 raw
points), so the mean survives the round trip through `(raw - 1) / 4 * 100`. With
noise much narrower than that, a planted 28-point gap would read as 25 and the
scenario would fail its own tolerance.

Open text is deliberately clustered on the planted scenarios rather than spread
evenly. Phase 6 asks Haiku to extract themes, and themes only emerge if the
comments actually concentrate somewhere.
"""

from datetime import timedelta

import numpy as np

from seed import scenarios as sc
from seed.people import Person, bad_manager_team
from seed.reference import survey_rows
from seed.util import clamp, dec

DRIVERS: tuple[str, ...] = ("manager", "growth", "recognition", "workload", "belonging")

#: Workload offsets are explicit because scenario 5 asserts Support holds the
#: company's *lowest* Workload score. Leaving that to chance would make the
#: assertion flaky.
WORKLOAD_OFFSET: dict[str, float] = {
    "SUP": sc.SUPPORT_WORKLOAD_DRIVER_OFFSET,
    "SAL": -8.0,
    "OPS": -6.0,
    "ENG": -4.0,
    "PRD": -2.0,
    "MKT": 0.0,
    "FIN": 3.0,
    "PPL": 5.0,
}

#: Small per-department offsets on the other four drivers, so the driver-by-department
#: radar has visible shape without any of it being a planted claim.
_OFFSET_CYCLE = (-5.0, -2.0, 0.0, 3.0, 5.0)

PARTICIPATION_OFFSET: dict[str, float] = {
    "ENG": -0.02,
    "SAL": -0.07,
    "SUP": -0.05,
    "OPS": 0.01,
    "PRD": 0.04,
    "MKT": 0.03,
    "FIN": 0.06,
    "PPL": 0.08,
}

RESPONSE_NOISE = 12.0

COMMENTS_MANAGER = (
    "My manager cancels our one-to-ones more often than not. I have stopped preparing for them.",
    "Feedback only ever arrives when something has gone wrong, and never before.",
    "Decisions about my work get made without me in the room and I hear about them later.",
    "I have asked about progression three times this year and still have no answer.",
    "Our team lead takes credit in reviews for work the team did. Morale is low.",
    "There is no trust on this team. People have stopped speaking up in meetings.",
    "I would stay for the work but I cannot keep working for this manager.",
    "Two people on my team left this quarter and nobody has asked the rest of us why.",
)

COMMENTS_WORKLOAD = (
    "We are covering three queues with two people and it has been like this for months.",
    "I worked most of the last four weekends just to keep the backlog from growing.",
    "Ticket volume keeps climbing and headcount has not moved since last year.",
    "I am tired. Not dramatic, just genuinely tired, and it has stopped being temporary.",
    "On-call has become every other week and the handover notes are never current.",
    "There is no slack in the schedule to fix the things that cause the tickets.",
    "I like this team but the pace is not survivable for another year.",
    "We are rewarded for firefighting and never given time to prevent the fires.",
)

COMMENTS_REORG = (
    "After the reorg I genuinely do not know who my stakeholders are any more.",
    "My new team is fine but I lost the people I had built five years of trust with.",
    "The reorg was announced as an opportunity. It has mostly been a reset to zero.",
    "Nobody explained why the change happened, only that it had.",
    "I was moved to a new group and my old projects were dropped with no handover.",
    "It feels like a different company than the one I joined, and not in a good way.",
    "Growth conversations stopped when the org chart changed and never restarted.",
    "I do not feel like I belong anywhere in the new structure.",
)

COMMENTS_POSITIVE = (
    "Best team I have worked on. People actually help each other here.",
    "My manager gave me a stretch project and then genuinely backed me on it.",
    "The engineering standards here have made me noticeably better at my job.",
    "I felt supported through a hard personal stretch. That mattered a lot.",
    "Onboarding was the smoothest I have experienced anywhere.",
    "Good autonomy, clear goals, and someone actually reads my design docs.",
    "Recognition here is specific rather than generic, which makes it land.",
    "I can see a path to the next level and what it would take to get there.",
)

COMMENTS_NEUTRAL = (
    "Mostly fine. Tooling could be better but nothing is on fire.",
    "Compensation feels slightly behind market but the work is interesting.",
    "Meetings could be halved with no loss of information.",
    "I would like more clarity on how priorities get set above my team.",
    "Remote setup works well for me. Occasional timezone friction with London.",
    "Training budget exists but there is never time to actually use it.",
    "Documentation is patchy. I learn most things by asking someone.",
    "No complaints worth writing down, honestly.",
)


def _driver_scores(
    rng: np.random.Generator,
    person: Person,
    department: str,
    department_index: int,
    *,
    on_bad_team: bool,
    reorg_affected: bool,
) -> dict[str, int]:
    """Scores on 0-100, offset by scenario, returned as raw 1-5 integers."""
    scores: dict[str, int] = {}
    for index, driver in enumerate(DRIVERS):
        value = sc.DRIVER_BASELINE[driver]

        if driver == "workload":
            value += WORKLOAD_OFFSET.get(department, 0.0)
        else:
            value += _OFFSET_CYCLE[(department_index + index) % len(_OFFSET_CYCLE)]

        if driver == "manager" and on_bad_team:
            # Offset, not the asserted gap — see the comment on BAD_MANAGER_DRIVER_OFFSET.
            value -= sc.BAD_MANAGER_DRIVER_OFFSET

        if reorg_affected and driver in sc.REORG_AFFECTED_DRIVERS:
            value -= sc.REORG_DRIVER_DROP

        value += float(rng.normal(0, RESPONSE_NOISE))
        value = clamp(value, 0.0, 100.0)

        # 0-100 -> raw 1-5. Noise above is what keeps this rounding unbiased.
        raw = int(round(1.0 + value / 100.0 * 4.0))
        scores[driver] = int(clamp(raw, 1, 5))
    return scores


def _engagement_index(scores: dict[str, int]) -> float:
    """Mean of the five drivers, back on the 0-100 scale."""
    mean_raw = sum(scores.values()) / len(scores)
    return (mean_raw - 1.0) / 4.0 * 100.0


def _comment(
    rng: np.random.Generator,
    *,
    on_bad_team: bool,
    is_support: bool,
    reorg_affected: bool,
    index: float,
) -> str:
    """Pick a comment pool that matches why this person is unhappy, if they are."""
    if on_bad_team and float(rng.random()) < 0.75:
        pool = COMMENTS_MANAGER
    elif is_support and float(rng.random()) < 0.70:
        pool = COMMENTS_WORKLOAD
    elif reorg_affected and float(rng.random()) < 0.55:
        pool = COMMENTS_REORG
    elif index >= 70:
        pool = COMMENTS_POSITIVE
    elif index >= 52:
        pool = COMMENTS_NEUTRAL
    else:
        pool = rng.choice(  # type: ignore[assignment]
            [COMMENTS_WORKLOAD, COMMENTS_MANAGER, COMMENTS_NEUTRAL], p=[0.4, 0.35, 0.25]
        )
    return str(pool[int(rng.integers(len(pool)))])


def build_survey_responses(
    people: list[Person], rng: np.random.Generator
) -> list[dict[str, object]]:
    surveys = survey_rows()
    department_order = list(WORKLOAD_OFFSET)
    bad_team_ids = {p.employee_id for p in bad_manager_team(people)}

    rows: list[dict[str, object]] = []
    response_id = 0

    for survey in surveys:
        closes_on = survey["closes_on"]
        quarter = survey["quarter_start"]
        reorg_affected = quarter in sc.REORG_AFFECTED_QUARTERS

        for person in people:
            if not person.active_on(closes_on):  # type: ignore[arg-type]
                continue
            department, _, _, _ = person.state_at(closes_on)  # type: ignore[arg-type]

            participation = sc.SURVEY_PARTICIPATION + PARTICIPATION_OFFSET.get(department, 0.0)
            if float(rng.random()) > participation:
                continue

            on_bad_team = person.employee_id in bad_team_ids
            department_index = (
                department_order.index(department) if department in department_order else 0
            )
            scores = _driver_scores(
                rng,
                person,
                department,
                department_index,
                on_bad_team=on_bad_team,
                reorg_affected=reorg_affected,
            )
            index = _engagement_index(scores)

            enps = sc.ENPS_BASELINE_MEAN + (index - 65.0) * 0.06 + float(rng.normal(0, 1.3))
            enps_score = int(clamp(round(enps), 0, 10))

            # Low scorers are likelier to write something, which is also true in life.
            comment_chance = sc.OPEN_TEXT_SHARE + (0.30 if index < 50 else 0.0)
            open_text = (
                _comment(
                    rng,
                    on_bad_team=on_bad_team,
                    is_support=department == sc.SUPPORT_DEPARTMENT,
                    reorg_affected=reorg_affected,
                    index=index,
                )
                if float(rng.random()) < comment_chance
                else None
            )

            response_id += 1
            opens_on = survey["opens_on"]
            span = (closes_on - opens_on).days  # type: ignore[operator]
            rows.append(
                {
                    "response_id": response_id,
                    "survey_id": survey["survey_id"],
                    "employee_id": person.employee_id,
                    "submitted_on": opens_on + timedelta(days=int(rng.integers(0, max(1, span)))),
                    "enps_score": enps_score,
                    "driver_manager": scores["manager"],
                    "driver_growth": scores["growth"],
                    "driver_recognition": scores["recognition"],
                    "driver_workload": scores["workload"],
                    "driver_belonging": scores["belonging"],
                    "open_text": open_text,
                }
            )
    return rows


def engagement_quartile_hint(rows: list[dict[str, object]]) -> dict[str, float]:
    """Mean engagement index per employee — used by the flight-risk seed in phase 3.

    Computed here because the driver-to-index conversion lives in this module and
    duplicating it elsewhere is how the two would drift apart.
    """
    totals: dict[str, list[float]] = {}
    for row in rows:
        scores = {
            "manager": int(row["driver_manager"]),  # type: ignore[arg-type]
            "growth": int(row["driver_growth"]),  # type: ignore[arg-type]
            "recognition": int(row["driver_recognition"]),  # type: ignore[arg-type]
            "workload": int(row["driver_workload"]),  # type: ignore[arg-type]
            "belonging": int(row["driver_belonging"]),  # type: ignore[arg-type]
        }
        totals.setdefault(str(row["employee_id"]), []).append(_engagement_index(scores))
    return {
        employee_id: float(dec(sum(values) / len(values), 2))
        for employee_id, values in totals.items()
    }
