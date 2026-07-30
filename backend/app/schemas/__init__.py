"""Pydantic response models.

Every endpoint in this application returns the same envelope:

    {"data": ..., "meta": {"as_of": ..., "filters_applied": ..., "row_count": ...}}

`data` carries raw numbers. Percentages, currency, and rounding are the
frontend's responsibility.
"""

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    """Provenance for a response: when it was computed and over what slice."""

    as_of: datetime = Field(description="UTC timestamp at which the response was computed")
    filters_applied: dict[str, Any] = Field(
        default_factory=dict,
        description="Echo of the filters that shaped this result, with defaults resolved",
    )
    row_count: int = Field(description="Number of rows in `data`, or 1 for a scalar payload")


class Envelope(BaseModel, Generic[T]):
    """The single response shape for the entire API."""

    data: T
    meta: Meta


def envelope(
    data: T,
    *,
    filters_applied: dict[str, Any] | None = None,
    row_count: int | None = None,
) -> Envelope[T]:
    """Wrap a payload in the standard envelope.

    `row_count` defaults to `len(data)` for sequences and 1 for anything else, so
    callers only pass it when the natural count is misleading.
    """
    if row_count is None:
        row_count = len(data) if isinstance(data, list | tuple) else 1
    return Envelope[T](
        data=data,
        meta=Meta(
            as_of=datetime.now(UTC),
            filters_applied=filters_applied or {},
            row_count=row_count,
        ),
    )


class HealthPayload(BaseModel):
    """Liveness payload. Deliberately does not touch the database."""

    status: str
    env: str
    version: str
