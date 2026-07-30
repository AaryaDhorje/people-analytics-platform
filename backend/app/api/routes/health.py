"""Liveness and readiness endpoints.

`/health` must never touch the database: it is what Render polls, and it is what
the frontend uses to show whether the API is reachable. Database reachability is
a separate, explicitly-requested check at `/health/db`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.db import get_db
from app.schemas import Envelope, HealthPayload, envelope

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Envelope[HealthPayload])
def health() -> Envelope[HealthPayload]:
    """Liveness. No database, no auth — safe to poll on a cold start."""
    return envelope(
        HealthPayload(status="ok", env=settings.env, version=__version__),
    )


@router.get("/health/db", response_model=Envelope[HealthPayload])
def health_db(db: Session = Depends(get_db)) -> Envelope[HealthPayload]:
    """Readiness. Returns 503 with a readable message if Postgres is unreachable."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"database unreachable: {type(exc).__name__}",
        ) from exc
    return envelope(
        HealthPayload(status="ok", env=settings.env, version=__version__),
    )
