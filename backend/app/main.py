"""FastAPI application entrypoint.

Routes are thin and live in app/api/routes/. Metric logic lives in app/metrics/.
Nothing in this file computes anything.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import health
from app.config import settings

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

app.include_router(health.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    """Point casual visitors at the docs rather than returning a bare 404."""
    return {"service": "people-analytics-api", "docs": "/docs", "health": "/health"}
