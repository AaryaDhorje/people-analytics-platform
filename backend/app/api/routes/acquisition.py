"""Talent acquisition endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.metrics import acquisition
from app.metrics.filters import MetricFilters, metric_filters
from app.schemas import Envelope, envelope
from app.schemas.metrics import (
    CostPerHire,
    FunnelStage,
    OfferAcceptance,
    QualityOfHire,
    RequisitionAging,
    SourceEffectiveness,
    SourceRetention,
    TimeToFill,
    TimeToHire,
)

router = APIRouter(prefix="/api/acquisition", tags=["acquisition"])

Filters = Annotated[MetricFilters, Depends(metric_filters)]
Db = Annotated[Session, Depends(get_db)]


@router.get("/time-to-fill", response_model=Envelope[TimeToFill])
def time_to_fill(db: Db, filters: Filters) -> Envelope[TimeToFill]:
    """Days from requisition open to offer accepted."""
    data = acquisition.time_to_fill(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/time-to-hire", response_model=Envelope[TimeToHire])
def time_to_hire(db: Db, filters: Filters) -> Envelope[TimeToHire]:
    """Days from first application to offer accepted — a different question from
    time to fill, and measured from a different starting point."""
    data = acquisition.time_to_hire(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/funnel", response_model=Envelope[list[FunnelStage]])
def funnel(db: Db, filters: Filters) -> Envelope[list[FunnelStage]]:
    """Applied -> Screen -> Interview -> Offer -> Hired, with conversion and dwell."""
    data = acquisition.funnel(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/offer-acceptance", response_model=Envelope[OfferAcceptance])
def offer_acceptance(db: Db, filters: Filters) -> Envelope[OfferAcceptance]:
    data = acquisition.offer_acceptance(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/cost-per-hire", response_model=Envelope[list[CostPerHire]])
def cost_per_hire(db: Db, filters: Filters) -> Envelope[list[CostPerHire]]:
    """Cost per hire by department and quarter. Null where spend exists but no hire has
    landed yet — zero would claim hiring was free."""
    data = acquisition.cost_per_hire(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/requisition-aging", response_model=Envelope[list[RequisitionAging]])
def requisition_aging(db: Db, filters: Filters) -> Envelope[list[RequisitionAging]]:
    """Open requisitions and how many are past the 60-day line."""
    data = acquisition.requisition_aging(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/source-effectiveness", response_model=Envelope[list[SourceEffectiveness]])
def source_effectiveness(db: Db, filters: Filters) -> Envelope[list[SourceEffectiveness]]:
    """Hires per application by channel — the conversion half of the metric."""
    data = acquisition.source_effectiveness(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/source-retention", response_model=Envelope[list[SourceRetention]])
def source_retention(db: Db, filters: Filters) -> Envelope[list[SourceRetention]]:
    """90- and 180-day retention of hires by channel — the retention half. Employee-level,
    where conversion is application-level."""
    data = acquisition.source_retention(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/quality-of-hire", response_model=Envelope[list[QualityOfHire]])
def quality_of_hire(db: Db, filters: Filters) -> Envelope[list[QualityOfHire]]:
    """Still employed at day 180 AND rated 3 or better."""
    data = acquisition.quality_of_hire(db, filters)
    return envelope(data, filters_applied=filters.as_dict())
