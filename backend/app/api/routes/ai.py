"""AI endpoints.

Thin, like every other router: parse input, call into `app/ai/`, wrap in the envelope.

The one rule specific to this file: **an unconfigured or failing AI layer is a 200, not a
500.** BUILD_PLAN section 6 requires every AI feature to degrade to a clear message, and a
panel that returns a server error takes its page down with it. So `AiUnavailableError`
becomes `{available: false, reason: ...}` and the frontend renders the reason.

A refusal is also a 200. "I cannot answer that from these views" is a correct answer to a
question about salaries, not a client error.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai import narrative, nl_query
from app.ai.provider import AiUnavailableError, get_provider
from app.config import settings
from app.db import get_db
from app.metrics.filters import MetricFilters, metric_filters
from app.schemas import Envelope, envelope
from app.schemas.metrics import (
    AiStatus,
    AskResponse,
    ExampleQuestion,
    NarrativeSummary,
    RiskExplanationResponse,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])

Filters = Annotated[MetricFilters, Depends(metric_filters)]
Db = Annotated[Session, Depends(get_db)]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.get("/status", response_model=Envelope[AiStatus])
def status() -> Envelope[AiStatus]:
    """Whether the AI layer is usable, so the frontend can render honestly rather than
    firing requests that will fail."""
    provider = get_provider()
    reasoning, bulk = settings.resolved_models
    return envelope(
        AiStatus(
            available=provider is not None,
            provider=settings.resolved_ai_provider,
            reasoning_model=reasoning,
            bulk_model=bulk,
            reason=None
            if provider is not None
            else "No AI key configured. Set GOOGLE_API_KEY or ANTHROPIC_API_KEY.",
        )
    )


@router.get("/examples", response_model=Envelope[list[ExampleQuestion]])
def examples() -> Envelope[list[ExampleQuestion]]:
    """One-click questions, chosen to hit the planted scenarios."""
    return envelope([ExampleQuestion(**spec) for spec in nl_query.EXAMPLE_QUESTIONS])


@router.post("/ask", response_model=Envelope[AskResponse])
def ask(db: Db, request: AskRequest) -> Envelope[AskResponse]:
    """Answer a question in SQL, and return the SQL alongside the rows.

    POST rather than GET because the question is user input of arbitrary length and does not
    belong in a URL or a proxy's access log.
    """
    try:
        result = nl_query.ask(db, request.question)
    except AiUnavailableError as exc:
        return envelope(
            AskResponse(
                question=request.question,
                available=False,
                refused=True,
                refusal_reason=str(exc),
            ),
            row_count=0,
        )

    return envelope(
        AskResponse(
            question=result.question,
            available=True,
            refused=result.refused,
            sql=result.sql,
            explanation=result.explanation,
            refusal_reason=result.refusal_reason,
            columns=list(result.columns),
            rows=result.rows,
            truncated=result.truncated,
            tables=list(result.tables),
            model=result.model,
            cached=result.cached,
        ),
        row_count=result.row_count,
    )


@router.get("/narrative", response_model=Envelope[NarrativeSummary])
def summary(db: Db, filters: Filters) -> Envelope[NarrativeSummary]:
    """Three bullets over the current slice, cached so a repeat visit costs nothing."""
    try:
        result = narrative.executive_summary(db, filters)
    except AiUnavailableError as exc:
        return envelope(
            NarrativeSummary(available=False, reason=str(exc)),
            filters_applied=filters.as_dict(),
            row_count=0,
        )

    return envelope(
        NarrativeSummary(
            available=True,
            headline=result.headline,
            bullets=list(result.bullets),
            model=result.model,
            cached=result.cached,
            stale=result.stale,
            generated_at=result.generated_at,
        ),
        filters_applied=filters.as_dict(),
        row_count=len(result.bullets),
    )


@router.get(
    "/flight-risk/{employee_id}/explanation",
    response_model=Envelope[RiskExplanationResponse],
)
def risk_explanation(db: Db, employee_id: str) -> Envelope[RiskExplanationResponse]:
    """Plain-English reasoning for one score, expanded from its component weights."""
    try:
        result = narrative.explain_risk(db, employee_id)
    except AiUnavailableError as exc:
        return envelope(
            RiskExplanationResponse(employee_id=employee_id, available=False, reason=str(exc)),
            row_count=0,
        )

    if result is None:
        # Not a 404: "this person has no current risk score" is an answer, and the table
        # this is reached from can legitimately hold an id that scoring skipped.
        return envelope(
            RiskExplanationResponse(
                employee_id=employee_id,
                available=True,
                reason="No current flight-risk score for this employee.",
            ),
            row_count=0,
        )

    return envelope(
        RiskExplanationResponse(
            employee_id=result.employee_id,
            available=True,
            score=result.score,
            band=result.band,
            explanation=result.explanation,
            components=result.components,
            model=result.model,
            cached=result.cached,
        )
    )
