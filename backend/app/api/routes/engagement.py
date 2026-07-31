"""Engagement endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.metrics import engagement
from app.metrics.filters import MetricFilters, metric_filters
from app.schemas import Envelope, envelope
from app.schemas.metrics import (
    Absenteeism,
    CommentTheme,
    DriverDepartmentPoint,
    DriverPoint,
    EngagementIndex,
    Enps,
    EnpsPoint,
    Participation,
    QuartileAttrition,
)

router = APIRouter(prefix="/api/engagement", tags=["engagement"])

Filters = Annotated[MetricFilters, Depends(metric_filters)]
Db = Annotated[Session, Depends(get_db)]


@router.get("/enps", response_model=Envelope[Enps])
def enps(db: Db, filters: Filters) -> Envelope[Enps]:
    """Promoters minus detractors, on a -100..+100 scale. Negative is meaningful."""
    data = engagement.enps(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/enps/trend", response_model=Envelope[list[EnpsPoint]])
def enps_trend(db: Db, filters: Filters) -> Envelope[list[EnpsPoint]]:
    data = engagement.enps_trend(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/index", response_model=Envelope[EngagementIndex])
def index(db: Db, filters: Filters) -> Envelope[EngagementIndex]:
    """Mean of the five drivers, normalized to 0-100."""
    data = engagement.engagement_index(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/drivers", response_model=Envelope[dict[str, float | None]])
def drivers(db: Db, filters: Filters) -> Envelope[dict[str, float | None]]:
    """Mean score per driver: manager, growth, recognition, workload, belonging."""
    data = engagement.driver_breakdown(db, filters)
    return envelope(data, filters_applied=filters.as_dict(), row_count=len(data))


@router.get("/drivers/trend", response_model=Envelope[list[DriverPoint]])
def driver_trend(db: Db, filters: Filters) -> Envelope[list[DriverPoint]]:
    """Driver means per survey quarter — where the post-reorg dip shows."""
    data = engagement.driver_trend(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/drivers/by-department", response_model=Envelope[list[DriverDepartmentPoint]])
def drivers_by_department(db: Db, filters: Filters) -> Envelope[list[DriverDepartmentPoint]]:
    data = engagement.driver_breakdown_by_department(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/participation", response_model=Envelope[list[Participation]])
def participation(db: Db, filters: Filters) -> Envelope[list[Participation]]:
    """Responses over employees eligible at the month the survey closed."""
    data = engagement.participation(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/attrition-link", response_model=Envelope[list[QuartileAttrition]])
def attrition_link(db: Db, filters: Filters) -> Envelope[list[QuartileAttrition]]:
    """Attrition of each engagement quartile in the quarter AFTER the survey closed."""
    data = engagement.engagement_attrition_link(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/absenteeism", response_model=Envelope[Absenteeism])
def absenteeism(db: Db, filters: Filters) -> Envelope[Absenteeism]:
    """Unplanned absence days over available workdays (headcount x workdays)."""
    data = engagement.absenteeism(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/themes", response_model=Envelope[list[CommentTheme]])
def themes(
    db: Db,
    filters: Filters,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Envelope[list[CommentTheme]]:
    """Claude-extracted comment themes. Empty until phase 6 populates them — an empty
    list, not an error, so the page still renders."""
    data = engagement.comment_themes(db, filters, limit=limit)
    return envelope(data, filters_applied=filters.as_dict())
