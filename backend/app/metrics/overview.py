"""The landing-page overview: eight headline KPIs in a single request.

One call rather than eight, because the Overview page is the first thing a cold Render
instance serves and eight parallel round-trips on a waking dyno is the worst possible
first impression.

Three things every card needs and one it must not get wrong:

- **value** for the current period
- **previous** for the immediately preceding period of equal length
- **sparkline** over a longer trailing window
- **`higher_is_better`**, because a green up-arrow on rising attrition is worse than no
  arrow at all. Some KPIs are genuinely directionless, and those say so with `None`
  rather than guessing.

Periods are resolved from the data, not from the wall clock. The warehouse is a fixed
window; using `today` would make every KPI read as empty the moment the demo is run on a
later date than the data covers.
"""

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.metrics import acquisition, engagement, productivity, retention
from app.metrics.filters import MetricFilters
from app.metrics.tables import v_headcount_monthly
from app.models import FactFlightRiskScore
from app.models.enums import RiskBand
from seed.util import add_months, month_start

#: How many months the default current period spans when the caller gives no dates.
DEFAULT_PERIOD_MONTHS = 3
#: How far back the sparklines reach.
SPARKLINE_MONTHS = 12


@dataclass(frozen=True)
class Kpi:
    key: str
    label: str
    value: float | None
    previous: float | None
    delta: float | None
    delta_pct: float | None
    unit: str
    higher_is_better: bool | None
    sparkline: list[float | None]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _kpi(
    key: str,
    label: str,
    value: float | None,
    previous: float | None,
    *,
    unit: str,
    higher_is_better: bool | None,
    sparkline: list[float | None] | None = None,
) -> dict[str, Any]:
    delta = None if value is None or previous is None else value - previous
    delta_pct = None if delta is None or not previous else delta / abs(previous)
    return Kpi(
        key=key,
        label=label,
        value=value,
        previous=previous,
        delta=delta,
        delta_pct=delta_pct,
        unit=unit,
        higher_is_better=higher_is_better,
        sparkline=sparkline or [],
    ).as_dict()


def latest_month(db: Session) -> date | None:
    """The most recent month with data. Anchors every period to the warehouse rather
    than to the clock."""
    return db.execute(select(func.max(v_headcount_monthly.c.month_start))).scalar()


def resolve_periods(
    db: Session, filters: MetricFilters
) -> tuple[MetricFilters, MetricFilters, MetricFilters]:
    """(current, previous, sparkline) filter windows.

    An explicit date range is honoured, and the previous period is the equal-length
    window immediately before it — so a quarter compares against the quarter before,
    not against an arbitrary fixed span.
    """
    anchor = latest_month(db) or date.today()

    if filters.date_from and filters.date_to:
        start = month_start(filters.date_from)
        end = month_start(filters.date_to)
        months = max(1, (end.year - start.year) * 12 + (end.month - start.month) + 1)
    else:
        months = DEFAULT_PERIOD_MONTHS
        end = anchor
        start = add_months(anchor, -(months - 1))

    previous_end = add_months(start, -1)
    previous_start = add_months(previous_end, -(months - 1))
    sparkline_start = add_months(end, -(SPARKLINE_MONTHS - 1))

    def window(from_month: date, to_month: date) -> MetricFilters:
        return MetricFilters(
            date_from=from_month,
            date_to=to_month,
            department_id=filters.department_id,
            location_id=filters.location_id,
            level=filters.level,
            manager_id=filters.manager_id,
        )

    return (
        window(start, end),
        window(previous_start, previous_end),
        window(sparkline_start, end),
    )


def _series(rows: list[dict[str, Any]], key: str) -> list[float | None]:
    return [None if row.get(key) is None else float(row[key]) for row in rows]


def _last(rows: list[dict[str, Any]], key: str) -> float | None:
    for row in reversed(rows):
        if row.get(key) is not None:
            return float(row[key])
    return None


def _last_two(rows: list[dict[str, Any]], key: str) -> tuple[float | None, float | None]:
    """The two most recent non-null observations, latest first.

    Used for **quarterly** metrics. A three-month current window frequently contains no
    survey at all — the default window ended 2026-07 while the last survey sat in the
    quarter beginning 2026-04 — so a window-based lookup rendered the eNPS card blank on
    the landing page. For a periodic metric the honest card is "latest reading against
    the one before it", not "readings inside an arbitrary window".
    """
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    if not values:
        return None, None
    if len(values) == 1:
        return values[-1], None
    return values[-1], values[-2]


