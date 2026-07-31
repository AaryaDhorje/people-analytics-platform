"""Productivity endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.metrics import productivity
from app.metrics.filters import MetricFilters, metric_filters
from app.schemas import Envelope, envelope
from app.schemas.metrics import (
    GoalAttainment,
    OutputPerHead,
    Overtime,
    OvertimeMonth,
    RevenuePerFte,
    SpanByLevel,
    SpanOfControl,
    Training,
    Utilization,
    UtilizationWeek,
)

router = APIRouter(prefix="/api/productivity", tags=["productivity"])

Filters = Annotated[MetricFilters, Depends(metric_filters)]
Db = Annotated[Session, Depends(get_db)]


@router.get("/utilization", response_model=Envelope[Utilization])
def utilization(db: Db, filters: Filters) -> Envelope[Utilization]:
    """Billable over available hours. Null where nobody files timesheets."""
    data = productivity.utilization(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/utilization/by-week", response_model=Envelope[list[UtilizationWeek]])
def utilization_by_week(db: Db, filters: Filters) -> Envelope[list[UtilizationWeek]]:
    """Weekly utilization per team, for the heatmap."""
    data = productivity.utilization_by_week(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/overtime", response_model=Envelope[Overtime])
def overtime(db: Db, filters: Filters) -> Envelope[Overtime]:
    """Hours over 40 per week, over total hours. The threshold is applied per week."""
    data = productivity.overtime(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/overtime/trend", response_model=Envelope[list[OvertimeMonth]])
def overtime_trend(db: Db, filters: Filters) -> Envelope[list[OvertimeMonth]]:
    """Overtime per team per month. The 40-hour threshold was applied per week before
    any of this was summed."""
    data = productivity.overtime_by_month(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/output", response_model=Envelope[OutputPerHead])
def output(db: Db, filters: Filters) -> Envelope[OutputPerHead]:
    """Output units per FTE-week."""
    data = productivity.output_per_head(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/revenue-per-fte", response_model=Envelope[list[RevenuePerFte]])
def revenue_per_fte(db: Db, filters: Filters) -> Envelope[list[RevenuePerFte]]:
    """Revenue over average FTE, by department and quarter."""
    data = productivity.revenue_per_fte(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/span-of-control", response_model=Envelope[SpanOfControl])
def span_of_control(db: Db, filters: Filters) -> Envelope[SpanOfControl]:
    """Average direct reports per manager, counting only managers who have reports."""
    data = productivity.span_of_control(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/span-of-control/by-level", response_model=Envelope[list[SpanByLevel]])
def span_of_control_by_level(db: Db, filters: Filters) -> Envelope[list[SpanByLevel]]:
    """Span grained by the manager's own department and level — not the reports' level,
    which would split one manager across several rows."""
    data = productivity.span_of_control_by_level(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/goal-attainment", response_model=Envelope[GoalAttainment])
def goal_attainment(db: Db, filters: Filters) -> Envelope[GoalAttainment]:
    """Mean attainment with each goal capped at 1.5 before averaging."""
    data = productivity.goal_attainment(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/training", response_model=Envelope[Training])
def training(db: Db, filters: Filters) -> Envelope[Training]:
    """Training hours per average head, plus completion rate."""
    data = productivity.training(db, filters)
    return envelope(data, filters_applied=filters.as_dict())
