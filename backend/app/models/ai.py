"""Cache for model-generated responses.

Not a fact table and not part of the star schema. It is operational state: the AI features
read through it so a question asked twice costs one API call, and so a demo runs at the
speed of Postgres rather than the speed of a reasoning model.

Three reasons this is a table rather than an in-process dict:

- Render restarts the service on deploy and spins it down when idle, so an in-memory cache
  is empty exactly when the demo starts.
- The free-tier quota is the binding constraint. A cached row is the difference between a
  page that renders and a 429 on camera.
- A cached answer survives the provider being down, which is what makes "degrade to stale
  rather than error" possible at all.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AiCache(Base):
    __tablename__ = "ai_cache"
    __table_args__ = (
        Index("ix_ai_cache_feature", "feature"),
        {
            "comment": (
                "Read-through cache for AI responses, keyed by a hash of the feature, the "
                "model and the exact inputs. Safe to TRUNCATE: it rebuilds on demand."
            )
        },
    )

    #: sha256 of (feature, model, canonical JSON of the inputs). The model id is part of the
    #: key on purpose — switching provider or model must not serve an answer produced by the
    #: old one, because the two are not interchangeable and the response records which
    #: produced it.
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)

    feature: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="ask | narrative | risk_explanation | comments"
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, comment="The response body this key resolves to."
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: Bumped on every hit so the pre-warm script can report what the demo path actually
    #: touched, and so an unused entry is identifiable rather than assumed.
    hits: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
