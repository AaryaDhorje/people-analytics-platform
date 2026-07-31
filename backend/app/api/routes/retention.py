"""Retention endpoints.

Thin by design: parse filters via the shared dependency, call into `app/metrics/`, wrap
in the standard envelope. No computation happens in this file.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.metrics import retention
from app.metrics.filters import MetricFilters, metric_filters
from app.schemas import Envelope, envelope
from app.schemas.metrics import (
    AttritionPoint,
    AttritionTotal,
    CohortRetention,
    HeadcountPoint,
    ManagerAttrition,
    ManagerAttritionTrailing,
    Mobility,
    MobilityYear,
    RegrettedAttrition,
    SurvivalPoint,
    TenureBand,
)

router = APIRouter(prefix="/api/retention", tags=["retention"])

Filters = Annotated[MetricFilters, Depends(metric_filters)]
Db = Annotated[Session, Depends(get_db)]


@router.get("/headcount", response_model=Envelope[list[HeadcountPoint]])
def headcount(db: Db, filters: Filters) -> Envelope[list[HeadcountPoint]]:
    """Month-end headcount, with both activity endpoints and the average denominator."""
    data = retention.headcount_series(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/attrition", response_model=Envelope[list[AttritionPoint]])
def attrition(db: Db, filters: Filters) -> Envelope[list[AttritionPoint]]:
    """Annualized attrition per month, over average headcount."""
    data = retention.attrition_rate(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/attrition/total", response_model=Envelope[AttritionTotal])
def attrition_total(db: Db, filters: Filters) -> Envelope[AttritionTotal]:
    """One annualized figure for the filtered period, with the voluntary split."""
    data = retention.attrition_total(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/attrition/regretted", response_model=Envelope[RegrettedAttrition])
def regretted(db: Db, filters: Filters) -> Envelope[RegrettedAttrition]:
    """Voluntary exits rated 4+, over all voluntary exits."""
    data = retention.regretted_attrition(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/attrition/by-manager", response_model=Envelope[list[ManagerAttrition]])
def attrition_by_manager(
    db: Db,
    filters: Filters,
    min_reports: Annotated[
        int, Query(ge=1, le=100, description="Floor on AVERAGE team size, per docs/METRICS.md")
    ] = retention.MIN_REPORTS_FOR_MANAGER_ATTRITION,
) -> Envelope[list[ManagerAttrition]]:
    """Annualized attrition per manager per quarter, above an average-span floor."""
    data = retention.attrition_by_manager(db, filters, min_reports=min_reports)
    return envelope(data, filters_applied={**filters.as_dict(), "min_reports": min_reports})


@router.get(
    "/attrition/by-manager/trailing",
    response_model=Envelope[list[ManagerAttritionTrailing]],
)
def attrition_by_manager_trailing(
    db: Db,
    filters: Filters,
    months: Annotated[
        int, Query(ge=3, le=60, description="Length of the trailing window, in months")
    ] = retention.TRAILING_MONTHS_FOR_MANAGER_RANKING,
    min_reports: Annotated[
        int, Query(ge=1, le=100, description="Floor on AVERAGE team size over the window")
    ] = retention.MIN_REPORTS_FOR_MANAGER_ATTRITION,
) -> Envelope[list[ManagerAttritionTrailing]]:
    """Managers ranked worst-first over a trailing window, with a company baseline.

    `/attrition/by-manager` is the per-quarter series; this is the ranking. Ranking the
    quarterly rows instead puts a single bad three-month stretch above a team that has been
    losing people all year, because a quarter's denominator is small enough for one exit to
    move the rate double digits.
    """
    data = retention.attrition_by_manager_trailing(
        db, filters, months=months, min_reports=min_reports
    )
    return envelope(
        data,
        filters_applied={**filters.as_dict(), "months": months, "min_reports": min_reports},
    )


@router.get("/tenure", response_model=Envelope[list[TenureBand]])
def tenure(db: Db, filters: Filters) -> Envelope[list[TenureBand]]:
    """Point-in-time tenure distribution at the latest month in range."""
    data = retention.tenure_distribution(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/cohort-retention", response_model=Envelope[list[CohortRetention]])
def cohort_retention(
    db: Db,
    filters: Filters,
    months: Annotated[int, Query(ge=1, le=24, description="Milestone in months")] = 12,
) -> Envelope[list[CohortRetention]]:
    """Retention at a milestone by hire channel. Cohorts that have not reached the
    milestone are censored out rather than counted."""
    data = retention.cohort_retention(db, filters, months=months)
    return envelope(data, filters_applied={**filters.as_dict(), "months": months})


@router.get("/cohort-survival", response_model=Envelope[list[SurvivalPoint]])
def cohort_survival(db: Db, filters: Filters) -> Envelope[list[SurvivalPoint]]:
    """Survival at every month offset — the curve behind the tenure-cliff knee."""
    data = retention.cohort_survival_curve(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/mobility", response_model=Envelope[Mobility])
def mobility(db: Db, filters: Filters) -> Envelope[Mobility]:
    """(promotions + lateral transfers) / average headcount, annualized."""
    data = retention.internal_mobility(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/mobility/by-year", response_model=Envelope[list[MobilityYear]])
def mobility_by_year(db: Db, filters: Filters) -> Envelope[list[MobilityYear]]:
    data = retention.mobility_by_year(db, filters)
    return envelope(data, filters_applied=filters.as_dict())
