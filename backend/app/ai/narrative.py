"""Generated prose over already-computed metrics.

Two features, one rule: **the model never computes anything**. It is handed numbers that
the metric layer produced and tested, and its only job is to say which of them matter and
in what order. Everything the summary states is therefore a number that already appears on
a page and already has a hand-computed test behind it.

That constraint is the difference between a summary a reviewer can trust and a paragraph of
plausible arithmetic. It also means the failure mode is mild: a bad summary emphasises the
wrong true thing, rather than asserting a false one.

`executive_summary` reuses `overview.build_overview` and the manager ranking rather than
recomputing either, so the bullets and the cards on screen cannot disagree.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.ai.cache import get_or_call
from app.ai.provider import AiUnavailableError, get_provider
from app.config import settings
from app.metrics import engagement, flight_risk, overview, retention
from app.metrics.filters import MetricFilters

log = logging.getLogger(__name__)

SUMMARY_FEATURE = "narrative"
RISK_FEATURE = "risk_explanation"

DEPARTMENTS: dict[int, str] = {
    1: "Engineering",
    2: "Sales",
    3: "Support",
    4: "Operations",
    5: "Product",
    6: "Marketing",
    7: "Finance",
    8: "People",
}

#: Three, per BUILD_PLAN section 6. A summary long enough to skim is not a summary.
BULLET_COUNT = 3


@dataclass(frozen=True, slots=True)
class Narrative:
    bullets: tuple[str, ...]
    headline: str
    model: str
    cached: bool
    generated_at: str
    stale: bool = False


SUMMARY_SYSTEM = """\
You write the executive summary at the top of an HR analytics dashboard, for a Chief People \
Officer who has thirty seconds.

You are given metrics that have already been computed and tested. Your job is to decide \
which of them matter and say so. You must not calculate anything, and you must not state a \
number that is not in the input — if a figure you want is missing, write around it.

Write exactly {bullets} bullets. Each one:
- names a specific department, manager or channel, and quotes the actual figure;
- says what changed or how it compares, not just what the number is;
- is one sentence, under 28 words, in plain British English with no jargon and no hedging.

Any field whose name ends in `_percent`, or whose unit is "percent", is already a \
percentage: write 87.8 as "87.8%", never as "0.88" and never by converting it yourself.

Lead with the finding that would change what someone does this week. A bullet that says \
"attrition is 20.8%" is worth nothing; one that says which team is driving it is worth \
reading.

Each bullet must cover a different area — retention, hiring, engagement, productivity or \
flight risk. Three bullets naming three managers is one finding written three times, and \
it wastes the only two lines you have to tell the reader about the rest of the business.

Do not open with "This dashboard shows" or any other throat-clearing. Do not recommend \
actions — the reader knows their business and you do not.

