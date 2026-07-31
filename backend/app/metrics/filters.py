"""The one filter implementation, shared by every metric route.

CLAUDE.md requires the same optional filters on every metric endpoint —
`date_from`, `date_to`, `department_id`, `location_id`, `level`, `manager_id` —
"implemented once as a shared dependency, not per route".

The important design choice here is that **an unsupported filter raises rather than
being ignored**. Silently dropping a filter is the worst available behaviour: the
caller gets a 200 with data for a slice they did not ask for, and no way to tell. A
`manager_id` filter that changes nothing is a bug, not a coincidence. So a filter that
a view cannot honour produces a clear 400.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from fastapi import Query
from sqlalchemy import Table
from sqlalchemy.sql import Select

PeriodKind = Literal["date", "year"]


class UnsupportedFilterError(ValueError):
    """Raised when a caller filters on a dimension the target view does not carry.

    Mapped to HTTP 400 by the route layer.
    """

    def __init__(self, filter_name: str, view_name: str) -> None:
        super().__init__(
            f"'{filter_name}' is not available for this metric "
            f"(view '{view_name}' has no such dimension)"
        )
        self.filter_name = filter_name
        self.view_name = view_name


@dataclass(frozen=True)
class MetricFilters:
    """A slice request. Frozen so it cannot be mutated mid-request."""

    date_from: date | None = None
    date_to: date | None = None
    department_id: int | None = None
    location_id: int | None = None
    level: int | None = None
    manager_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """What goes into `meta.filters_applied`, with unset filters omitted.

        Echoing only what was actually applied means a client can tell the difference
        between "no department filter" and "department 3".
        """
        return {
            key: value
            for key, value in {
                "date_from": self.date_from.isoformat() if self.date_from else None,
                "date_to": self.date_to.isoformat() if self.date_to else None,
                "department_id": self.department_id,
                "location_id": self.location_id,
                "level": self.level,
                "manager_id": self.manager_id,
            }.items()
            if value is not None
        }


def metric_filters(
    date_from: date | None = Query(
        None, description="Inclusive lower bound on the metric's period column."
    ),
    date_to: date | None = Query(
        None, description="Inclusive upper bound on the metric's period column."
    ),
    department_id: int | None = Query(None, ge=1, description="dim_department.department_id"),
    location_id: int | None = Query(None, ge=1, description="dim_location.location_id"),
    level: int | None = Query(None, ge=1, le=6, description="dim_job_level.job_level_id"),
    manager_id: str | None = Query(
        None, max_length=12, description="dim_employee.employee_id of a manager, e.g. M-114"
    ),
) -> MetricFilters:
    """FastAPI dependency. Registered once, reused by every metric route."""
    return MetricFilters(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        location_id=location_id,
        level=level,
        manager_id=manager_id,
    )


#: Filter name -> the column that implements it. `level` is the odd one: the public
#: filter is called `level` but the column is `job_level_id`.
_DIMENSION_COLUMNS: dict[str, str] = {
    "department_id": "department_id",
    "location_id": "location_id",
    "level": "job_level_id",
    "manager_id": "manager_id",
}


def apply_filters(
    stmt: Select[Any],
    source: Table,
    filters: MetricFilters,
    *,
    period_column: str,
    period_kind: PeriodKind = "date",
) -> Select[Any]:
    """Apply the shared filters to a select over `source`.

    `period_column` is explicit because views name their period differently —
    `month_start`, `quarter_start`, `week_start`, `hire_quarter`, `year`. Guessing it
    would silently pick the wrong column on any view carrying more than one.
    """
    columns = source.c
    period = columns[period_column]

    if filters.date_from is not None:
        stmt = stmt.where(
            period >= (filters.date_from.year if period_kind == "year" else filters.date_from)
        )
    if filters.date_to is not None:
        stmt = stmt.where(
            period <= (filters.date_to.year if period_kind == "year" else filters.date_to)
        )

    for filter_name, column_name in _DIMENSION_COLUMNS.items():
        value = getattr(filters, filter_name)
        if value is None:
            continue
        if column_name not in columns:
            raise UnsupportedFilterError(filter_name, source.name)
        stmt = stmt.where(columns[column_name] == value)

    return stmt


#: Tenure bands, matching sql/views/11_v_tenure_band_monthly.sql. Duplicated in SQL and
#: Python by necessity; this ordering exists so the API can return bands in a sensible
#: order even when a band has no members and the view emits no row for it.
TENURE_BANDS: tuple[str, ...] = ("<6m", "6-12m", "1-2y", "2-5y", "5y+")
