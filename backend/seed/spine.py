"""The `dim_date` spine.

Deterministic and RNG-free: the same window always produces the same rows. Every
period-grain metric joins here instead of calling `date_trunc` inline, so "month"
and "quarter" mean exactly one thing across all 31 metrics.
"""

from datetime import date, timedelta

from seed.reference import WINDOW_END, WINDOW_START
from seed.util import month_end, month_start, quarter_start

#: Fixed holidays observed across all locations. A real deployment would vary these
#: by country; here they exist so `is_workday` is not simply "Mon-Fri", which would
#: make the absenteeism denominator subtly wrong in every month containing one.
HOLIDAYS: frozenset[date] = frozenset(
    {
        # 2023
        date(2023, 9, 4),
        date(2023, 11, 23),
        date(2023, 12, 25),
        date(2023, 12, 26),
        # 2024
        date(2024, 1, 1),
        date(2024, 3, 29),
        date(2024, 5, 27),
        date(2024, 7, 4),
        date(2024, 9, 2),
        date(2024, 11, 28),
        date(2024, 12, 25),
        date(2024, 12, 26),
        # 2025
        date(2025, 1, 1),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
        date(2025, 12, 26),
        # 2026
        date(2026, 1, 1),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 7, 3),
    }
)


def is_workday(day: date) -> bool:
    """Monday-Friday and not a holiday. Denominator for absenteeism."""
    return day.weekday() < 5 and day not in HOLIDAYS


def date_rows() -> list[dict[str, object]]:
    """One row per calendar day in the window."""
    rows: list[dict[str, object]] = []
    day = WINDOW_START
    index = 0
    while day <= WINDOW_END:
        first_of_month = month_start(day)
        last_of_month = month_end(day)
        rows.append(
            {
                "day": day,
                "year": day.year,
                "quarter": (day.month - 1) // 3 + 1,
                "month": day.month,
                "month_start": first_of_month,
                "month_end": last_of_month,
                "quarter_start": quarter_start(day),
                "week_start": day - timedelta(days=day.weekday()),
                "iso_week": day.isocalendar().week,
                "day_of_week": day.isoweekday(),
                "is_workday": is_workday(day),
                "is_month_end": day == last_of_month,
                "tenure_day_index": index,
            }
        )
        day += timedelta(days=1)
        index += 1
    return rows


def workdays_in_month(month_first: date) -> int:
    """Count of workdays in the month containing `month_first`."""
    last = month_end(month_first)
    day = month_start(month_first)
    count = 0
    while day <= last:
        if is_workday(day):
            count += 1
        day += timedelta(days=1)
    return count
