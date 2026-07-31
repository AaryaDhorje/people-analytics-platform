"""Flight risk endpoints.

Reads persisted scores rather than recomputing per request. Scoring 1,200 people on every
page load would be slow for no benefit, and — more importantly — the numbers on screen
must be the same ones phase 6's narrative was generated from. A score that changes between
the table and the explanation of it is worse than a stale one.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.metrics import flight_risk
from app.metrics.filters import MetricFilters, metric_filters
from app.models.enums import RiskBand
from app.schemas import Envelope, envelope
from app.schemas.metrics import FlightRisk, RiskBandCount

router = APIRouter(prefix="/api/flight-risk", tags=["flight-risk"])

Filters = Annotated[MetricFilters, Depends(metric_filters)]
Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=Envelope[list[FlightRisk]])
def top_risks(
    db: Db,
    filters: Filters,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    band: Annotated[RiskBand | None, Query(description="Filter to a single risk band")] = None,
) -> Envelope[list[FlightRisk]]:
    """Highest scores first, each carrying its per-component breakdown.

    `components` holds every factor's raw score, weight and contribution — that is what
    drives the expandable reason table, and what makes the number defensible out loud.

    Honours the shared filter set. `manager_id` is the interesting one: it turns "who is
    at risk" into "who is at risk on this manager's team", which is how the heatmap and
    the risk table get connected on camera.
    """
    data = flight_risk.top_risks(db, filters, limit=limit, band=band)
    applied: dict[str, object] = {**filters.as_dict(), "limit": limit}
    if band is not None:
        applied["band"] = band.value
    return envelope(data, filters_applied=applied)


@router.get("/bands", response_model=Envelope[list[RiskBandCount]])
def bands(db: Db, filters: Filters) -> Envelope[list[RiskBandCount]]:
    """Population per risk band, for the KPI row."""
    data = flight_risk.band_summary(db, filters)
    return envelope(data, filters_applied=filters.as_dict())


@router.get("/weights", response_model=Envelope[dict[str, float]])
def weights() -> Envelope[dict[str, float]]:
    """The component weights, exposed so the scoring is auditable from the API itself
    rather than only from the source."""
    return envelope(flight_risk.WEIGHTS, row_count=len(flight_risk.WEIGHTS))
