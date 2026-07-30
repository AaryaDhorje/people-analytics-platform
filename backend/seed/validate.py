"""Validation report and per-scenario assertions.

Two jobs. The report is the five sections BUILD_PLAN §6 asks for, printed for human
review. The assertions are what make "all six planted scenarios must be verifiably
present" a checked claim: each `Target` in scenarios.py is recomputed from the
database and judged against its tolerance.

Every recomputation here is written independently of the generator — from the metric
definitions in docs/METRICS.md, in raw SQL. Reusing generator helpers would only
confirm the generator agrees with itself.

    python -m seed.validate
    python -m seed.validate --checksum
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from seed import scenarios as sc
from seed.reference import WINDOW_END, WINDOW_START
from seed.scenarios import SCENARIOS, Target
from seed.util import add_months

REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "SEED_VALIDATION.md"

#: Company-wide annualized attrition, expressed so it reads the same everywhere:
#: exits * 12 / (sum of each month's average headcount).
_ATTRITION_SQL = """
SELECT SUM(terminated_in_month::int) AS exits,
       SUM((active_at_month_start::int + active_at_month_end::int) / 2.0) AS headcount_months
FROM fact_monthly_headcount_snapshot
WHERE month_start >= :from_month AND month_start <= :to_month
"""


def q(session: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    rows = session.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def one(session: Session, sql: str, **params: Any) -> dict[str, Any]:
    rows = q(session, sql, **params)
    return rows[0] if rows else {}


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(out)


def _num(value: Any, places: int = 1) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.{places}f}"


def _annualized(exits: float | None, headcount_months: float | None) -> float | None:
    if not exits or not headcount_months:
        return None
    return float(exits) * 12.0 / float(headcount_months)


# --- Report sections --------------------------------------------------------


def section_headcount(session: Session) -> str:
    rows = q(
        session,
        """
        SELECT month_start,
               SUM(active_at_month_start::int) AS at_start,
               SUM(active_at_month_end::int)   AS at_end,
               SUM(hired_in_month::int)        AS hires,
               SUM(terminated_in_month::int)   AS exits
        FROM fact_monthly_headcount_snapshot
        GROUP BY month_start ORDER BY month_start
        """,
    )
    body = [
        (
            r["month_start"],
            r["at_start"],
            r["at_end"],
            _num((r["at_start"] + r["at_end"]) / 2.0, 1),
            r["hires"],
            r["exits"],
        )
        for r in rows
    ]
    return (
        "### 1. Headcount by month\n\n"
        "`avg` is the average-headcount denominator every rate metric divides by.\n\n"
        + _table(["month", "at start", "at end", "avg", "hires", "exits"], body)
    )


def section_attrition_by_department(session: Session) -> str:
    rows = q(
        session,
        """
        WITH monthly AS (
          SELECT dep.code AS dept, s.month_start,
                 SUM(s.terminated_in_month::int) AS exits,
                 SUM((s.active_at_month_start::int + s.active_at_month_end::int) / 2.0) AS avg_hc
          FROM fact_monthly_headcount_snapshot s
          JOIN dim_department dep ON dep.department_id = s.department_id
          GROUP BY dep.code, s.month_start
        )
        SELECT dept,
               date_trunc('quarter', month_start)::date AS quarter_start,
               SUM(exits)  AS exits,
               SUM(avg_hc) AS headcount_months
        FROM monthly
        GROUP BY dept, quarter_start
        ORDER BY dept, quarter_start
        """,
    )
    body = [
        (
            r["dept"],
            r["quarter_start"],
            r["exits"],
            _num(float(r["headcount_months"]) / 3.0, 1),
            _num((_annualized(r["exits"], r["headcount_months"]) or 0) * 100, 1) + "%",
        )
        for r in rows
    ]
    return (
        "### 2. Attrition rate by department by quarter (annualized)\n\n"
        "Denominator is average headcount, never end-of-period.\n\n"
        + _table(["dept", "quarter", "exits", "avg headcount", "annualized"], body)
    )


def section_funnel(session: Session) -> str:
    rows = q(
        session,
        """
        SELECT se.stage::text AS stage, COUNT(DISTINCT se.application_id) AS applications
        FROM fact_application_stage_event se
        GROUP BY se.stage
        """,
    )
    order = ["applied", "screen", "interview", "offer", "hired"]
    counts = {r["stage"]: r["applications"] for r in rows}
    body = []
    previous: int | None = None
    for stage in order:
        current = counts.get(stage, 0)
        conversion = "-" if previous in (None, 0) else f"{current / previous * 100:.1f}%"
        body.append((stage, f"{current:,}", conversion))
        previous = current
    return (
        "### 3. Funnel counts by stage\n\n"
        "Conversion is stage_n / stage_n-1, per docs/METRICS.md.\n\n"
        + _table(["stage", "applications", "conversion"], body)
    )


def section_drivers(session: Session) -> str:
    """Driver means by as-of department, normalized back to 0-100."""
    rows = q(
        session,
        """
        SELECT dep.code AS dept, sv.quarter_start,
               AVG((r.driver_manager     - 1) / 4.0 * 100) AS manager,
               AVG((r.driver_growth      - 1) / 4.0 * 100) AS growth,
               AVG((r.driver_recognition - 1) / 4.0 * 100) AS recognition,
               AVG((r.driver_workload    - 1) / 4.0 * 100) AS workload,
               AVG((r.driver_belonging   - 1) / 4.0 * 100) AS belonging,
               COUNT(*) AS responses
        FROM fact_survey_response r
        JOIN dim_survey sv ON sv.survey_id = r.survey_id
        JOIN fact_monthly_headcount_snapshot s
          ON s.employee_id = r.employee_id
         AND s.month_start = date_trunc('month', r.submitted_on)::date
        JOIN dim_department dep ON dep.department_id = s.department_id
        GROUP BY dep.code, sv.quarter_start
        ORDER BY dep.code, sv.quarter_start
        """,
    )
    body = [
        (
            r["dept"],
            r["quarter_start"],
            r["responses"],
            _num(r["manager"]),
            _num(r["growth"]),
            _num(r["recognition"]),
            _num(r["workload"]),
            _num(r["belonging"]),
        )
        for r in rows
    ]
    return (
        "### 4. Engagement driver means by department by quarter (0-100)\n\n"
        "Stored raw 1-5; normalized here exactly as the views will.\n\n"
        + _table(
            ["dept", "quarter", "n", "manager", "growth", "recognition", "workload", "belonging"],
            body,
        )
    )


def section_overtime(session: Session) -> str:
    rows = q(
        session,
        """
        SELECT dep.code AS dept,
               date_trunc('month', t.week_start)::date AS month,
               SUM(GREATEST(t.billable_hours + t.non_billable_hours - 40, 0))
                 / NULLIF(SUM(t.billable_hours + t.non_billable_hours), 0) AS overtime_rate,
               SUM(t.billable_hours) / NULLIF(SUM(t.available_hours), 0)   AS utilization
        FROM fact_timesheet_week t
        JOIN dim_department dep ON dep.department_id = t.department_id
        GROUP BY dep.code, month
        ORDER BY dep.code, month
        """,
    )
    body = [
        (
            r["dept"],
            r["month"],
            _num(float(r["overtime_rate"] or 0) * 100, 1) + "%",
            _num(float(r["utilization"] or 0) * 100, 1) + "%",
        )
        for r in rows
    ]
    return (
        "### 5. Overtime rate and utilization by team by month\n\n"
        "Overtime is hours over 40 / total hours; utilization is billable / available.\n\n"
        + _table(["team", "month", "overtime", "utilization"], body)
    )


# --- Scenario checks --------------------------------------------------------


def check_bad_manager(session: Session) -> dict[str, float | None]:
    from_month = sc.BAD_MANAGER_EXIT_QUARTERS[0]

    scoped = one(
        session,
        """
        SELECT
          SUM(CASE WHEN manager_id = :mgr THEN terminated_in_month::int ELSE 0 END) AS mgr_exits,
          SUM(CASE WHEN manager_id = :mgr
                   THEN (active_at_month_start::int + active_at_month_end::int) / 2.0
                   ELSE 0 END) AS mgr_headcount_months,
          SUM(terminated_in_month::int) AS all_exits,
          SUM((active_at_month_start::int + active_at_month_end::int) / 2.0) AS all_headcount_months
        FROM fact_monthly_headcount_snapshot
        WHERE month_start >= :from_month
        """,
        mgr=sc.BAD_MANAGER_ID,
        from_month=from_month,
    )
    mgr_rate = _annualized(scoped.get("mgr_exits"), scoped.get("mgr_headcount_months"))
    all_rate = _annualized(scoped.get("all_exits"), scoped.get("all_headcount_months"))
    ratio = (mgr_rate / all_rate) if (mgr_rate and all_rate) else None

    drivers = one(
        session,
        """
        SELECT
          AVG(CASE WHEN s.manager_id = :mgr
                   THEN (r.driver_manager - 1) / 4.0 * 100 END) AS team_manager,
          AVG((r.driver_manager - 1) / 4.0 * 100)              AS company_manager
        FROM fact_survey_response r
        JOIN fact_monthly_headcount_snapshot s
          ON s.employee_id = r.employee_id
         AND s.month_start = date_trunc('month', r.submitted_on)::date
        """,
        mgr=sc.BAD_MANAGER_ID,
    )
    gap = None
    if drivers.get("team_manager") is not None and drivers.get("company_manager") is not None:
        gap = float(drivers["company_manager"]) - float(drivers["team_manager"])

    exits = one(
        session,
        """
        SELECT COUNT(*) AS exits FROM fact_monthly_headcount_snapshot
        WHERE manager_id = :mgr AND terminated_in_month AND month_start >= :from_month
        """,
        mgr=sc.BAD_MANAGER_ID,
        from_month=from_month,
    )
    regretted = one(
        session,
        """
        SELECT COUNT(*) AS regretted
        FROM dim_employee e
        WHERE e.manager_id = :mgr
          AND e.termination_date IS NOT NULL
          AND e.termination_date >= :from_month
          AND e.termination_type = 'voluntary'
          AND (SELECT r.rating FROM fact_performance_review r
               WHERE r.employee_id = e.employee_id
               ORDER BY r.review_date DESC LIMIT 1) >= 4
        """,
        mgr=sc.BAD_MANAGER_ID,
        from_month=from_month,
    )
    return {
        "attrition_ratio": ratio,
        "driver_gap": gap,
        "forced_exits": float(exits.get("exits") or 0),
        "regretted_exits": float(regretted.get("regretted") or 0),
    }


def check_sourcing(session: Session) -> dict[str, float | None]:
    cutoff = add_months(WINDOW_END, -sc.RETENTION_HORIZON_MONTHS)
    retention = q(
        session,
        """
        SELECT src.code AS source,
               COUNT(*) AS cohort,
               SUM(CASE WHEN e.termination_date IS NULL
                         OR e.termination_date > (e.hire_date + INTERVAL '12 months')
                        THEN 1 ELSE 0 END) AS retained
        FROM dim_employee e
        JOIN dim_source src ON src.source_id = e.source_id
        WHERE e.hire_date >= :window_start AND e.hire_date <= :cutoff
        GROUP BY src.code
        """,
        window_start=WINDOW_START,
        cutoff=cutoff,
    )
    by_source = {
        r["source"]: (float(r["retained"]) / float(r["cohort"]) * 100) if r["cohort"] else None
        for r in retention
    }

    cost = q(
        session,
        """
        WITH hires AS (
          SELECT a.requisition_id, a.source_id
          FROM fact_application a WHERE a.hired_employee_id IS NOT NULL
        ), per_req AS (
          SELECT requisition_id, COUNT(*) AS hires FROM hires GROUP BY requisition_id
        )
        SELECT src.code AS source,
               SUM((r.internal_cost + r.external_cost) / per_req.hires) / COUNT(*) AS cost_per_hire
        FROM hires h
        JOIN per_req ON per_req.requisition_id = h.requisition_id
        JOIN dim_requisition r ON r.requisition_id = h.requisition_id
        JOIN dim_source src ON src.source_id = h.source_id
        GROUP BY src.code
        """,
    )
    cost_by_source = {r["source"]: float(r["cost_per_hire"] or 0) for r in cost}
    agency_cost = cost_by_source.get("AGENCY")
    referral_cost = cost_by_source.get("REFERRAL")
    ratio = (agency_cost / referral_cost) if (agency_cost and referral_cost) else None

    return {
        "agency_retention": by_source.get("AGENCY"),
        "referral_retention": by_source.get("REFERRAL"),
        "cost_ratio": ratio,
    }


def check_reorg(session: Session) -> dict[str, float | None]:
    means = q(
        session,
        """
        SELECT sv.quarter_start,
               AVG((r.driver_belonging - 1) / 4.0 * 100) AS belonging,
               AVG((r.driver_growth    - 1) / 4.0 * 100) AS growth
        FROM fact_survey_response r
        JOIN dim_survey sv ON sv.survey_id = r.survey_id
        GROUP BY sv.quarter_start ORDER BY sv.quarter_start
        """,
    )
    pre = [r for r in means if r["quarter_start"] < sc.REORG_QUARTER]
    during = [r for r in means if r["quarter_start"] in sc.REORG_AFFECTED_QUARTERS]

    def mean_of(rows: list[dict[str, Any]], key: str) -> float | None:
        values = [float(r[key]) for r in rows if r[key] is not None]
        return sum(values) / len(values) if values else None

    pre_belonging, during_belonging = mean_of(pre, "belonging"), mean_of(during, "belonging")
    pre_growth, during_growth = mean_of(pre, "growth"), mean_of(during, "growth")

    lag_quarter = add_months(sc.REORG_QUARTER, 3 * sc.REORG_ATTRITION_LAG_QUARTERS)
    before = one(
        session,
        _ATTRITION_SQL,
        from_month=sc.REORG_QUARTER,
        to_month=add_months(sc.REORG_QUARTER, 2),
    )
    after = one(
        session, _ATTRITION_SQL, from_month=lag_quarter, to_month=add_months(lag_quarter, 2)
    )
    before_rate = _annualized(before.get("exits"), before.get("headcount_months"))
    after_rate = _annualized(after.get("exits"), after.get("headcount_months"))

    return {
        "belonging_drop": (pre_belonging - during_belonging)
        if (pre_belonging and during_belonging)
        else None,
        "growth_drop": (pre_growth - during_growth) if (pre_growth and during_growth) else None,
        "lagged_attrition_rise": (after_rate / before_rate)
        if (before_rate and after_rate)
        else None,
    }


def check_sales(session: Session) -> dict[str, float | None]:
    dwell = q(
        session,
        """
        SELECT (dep.code = 'SAL') AS is_sales,
               AVG(se.exited_on - se.entered_on)::float AS dwell
        FROM fact_application_stage_event se
        JOIN fact_application a ON a.application_id = se.application_id
        JOIN dim_requisition r  ON r.requisition_id = a.requisition_id
        JOIN dim_department dep ON dep.department_id = r.department_id
        WHERE se.stage = 'interview' AND se.exited_on IS NOT NULL
        GROUP BY 1
        """,
    )
    dwell_map = {bool(r["is_sales"]): r["dwell"] for r in dwell}

    ttf = q(
        session,
        """
        SELECT (dep.code = 'SAL') AS is_sales,
               AVG(a.offer_accepted_date - r.opened_date)::float AS ttf
        FROM fact_application a
        JOIN dim_requisition r  ON r.requisition_id = a.requisition_id
        JOIN dim_department dep ON dep.department_id = r.department_id
        WHERE a.offer_accepted_date IS NOT NULL
        GROUP BY 1
        """,
    )
    ttf_map = {bool(r["is_sales"]): r["ttf"] for r in ttf}
    company = one(
        session,
        """
        SELECT AVG(a.offer_accepted_date - r.opened_date)::float AS ttf
        FROM fact_application a
        JOIN dim_requisition r ON r.requisition_id = a.requisition_id
        WHERE a.offer_accepted_date IS NOT NULL
        """,
    )

    return {
        "sales_dwell": dwell_map.get(True),
        "other_dwell": dwell_map.get(False),
        "sales_ttf": ttf_map.get(True),
        "company_ttf": company.get("ttf"),
    }


def check_support(session: Session) -> dict[str, float | None]:
    hours = one(
        session,
        """
        SELECT SUM(GREATEST(t.billable_hours + t.non_billable_hours - 40, 0))
                 / NULLIF(SUM(t.billable_hours + t.non_billable_hours), 0) AS overtime_rate,
               SUM(t.billable_hours) / NULLIF(SUM(t.available_hours), 0)   AS utilization
        FROM fact_timesheet_week t
        JOIN dim_department dep ON dep.department_id = t.department_id
        WHERE dep.code = :dept
        """,
        dept=sc.SUPPORT_DEPARTMENT,
    )
    workload = q(
        session,
        """
        SELECT dep.code AS dept, AVG((r.driver_workload - 1) / 4.0 * 100) AS workload
        FROM fact_survey_response r
        JOIN fact_monthly_headcount_snapshot s
          ON s.employee_id = r.employee_id
         AND s.month_start = date_trunc('month', r.submitted_on)::date
        JOIN dim_department dep ON dep.department_id = s.department_id
        GROUP BY dep.code ORDER BY workload ASC
        """,
    )
    lowest = workload[0]["dept"] if workload else None

    final_month = WINDOW_END.replace(day=1)
    earlier_month = add_months(final_month, -(sc.SUPPORT_ABSENCE_CLIMB_MONTHS - 1))
    climb = one(
        session,
        """
        WITH monthly AS (
          SELECT date_trunc('month', a.absence_date)::date AS month,
                 SUM(a.days) AS unplanned_days
          FROM fact_absence a
          JOIN dim_employee e ON e.employee_id = a.employee_id
          JOIN dim_department dep ON dep.department_id = e.department_id
          WHERE a.is_unplanned AND dep.code = :dept
          GROUP BY 1
        )
        SELECT
          (SELECT unplanned_days FROM monthly WHERE month = :final)   AS final_days,
          (SELECT unplanned_days FROM monthly WHERE month = :earlier) AS earlier_days
        """,
        dept=sc.SUPPORT_DEPARTMENT,
        final=final_month,
        earlier=earlier_month,
    )
    final_days = climb.get("final_days")
    earlier_days = climb.get("earlier_days")
    absence_ratio = (
        float(final_days) / float(earlier_days) if (final_days and earlier_days) else None
    )

    return {
        "overtime_rate": float(hours["overtime_rate"] or 0) * 100 if hours else None,
        "utilization": float(hours["utilization"] or 0) * 100 if hours else None,
        "workload_is_lowest": 1.0 if lowest == sc.SUPPORT_DEPARTMENT else 0.0,
        "absence_climb": absence_ratio,
    }


def check_tenure_cliff(session: Session) -> dict[str, float | None]:
    low, high = sc.CLIFF_MONTH_RANGE
    rows = q(
        session,
        """
        SELECT s.tenure_months, SUM(s.terminated_in_month::int) AS exits
        FROM fact_monthly_headcount_snapshot s
        JOIN dim_employee e ON e.employee_id = s.employee_id
        WHERE date_trunc('quarter', e.hire_date)::date = ANY(:cohorts)
        GROUP BY s.tenure_months ORDER BY s.tenure_months
        """,
        cohorts=list(sc.CLIFF_COHORT_QUARTERS),
    )
    exits_by_tenure = {int(r["tenure_months"]): float(r["exits"]) for r in rows}

    inside = [exits_by_tenure.get(m, 0.0) for m in range(low, high + 1)]
    adjacent = [
        exits_by_tenure.get(m, 0.0) for m in list(range(9, low)) + list(range(high + 1, 24))
    ]

    inside_mean = sum(inside) / len(inside) if inside else 0.0
    adjacent_mean = sum(adjacent) / len(adjacent) if adjacent else 0.0
    ratio = (inside_mean / adjacent_mean) if adjacent_mean else None

    return {"cliff_ratio": ratio, "cliff_exits": sum(inside)}


CHECKS = {
    "bad_manager": check_bad_manager,
    "sourcing_decay": check_sourcing,
    "post_reorg_dip": check_reorg,
    "sales_bottleneck": check_sales,
    "support_burnout": check_support,
    "tenure_cliff": check_tenure_cliff,
}


def _scenario_block(session: Session) -> tuple[str, bool]:
    lines: list[str] = ["## Scenario verification\n"]
    all_passed = True

    for scenario in SCENARIOS:
        actuals = CHECKS[scenario.key](session)
        results: list[tuple[Target, float | None, bool]] = []
        for target in scenario.targets:
            actual = actuals.get(target.key)
            ok = target.passes(actual)
            results.append((target, actual, ok))
        scenario_passed = all(ok for _, _, ok in results)
        all_passed = all_passed and scenario_passed

        badge = "PASS" if scenario_passed else "**FAIL**"
        lines.append(f"### {scenario.number}. {scenario.title} — {badge}\n")
        lines.append(f"{scenario.story}\n")
        body = []
        for target, actual, ok in results:
            expectation = {
                "within": f"{_num(target.target, 2)} ± {_num(target.tolerance, 2)}",
                "at_least": f">= {_num(target.target - target.tolerance, 2)}",
                "at_most": f"<= {_num(target.target + target.tolerance, 2)}",
                "exact": f"= {_num(target.target, 0)}",
            }[target.comparison]
            body.append(
                (
                    target.label,
                    expectation + (f" {target.unit}" if target.unit else ""),
                    _num(actual, 2),
                    "ok" if ok else "**MISS**",
                )
            )
        lines.append(_table(["assertion", "expected", "actual", ""], body) + "\n")
        lines.append(f"*Demo beat:* {scenario.demo_beat}\n")

    return "\n".join(lines), all_passed


def checksum(session: Session) -> str:
    """Hash row counts plus key aggregates, so determinism is verified not asserted."""
    payload: dict[str, Any] = {}
    tables = q(
        session,
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
          AND table_name <> 'alembic_version'
        ORDER BY table_name
        """,
    )
    for row in tables:
        name = row["table_name"]
        count = one(session, f"SELECT COUNT(*) AS n FROM {name}")  # noqa: S608 - from catalog
        payload[name] = count.get("n")

    payload["employees"] = one(
        session,
        """
        SELECT COUNT(*) AS total,
               COUNT(termination_date) AS terminated,
               SUM(comp_amount)::text AS comp_total
        FROM dim_employee
        """,
    )
    payload["snapshot"] = one(
        session,
        """
        SELECT SUM(active_at_month_end::int) AS active_months,
               SUM(terminated_in_month::int) AS exits
        FROM fact_monthly_headcount_snapshot
        """,
    )
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def run_validation(counts: dict[str, int] | None = None, scale: float = 1.0) -> bool:
    with SessionLocal() as session:
        digest = checksum(session)
        sections = [
            section_headcount(session),
            section_attrition_by_department(session),
            section_funnel(session),
            section_drivers(session),
            section_overtime(session),
        ]
        scenario_text, passed = _scenario_block(session)

        row_counts = counts or {
            r["table_name"]: one(
                session,
                f"SELECT COUNT(*) AS n FROM {r['table_name']}",  # noqa: S608 - from catalog
            )["n"]
            for r in q(
                session,
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE'
                  AND table_name <> 'alembic_version' ORDER BY table_name
                """,
            )
        }

    header = [
        "# Seed validation report",
        "",
        f"Window **{WINDOW_START} to {WINDOW_END}** · scale **{scale:g}** · "
        f"seed **42** · checksum **{digest}**",
        "",
        "Generated by `python -m seed.generate --reset`. All data is synthetic.",
        "",
        f"**Overall: {'ALL SCENARIOS PASS' if passed else 'ONE OR MORE SCENARIOS FAILED'}**",
        "",
        "## Row counts",
        "",
        _table(
            ["table", "rows"],
            [(name, f"{value:,}") for name, value in sorted(row_counts.items())],
        ),
        "",
    ]

    document = (
        "\n".join(header) + "\n" + scenario_text + "\n\n## Report\n\n" + "\n\n".join(sections)
    )
    document += "\n"
    REPORT_PATH.write_text(document, encoding="utf-8")

    print()
    print(scenario_text)
    print(f"checksum: {digest}")
    print(f"full report written to {REPORT_PATH}")
    return passed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the generated warehouse.")
    parser.add_argument(
        "--checksum", action="store_true", help="Print only the determinism checksum."
    )
    args = parser.parse_args(argv)

    if args.checksum:
        with SessionLocal() as session:
            print(checksum(session))
        return 0

    return 0 if run_validation() else 1


if __name__ == "__main__":
    sys.exit(main())
