"""Read-through cache for AI responses.

Every AI feature goes through `get_or_call`. BUILD_PLAN section 6 requires it ("cache all
AI responses"), and on a free-tier key it is the difference between a demo that renders and
a 429 on camera.

**The key includes the model id.** Switching provider or model must miss rather than serve
an answer the other one produced: the two are not interchangeable, and the response records
which model wrote it. Changing `MODEL_REASONING` therefore invalidates exactly the entries
that are now wrong, and nothing else.

**A stale hit beats an error.** If the provider fails on a miss and an entry exists for the
same feature and inputs under a *different* model, that entry is served with `stale: true`
rather than raising. The alternative during a demo is a blank panel, and the alternative in
production is an outage taking a page down over a summary.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import AiUnavailableError
from app.models.ai import AiCache

log = logging.getLogger(__name__)


def cache_key(feature: str, model: str, inputs: dict[str, Any]) -> str:
    """Stable hash of what was asked and who was asked.

    `sort_keys` matters more than it looks: without it two dicts differing only in insertion
    order hash differently, and a cache that misses every time is just a table.
    """
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{feature}\x00{model}\x00{canonical}".encode()).hexdigest()


def _fingerprint(feature: str, inputs: dict[str, Any]) -> str:
    """Model-independent hash, used only to find a stale entry to fall back to."""
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{feature}\x00{canonical}".encode()).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class Cached:
    """A payload plus how it was obtained, so the UI can be honest about it."""

    payload: dict[str, Any]
    cached: bool
    generated_at: datetime
    model: str
    #: True when the provider failed and an entry from a different model was served.
    stale: bool = False


def get_or_call(
    db: Session,
    *,
    feature: str,
    model: str,
    inputs: dict[str, Any],
    call: Callable[[], dict[str, Any]],
) -> Cached:
    """Return the cached payload for these inputs, or produce and store one.

    `call` is a zero-argument closure rather than a provider handle so this module stays
    unaware of how an answer is generated — which is what lets the tests drive it with a
    counter instead of a network.
    """
    key = cache_key(feature, model, inputs)
    fingerprint = _fingerprint(feature, inputs)

    row = db.get(AiCache, key)
    if row is not None:
        # Counting hits is what lets the pre-warm script report which entries the demo path
        # actually touched, rather than assuming.
        row.hits += 1
        db.commit()
        return Cached(
            payload=dict(row.payload),
            cached=True,
            generated_at=row.created_at,
            model=row.model,
        )

    try:
        payload = call()
    except AiUnavailableError:
        fallback = _stale_entry(db, feature, fingerprint)
        if fallback is None:
            raise
        log.warning("AI provider failed; serving a stale %s entry from %s", feature, fallback.model)
        return Cached(
            payload=dict(fallback.payload),
            cached=True,
            generated_at=fallback.created_at,
            model=fallback.model,
            stale=True,
        )

    row = AiCache(
        cache_key=key,
        feature=feature,
        model=model,
        payload={**payload, "_fingerprint": fingerprint},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return Cached(payload=dict(row.payload), cached=False, generated_at=row.created_at, model=model)


def _stale_entry(db: Session, feature: str, fingerprint: str) -> AiCache | None:
    """The most recent entry for the same question under any model."""
    stmt = (
        select(AiCache)
        .where(
            AiCache.feature == feature,
            AiCache.payload["_fingerprint"].astext == fingerprint,
        )
        .order_by(AiCache.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def invalidate(db: Session, *, feature: str | None = None) -> int:
    """Drop cached entries, optionally for one feature. Returns how many went.

    Used by the pre-warm script's `--force` and by anyone who changes a prompt: a prompt
    edit does not change the cache key, so without this the old answer survives the change
    that was meant to improve it.
    """
    stmt = select(AiCache)
    if feature is not None:
        stmt = stmt.where(AiCache.feature == feature)
    rows = db.execute(stmt).scalars().all()
    for row in rows:
        db.delete(row)
    db.commit()
    return len(rows)
