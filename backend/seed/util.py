"""Date and numeric helpers for the generator.

Pure functions only — no RNG, no database. Everything here is exercised by
tests/test_seed_scenarios.py without a connection, because an off-by-one in
`months_between` would silently corrupt every tenure figure in the warehouse.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal


def dec(value: float | int | Decimal, places: int = 2) -> Decimal:
    """Round to a fixed number of places as Decimal.

    Numeric columns must never receive a raw float: binary floating point makes
    currency totals that fail to reconcile, and a metric off by a cent is
    indistinguishable from one that is wrong.
    """
    quantum = Decimal(1).scaleb(-places)
    return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(day: date, months: int) -> date:
    """Shift by whole months, clamping the day to the target month's length."""
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    # Clamp: 31 Jan + 1 month is 28/29 Feb, not an error.
    next_month_first = date(year + (month // 12), month % 12 + 1, 1)
    last_day_of_target = (next_month_first - timedelta(days=1)).day
    return date(year, month, min(day.day, last_day_of_target))


def month_end(day: date) -> date:
    return add_months(month_start(day), 1) - timedelta(days=1)


def months_between(earlier: date, later: date) -> int:
    """Whole months elapsed. Negative if `later` precedes `earlier`.

    "Whole" means the day-of-month must have been reached: 15 Jan to 14 Feb is 0
    months, 15 Jan to 15 Feb is 1. Tenure banding depends on this.
    """
    months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
    if later.day < earlier.day:
        months -= 1
    return months


def quarter_start(day: date) -> date:
    """Calendar quarter, matching dim_date.quarter_start."""
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def iter_months(start: date, end: date) -> list[date]:
    """Month-start dates from the month containing `start` through `end`."""
    months: list[date] = []
    cursor = month_start(start)
    while cursor <= end:
        months.append(cursor)
        cursor = add_months(cursor, 1)
    return months


def iter_weeks(start: date, end: date) -> list[date]:
    """Monday dates covering the range."""
    weeks: list[date] = []
    cursor = monday_of(start)
    while cursor <= end:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    return weeks


def iter_quarters(start: date, end: date) -> list[date]:
    quarters: list[date] = []
    cursor = quarter_start(start)
    while cursor <= end:
        quarters.append(cursor)
        cursor = add_months(cursor, 3)
    return quarters


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
