"""Natural language to SQL, over the allowlisted views only.

The flow is deliberately boring: ask the model for SQL, validate it in `sql_guard`, run it
in a read-only transaction, and return the rows *with the SQL that produced them*. That
last part is the feature. An answer you cannot audit is a number someone has to take on
faith, which is exactly what a people-analytics team cannot do with headcount and attrition.

**The model is never trusted.** It is asked for SQL and its output goes through the same
validator regardless of how well the prompt is written — the prompt reduces refusals, the
guard prevents damage, and confusing the two is how these features go wrong. `sql_guard`
has no network and no database precisely so that boundary can be tested exhaustively.

**The schema is described, not discovered.** The prompt carries the view list with grains
and columns pulled from the live database, so it cannot drift from what actually exists. A
hand-maintained schema description is wrong the first time a view changes and then
generates confidently invalid SQL forever.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.cache import get_or_call
from app.ai.provider import AiUnavailableError, get_provider
from app.ai.sql_guard import MAX_ROWS, UnsafeSqlError, allowlist, validate
from app.config import settings

log = logging.getLogger(__name__)

FEATURE = "ask"

#: A query that outlives this is not an answer anyone is waiting for, and on Render's free
#: tier it is a worker held hostage. Enforced by Postgres, not by Python.
STATEMENT_TIMEOUT_MS = 5000

#: Questions that hit the planted scenarios, per BUILD_PLAN section 6 ("seed those examples
#: with questions that hit your planted scenarios"). Each one has been run.
EXAMPLE_QUESTIONS: tuple[dict[str, str], ...] = (
    {
        "question": "Which managers have the worst attrition?",
        "hint": "The planted bad-manager scenario, surfaced from the data alone.",
    },
    {
        "question": "Which hiring channel produces the hires that stay longest?",
        "hint": "Agency is the most expensive channel and the worst-retaining one.",
    },
    {
        "question": "How has headcount changed by department over the last year?",
        "hint": "Growth and contraction side by side.",
    },
    {
        "question": "Do people with low engagement scores leave more often?",
        "hint": "Engagement quartile against the attrition that follows it.",
    },
    {
        "question": "Where do candidates drop out of the hiring funnel?",
        "hint": "Stage-by-stage conversion, and the stage that stalls.",
    },
)


@dataclass(frozen=True, slots=True)
class AskResult:
    """Everything the Ask page needs, including why it refused if it did."""

    question: str
    refused: bool
    sql: str | None = None
    explanation: str = ""
    refusal_reason: str = ""
    columns: tuple[str, ...] = ()
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    tables: tuple[str, ...] = ()
    model: str = ""
    cached: bool = False


_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sql": {
            "type": "string",
            "description": "One PostgreSQL SELECT statement, or empty if refusing.",
        },
        "explanation": {
            "type": "string",
            "description": "One or two plain sentences on what the query measures.",
        },
        "refused": {"type": "boolean"},
        "refusal_reason": {
            "type": "string",
            "description": "If refusing, what the data cannot answer and why.",
        },
    },
    "required": ["sql", "explanation", "refused", "refusal_reason"],
}


@lru_cache(maxsize=1)
def _schema_description(_fingerprint: str) -> str:
    """Column lists for every allowlisted view, read from the database.

    Cached on a fingerprint of the allowlist so it is built once per process but rebuilt if
    the set of views changes.
    """
    from app.db import engine

    lines: list[str] = []
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ANY(:views)
                ORDER BY table_name, ordinal_position
                """
            ),
            {"views": sorted(allowlist())},
        ).all()

    by_view: dict[str, list[str]] = {}
    for view, column, dtype in rows:
        by_view.setdefault(view, []).append(f"{column} {_short_type(dtype)}")

    for view in sorted(by_view):
        lines.append(f"{view}({', '.join(by_view[view])})")
    return "\n".join(lines)


def _short_type(data_type: str) -> str:
    return {
        "character varying": "text",
        "timestamp with time zone": "timestamptz",
        "double precision": "float",
        "numeric": "numeric",
        "integer": "int",
        "smallint": "int",
        "bigint": "int",
    }.get(data_type, data_type)


def schema_description() -> str:
    return _schema_description(",".join(sorted(allowlist())))


