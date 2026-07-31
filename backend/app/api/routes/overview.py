"""The landing-page overview endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.metrics import overview
from app.metrics.filters import MetricFilters, metric_filters
from app.schemas import Envelope, envelope
from app.schemas.metrics import Overview

router = APIRouter(prefix="/api", tags=["overview"])

Filters = Annotated[MetricFilters, Depends(metric_filters)]
Db = Annotated[Session, Depends(get_db)]


@router.get("/overview", response_model=Envelope[Overview])
def get_overview(db: Db, filters: Filters) -> Envelope[Overview]:
    """Eight headline KPIs in one call, each with a period-over-period delta.

    One request rather than eight: this is the first thing a cold Render instance serves,
    and eight parallel round-trips on a waking dyno is the worst available first
    impression.

    Periods come from the data's own latest month, not from the wall clock. Anchoring to
    `today` would make every card read empty the moment the demo runs on a date beyond
    the window the warehouse covers.
    """
    data = overview.build_overview(db, filters)
    return envelope(
        data,
        filters_applied=filters.as_dict(),
        row_count=len(data["kpis"]),
    )