Also return a headline of at most eight words naming the single most important thing."""


_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "bullets"],
}


def _round1(value: Any) -> Any:
    return (
        round(value, 1) if isinstance(value, int | float) and not isinstance(value, bool) else value
    )


def _as_percent(value: float | None) -> float | None:
    """0.878 -> 87.8. One decimal, because a summary quoting 87.83% is not a summary."""
    return None if value is None else round(value * 100, 1)


def _multiple(value: float | None, baseline: float | None) -> float | None:
    """How many times the baseline, which is the comparison that makes a rate mean anything."""
    if value is None or not baseline:
        return None
    return round(value / baseline, 1)


def _facts(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """The numbers the model is allowed to talk about.

    Every one comes from a tested metric function. Nothing is computed here beyond picking
    the top few rows, which is selection rather than arithmetic.
    """
    data = overview.build_overview(db, filters)

    # Rates arrive as 0-1 fractions because CLAUDE.md has the API return raw numbers and the
    # frontend format them. Prose is the one place that rule cannot hold: the model writes
    # the final string, so it has to be handed a percentage or it writes "a rate of 0.88".
    # Converting here rather than asking the model to multiply also keeps the standing rule
    # that it never does arithmetic.
    kpis = {
        kpi["key"]: {
            "label": kpi["label"],
            "value": _as_percent(kpi["value"]) if kpi["unit"] == "rate" else kpi["value"],
            "previous": _as_percent(kpi["previous"]) if kpi["unit"] == "rate" else kpi["previous"],
            "change_vs_previous_pct": kpi["delta_pct"],
            "unit": "percent" if kpi["unit"] == "rate" else kpi["unit"],
            "higher_is_better": kpi["higher_is_better"],
        }
        for kpi in data["kpis"]
    }

    managers = [
        {
            "manager_id": row["manager_id"],
            "department": DEPARTMENTS.get(row["department_id"] or 0, "unknown"),
            "annualized_attrition_percent": _as_percent(row["annualized_rate"]),
            "company_attrition_percent": _as_percent(row["company_annualized_rate"]),
            "times_the_company_rate": _multiple(
                row["annualized_rate"], row["company_annualized_rate"]
            ),
            "exits": row["terminations"],
            "avg_team": round(row["avg_reports"], 1),
        }
        for row in retention.attrition_by_manager_trailing(db, filters)[:3]
    ]

    # Rounded before it goes anywhere near the prompt. A model handed 58.03724928366763
    # writes 58.03724928366763, and a summary is the one output with no formatter between
    # the number and the reader.
    drivers = [
        {
            "department": DEPARTMENTS.get(row["department_id"] or 0, "unknown"),
            "engagement_index": _round1(row["engagement_index"]),
            **{k: _round1(v) for k, v in row.items() if k.startswith("driver_")},
        }
        for row in engagement.driver_breakdown_by_department(db, filters)[:3]
    ]

    return {
        "period": {"from": str(data["period_from"]), "to": str(data["period_to"])},
        "comparison": {"from": str(data["comparison_from"]), "to": str(data["comparison_to"])},
        "kpis": kpis,
        "worst_managers_trailing_12m": managers,
        "lowest_engagement_departments": drivers,
        "risk_bands": {
            row["band"]: row["employees"] for row in flight_risk.band_summary(db, filters)
        },
    }


def executive_summary(
    db: Session, filters: MetricFilters, *, provider: Any | None = None
) -> Narrative:
    """Three bullets over the current slice, cached per slice."""
    provider = provider or get_provider()
    if provider is None:
        raise AiUnavailableError("The summary needs an AI key. Set GOOGLE_API_KEY in backend/.env.")

    model = settings.resolved_models[0] or ""
    facts = _facts(db, filters)

    def call() -> dict[str, Any]:
        import json

        completion = provider.complete_json(
            system=SUMMARY_SYSTEM.format(bullets=BULLET_COUNT),
            user=json.dumps(facts, indent=2, default=str),
            schema=_SUMMARY_SCHEMA,
            model=model,
        )
        return completion.data

    cached = get_or_call(
        db,
        feature=SUMMARY_FEATURE,
        model=model,
        # Keyed on the facts, not on the filters. Two slices producing identical numbers
        # are the same summary, and — more usefully — a filter that changes nothing on
        # screen does not cost a second call.
        inputs={"facts": facts},
        call=call,
    )

    bullets = [str(b).strip() for b in cached.payload.get("bullets", []) if str(b).strip()]
    return Narrative(
        bullets=tuple(bullets[:BULLET_COUNT]),
        headline=str(cached.payload.get("headline") or "").strip(),
        model=cached.model,
        cached=cached.cached,
        generated_at=cached.generated_at.isoformat(),
        stale=cached.stale,
    )


RISK_SYSTEM = """\
You explain one employee's flight-risk score to their HR business partner.

The score is a transparent weighted sum of five components — there is no model to \
interpret, only arithmetic to put into words. You are given each component's score out of \
100, its fixed weight, and how many points it contributed.

Write one short paragraph, at most four sentences:
- lead with the component that contributed most, and say what it means in plain terms;
- mention the second contributor only if it is material;
- state the total and the band.

Do not invent a reason that is not in the components. Do not recommend an intervention. Do \
not speculate about the person — you know five numbers about their situation and nothing \
about them."""

_RISK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"explanation": {"type": "string"}},
    "required": ["explanation"],
}


@dataclass(frozen=True, slots=True)
class RiskExplanation:
    employee_id: str
    score: float
    band: str
    explanation: str
    components: list[str]
    model: str
    cached: bool


def explain_risk(
    db: Session, employee_id: str, *, provider: Any | None = None
) -> RiskExplanation | None:
    """Plain-English reasoning for one score, or None when the employee has no score."""
    match = next(
        (
            row
            for row in flight_risk.top_risks(db, MetricFilters(), limit=5000)
            if row["employee_id"] == employee_id
        ),
        None,
    )
    if match is None:
        return None

    sentences = [
        f"{name}: score {values['score']:.0f}/100, weight {values['weight']:.0%}, "
        f"contributing {values['contribution']:.1f} points"
        for name, values in sorted(
            match["components"].items(),
            key=lambda item: item[1]["contribution"],
            reverse=True,
        )
    ]

    provider = provider or get_provider()
    if provider is None:
        raise AiUnavailableError("Risk explanations need an AI key.")

    model = settings.resolved_models[0] or ""
    facts = {
        "total_score": match["score"],
        "band": match["band"],
        "components": sentences,
    }

    def call() -> dict[str, Any]:
        import json

        completion = provider.complete_json(
            system=RISK_SYSTEM,
            user=json.dumps(facts, indent=2, default=str),
            schema=_RISK_SCHEMA,
            model=model,
        )
        return completion.data

    cached = get_or_call(db, feature=RISK_FEATURE, model=model, inputs=facts, call=call)

    return RiskExplanation(
        employee_id=employee_id,
        score=match["score"],
        band=match["band"],
        explanation=str(cached.payload.get("explanation") or "").strip(),
        components=sentences,
        model=cached.model,
        cached=cached.cached,
    )