def build_overview(db: Session, filters: MetricFilters) -> dict[str, Any]:
    """Eight KPIs spanning all four domains, weighted toward Retention.

    Retention gets four of the eight deliberately — it is the domain HR leaders buy, and
    the plan's own cut line says depth there beats coverage everywhere.
    """
    current, previous, spark = resolve_periods(db, filters)
    kpis: list[dict[str, Any]] = []

    # --- Retention ----------------------------------------------------------
    headcount_now = retention.headcount_series(db, current)
    headcount_prev = retention.headcount_series(db, previous)
    headcount_spark = retention.headcount_series(db, spark)
    kpis.append(
        _kpi(
            "headcount",
            "Headcount",
            _last(headcount_now, "headcount"),
            _last(headcount_prev, "headcount"),
            unit="people",
            higher_is_better=None,  # growth is neither good nor bad without context
            sparkline=_series(headcount_spark, "headcount"),
        )
    )

    attrition_now = retention.attrition_total(db, current)
    attrition_prev = retention.attrition_total(db, previous)
    kpis.append(
        _kpi(
            "attrition_rate",
            "Attrition (annualized)",
            attrition_now["annualized_rate"],
            attrition_prev["annualized_rate"],
            unit="rate",
            higher_is_better=False,
            sparkline=_series(retention.attrition_rate(db, spark), "annualized_rate"),
        )
    )

    regretted_now = retention.regretted_attrition(db, current)
    regretted_prev = retention.regretted_attrition(db, previous)
    kpis.append(
        _kpi(
            "regretted_attrition",
            "Regretted attrition",
            regretted_now["regretted_share"],
            regretted_prev["regretted_share"],
            unit="rate",
            higher_is_better=False,
            sparkline=_series(retention.regretted_attrition_trend(db, spark), "regretted_share"),
        )
    )

    # Flight risk is scored for one month only, so it has no history to plot. An empty
    # sparkline is honest; a flat line would imply the number has been stable.
    high_risk = db.execute(
        select(func.count())
        .select_from(FactFlightRiskScore)
        .where(FactFlightRiskScore.band == RiskBand.HIGH)
    ).scalar()
    kpis.append(
        _kpi(
            "high_flight_risk",
            "High flight risk",
            float(high_risk or 0),
            None,
            unit="people",
            higher_is_better=False,
        )
    )

    # --- Acquisition --------------------------------------------------------
    kpis.append(
        _kpi(
            "time_to_fill",
            "Time to fill",
            acquisition.time_to_fill(db, current)["mean_days"],
            acquisition.time_to_fill(db, previous)["mean_days"],
            unit="days",
            higher_is_better=False,
            sparkline=_series(acquisition.time_to_fill_by_month(db, spark), "mean_days"),
        )
    )

    kpis.append(
        _kpi(
            "offer_acceptance",
            "Offer acceptance",
            acquisition.offer_acceptance(db, current)["acceptance_rate"],
            acquisition.offer_acceptance(db, previous)["acceptance_rate"],
            unit="rate",
            higher_is_better=True,
            sparkline=_series(acquisition.offer_acceptance_by_month(db, spark), "acceptance_rate"),
        )
    )

    # --- Engagement ---------------------------------------------------------
    # Quarterly cadence, so this is latest reading versus the one before it rather than
    # window versus window. A three-month current window routinely contains no survey at
    # all — the default window ran to 2026-07 while the last survey sat in the quarter
    # beginning 2026-04 — which rendered the eNPS card blank on the landing page.
    enps_trend = engagement.enps_trend(db, spark)
    enps_now, enps_prev = _last_two(enps_trend, "enps")
    kpis.append(
        _kpi(
            "enps",
            "eNPS",
            enps_now,
            enps_prev,
            unit="score",
            higher_is_better=True,
            sparkline=_series(enps_trend, "enps"),
        )
    )

    # --- Productivity -------------------------------------------------------
    # Also quarterly, and revenue arrives per (department, quarter) — so rows are
    # collapsed to one weighted figure per quarter before anything is plotted. Plotting
    # the raw rows gave 20 sparkline points for 4 quarters, silently interleaving
    # departments into what looks like a time series.
    revenue_by_quarter = _revenue_series(productivity.revenue_per_fte(db, spark))
    revenue_now, revenue_prev = _last_two(revenue_by_quarter, "revenue_per_fte")
    kpis.append(
        _kpi(
            "revenue_per_fte",
            "Revenue per FTE",
            revenue_now,
            revenue_prev,
            unit="currency",
            higher_is_better=True,
            sparkline=_series(revenue_by_quarter, "revenue_per_fte"),
        )
    )

    return {
        "as_of": current.date_to,
        "period_from": current.date_from,
        "period_to": current.date_to,
        "comparison_from": previous.date_from,
        "comparison_to": previous.date_to,
        "kpis": kpis,
    }


def _revenue_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse per-(department, quarter) revenue rows into one figure per quarter."""
    by_quarter: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        by_quarter.setdefault(row["period"], []).append(row)
    return [
        {"period": period, "revenue_per_fte": _weighted_revenue_per_fte(group)}
        for period, group in sorted(by_quarter.items())
    ]


def _weighted_revenue_per_fte(rows: list[dict[str, Any]]) -> float | None:
    """Total revenue over total FTE, not the mean of per-department ratios.

    Averaging the ratios would weight an 8-person department the same as a 340-person
    one, which is the same class of error as averaging a pre-averaged column.
    """
    revenue = sum(float(row["revenue_amount"] or 0) for row in rows)
    fte_months = sum(float(row["fte_months"] or 0) for row in rows)
    months = max((int(row["months_observed"] or 0) for row in rows), default=0)
    if not fte_months or not months:
        return None
    return revenue / (fte_months / months)


__all__ = ["DEFAULT_PERIOD_MONTHS", "SPARKLINE_MONTHS", "Kpi", "build_overview", "resolve_periods"]