SYSTEM_PROMPT = """\
You write one PostgreSQL SELECT statement to answer a question about an HR analytics \
warehouse. The result is shown to an HR leader alongside the SQL itself, so the query has \
to be correct and readable.

You may read ONLY these views. There are no other tables, and base tables are not \
available at any nesting depth:

{schema}

Hard rules — a query breaking any of them is rejected before it runs:
- One statement. SELECT only. No INSERT, UPDATE, DELETE, DDL, or SELECT INTO.
- Never reference a table that is not listed above.
- Include LIMIT {max_rows} or less.
- Never use CURRENT_DATE, now(), or any wall-clock function. This warehouse covers a fixed \
historical period, so a query anchored to today returns less data every day and eventually \
none. Anchor to the data instead, e.g. \
`(SELECT max(month_start) FROM v_headcount_monthly)`.

Metric rules — these are how the business defines its numbers:
- Attrition and every other rate divides by AVERAGE headcount for the period, never \
end-of-period headcount. The views expose `headcount_months` and `avg_headcount` for this.
- Annualized rate = terminations * 12 / sum of monthly average headcount. This is correct \
for any number of months, so use it at every grain.
- Sum numerators and denominators separately, then divide once. Never average a column of \
pre-computed rates: that weights a three-person team the same as a three-hundred-person one.
- Manager attrition is only meaningful for teams averaging at least 8 reports. Filter on \
average team size, not on the count of distinct people.
- When *ranking* managers against each other, aggregate a trailing 12 months ending at the \
latest quarter in the data, not the whole history and not a single quarter. A quarter's \
denominator is small enough that one bad three-month stretch outranks a team that has been \
losing people all year, and a multi-year average hides a team that is collapsing now. The \
dashboard ranks this way, so a query that does not will disagree with it.
- To rank managers against each other, aggregate a trailing 12 months ending at the latest \
quarter in the data, not the whole history. A three-year average hides a team that was fine \
for two years and is failing now, and a single quarter's denominator is small enough that \
one bad stretch outranks a team losing people all year. The dashboard ranks this way, so a \
query that does not will contradict the page the reader just came from.

Style:
- Alias aggregates to readable names — `annualized_attrition`, not `?column?`.
- Order so the answer is the first row.
- Round rates in SQL only if it aids reading; the caller formats for display.

If the question cannot be answered from these views — it needs individual salaries, named \
people, or data the warehouse does not hold — set refused to true, leave sql empty, and \
explain what is missing in refusal_reason. Refusing is a correct answer; inventing a column \
is not."""


def ask(db: Session, question: str, *, provider: Any | None = None) -> AskResult:
    """Answer a question in SQL, or refuse with a reason.

    Raises `AiUnavailableError` only when there is no provider and nothing cached; every
    other failure is a populated `AskResult` describing what went wrong.
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("A question is required.")

    provider = provider or get_provider()
    if provider is None:
        raise AiUnavailableError(
            "Natural-language querying needs an AI key. Set GOOGLE_API_KEY in backend/.env."
        )

    model = settings.resolved_models[0] or ""

    def call() -> dict[str, Any]:
        completion = provider.complete_json(
            system=SYSTEM_PROMPT.format(schema=schema_description(), max_rows=MAX_ROWS),
            user=question,
            schema=_RESPONSE_SCHEMA,
            model=model,
        )
        return completion.data

    # Only the model's answer is cached, never the rows. The warehouse can change under a
    # cached question, and serving stale numbers is a worse failure than a second query.
    cached = get_or_call(
        db, feature=FEATURE, model=model, inputs={"question": question.lower()}, call=call
    )
    answer = cached.payload

    if answer.get("refused"):
        return AskResult(
            question=question,
            refused=True,
            refusal_reason=str(answer.get("refusal_reason") or "").strip()
            or "That question cannot be answered from the available views.",
            explanation=str(answer.get("explanation") or ""),
            model=cached.model,
            cached=cached.cached,
        )

    raw_sql = str(answer.get("sql") or "")
    try:
        safe = validate(raw_sql)
    except UnsafeSqlError as exc:
        # The guard rejecting the model is a normal outcome, not an error state. The user
        # is shown the rejected SQL so the refusal is checkable rather than mysterious.
        return AskResult(
            question=question,
            refused=True,
            sql=raw_sql or None,
            refusal_reason=str(exc),
            explanation=str(answer.get("explanation") or ""),
            model=cached.model,
            cached=cached.cached,
        )

    try:
        columns, rows = _execute_read_only(db, safe.sql)
    except SQLAlchemyError as exc:
        return AskResult(
            question=question,
            refused=True,
            sql=safe.sql,
            refusal_reason=f"The query was valid but failed to run: {_db_message(exc)}",
            explanation=str(answer.get("explanation") or ""),
            tables=safe.tables,
            model=cached.model,
            cached=cached.cached,
        )

    return AskResult(
        question=question,
        refused=False,
        sql=safe.sql,
        explanation=str(answer.get("explanation") or ""),
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=len(rows) >= safe.limit,
        tables=safe.tables,
        model=cached.model,
        cached=cached.cached,
    )


def _execute_read_only(db: Session, sql: str) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    """Run inside a transaction that cannot write and cannot run long.

    A backstop rather than the boundary — `sql_guard` is the boundary. It is here because
    defences that depend on a correct parse should not be the only thing between a
    generated string and the database. A restricted database role is the phase-7 upgrade.
    """
    db.rollback()  # start clean; SET LOCAL only applies inside the current transaction
    try:
        db.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        db.execute(text("SET LOCAL transaction_read_only = on"))
        result = db.execute(text(sql))
        columns = tuple(result.keys())
        rows = [dict(row) for row in result.mappings().all()]
    finally:
        # Always end the transaction so the read-only flag never leaks into the next
        # request on a pooled connection.
        db.rollback()
    return columns, rows


def _db_message(exc: SQLAlchemyError) -> str:
    original = getattr(exc, "orig", None)
    message = str(original or exc).strip().splitlines()[0]
    if "statement timeout" in message.lower():
        return f"it took longer than {STATEMENT_TIMEOUT_MS // 1000}s."
    return message[:200]
