"""FastAPI application entrypoint.

Routes are thin and live in app/api/routes/. Metric logic lives in app/metrics/.
Nothing in this file computes anything.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import (
    acquisition,
    engagement,
    flight_risk,
    health,
    productivity,
    retention,
)
from app.config import settings
from app.metrics.filters import UnsupportedFilterError

app = FastAPI(
    title="People Analytics API",
    version=__version__,
    description=(
        "Metric services over a synthetic HR warehouse: talent acquisition, "
        "retention, engagement, and productivity. All data is synthetic."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(UnsupportedFilterError)
def unsupported_filter(_: Request, exc: UnsupportedFilterError) -> JSONResponse:
    """400, not 500, and never a silent pass.

    A filter a view cannot honour is a client error with a fixable cause. The alternative —
    ignoring it — returns 200 with data for a slice nobody asked for, which is the worst
    outcome available because nothing on screen indicates it happened.
    """
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "filter": exc.filter_name,
            "metric_source": exc.view_name,
        },
    )


app.include_router(health.router)
app.include_router(retention.router)
app.include_router(acquisition.router)
app.include_router(engagement.router)
app.include_router(productivity.router)
app.include_router(flight_risk.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    """Point casual visitors at the docs rather than returning a bare 404."""
    return {"service": "people-analytics-api", "docs": "/docs", "health": "/health"}
