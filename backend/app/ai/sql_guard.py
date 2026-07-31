"""Validation for model-generated SQL. The security boundary of the Ask feature.

Nothing here touches the database or the network. That is deliberate and it is the same
reason `flight_risk`'s scoring functions are pure: this is the one module where a bug is
dangerous rather than annoying, so it has to be exhaustively testable without a warehouse.

**Why an AST and not string matching.** Every regex-based validator fails the same way — it
inspects the text a human reads instead of the query the planner runs. `sqlglot` parses to
a tree, and a table reference is a table reference whether it appears in the top-level
`FROM`, three subqueries down, inside a CTE that shadows a view name, or behind a comment
that a regex happily skips over. Walking the tree is the difference between rejecting

    SELECT * FROM (SELECT salary FROM dim_employee) x

and letting it through because the word after `FROM` was a parenthesis.

**The allowlist is derived, not duplicated.** Every view file states `NL-queryable: yes|no`
in its header, and that line is the single source of truth. Copying the list here would
mean a view added in a later phase is either silently unqueryable or, far worse, silently
queryable because someone updated one list and not the other.

Four defences, in order:

1. one statement only — no stacking a second query behind a semicolon;
2. `SELECT` only — every write and DDL node is rejected by type, not by keyword;
3. every table in the allowlist — base tables are unreachable even from a subquery;
4. a `LIMIT` is imposed, and clamped if the model asked for more.

Executing under a `READ ONLY` transaction with a statement timeout is a fifth defence, but
it lives in `nl_query.py` because it needs a session. It is a backstop, not the boundary —
see the phase-7 note about a restricted database role.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import sqlglot
from sqlglot import exp

#: docs/METRICS.md caps a result set here, and the plan requires it be mandatory rather
#: than advisory. A question that genuinely needs more rows is a report, not a chat answer.
MAX_ROWS = 500

DIALECT = "postgres"

#: Functions that read the wall clock. Banned because the warehouse covers a fixed span:
#: the model, asked for "the last year", generated
#: `WHERE quarter_start >= CURRENT_DATE - INTERVAL '1 year'`, which silently returns less
#: data every day and eventually none. The overview and the manager ranking each had to fix
#: the same trap in hand-written code; there is no reason to let it back in through SQL.
_CLOCK_FUNCTIONS = frozenset(
    {
        "current_date",
        "current_time",
        "current_timestamp",
        "localtime",
        "localtimestamp",
        "now",
        "statement_timestamp",
        "transaction_timestamp",
        "clock_timestamp",
    }
)

#: Server-side functions with no business meaning in an analytics answer, whose only use
#: here would be to stall a connection or read the server's environment.
_BANNED_FUNCTIONS = frozenset(
    {
        "pg_sleep",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "dblink",
        "query_to_xml",
        "set_config",
        "pg_terminate_backend",
        "pg_cancel_backend",
    }
)

#: Only `SELECT` survives. Listed by node type so a future sqlglot version that renames a
#: keyword cannot quietly open a hole.
_FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,  # sqlglot's catch-all for anything it does not model: COPY, VACUUM, SET...
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Use,
)

_VIEWS_DIR = Path(__file__).resolve().parents[2] / "sql" / "views"

_NL_QUERYABLE = re.compile(r"^--\s*NL-queryable:\s*(\w+)", re.IGNORECASE | re.MULTILINE)
_VIEW_NAME = re.compile(r"^--\s*(v_\w+)", re.IGNORECASE | re.MULTILINE)


class UnsafeSqlError(ValueError):
    """Raised when generated SQL fails validation. The message is shown to the user."""


@dataclass(frozen=True, slots=True)
class SafeSql:
    """SQL that passed every check, rewritten with an enforced LIMIT.

    `sql` is what executes; `tables` is what it reads. Both are returned to the caller and
    surfaced in the API response, because an answer whose query you cannot see is not
    auditable — which is the whole reason the Ask page shows the SQL.
    """

    sql: str
    tables: tuple[str, ...]
    limit: int


@lru_cache(maxsize=1)
def allowlist() -> frozenset[str]:
    """View names marked `NL-queryable: yes` in their own header comment.

    Parsed from the files rather than restated here, so the header stays the single source
    of truth. A new view is unqueryable until its header says otherwise, which is the safe
    direction to fail in.
    """
    allowed: set[str] = set()
    for path in sorted(_VIEWS_DIR.glob("*.sql")):
        header = path.read_text(encoding="utf-8")[:4000]
        flag = _NL_QUERYABLE.search(header)
        name = _VIEW_NAME.search(header)
        if flag and name and flag.group(1).lower() == "yes":
            allowed.add(name.group(1).lower())
    if not allowed:
        # A packaging mistake that loses sql/views/ would otherwise produce an empty
        # allowlist, which rejects everything — safe, but silently and confusingly.
        raise RuntimeError(f"No NL-queryable views found under {_VIEWS_DIR}")
    return frozenset(allowed)


def _cte_names(statement: exp.Expression) -> set[str]:
    """Names bound by WITH clauses anywhere in the statement.

    A CTE is a reference to something defined inside the query, not to a table, so it must
    not be measured against the allowlist. Its *body* still is — the walk visits those
    nodes too, which is what stops `WITH x AS (SELECT * FROM dim_employee) SELECT * FROM x`.
    """
    return {
        cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE) if cte.alias_or_name
    }


def validate(sql: str, *, max_rows: int = MAX_ROWS) -> SafeSql:
    """Parse, check, and return executable SQL — or raise `UnsafeSqlError` with a readable why.

    Every rejection message is written for the person who asked the question, not for a
    log: the Ask page prints it verbatim.
    """
    if not sql or not sql.strip():
        raise UnsafeSqlError("The model returned no SQL.")

    try:
        statements = sqlglot.parse(sql, dialect=DIALECT)
    except Exception as exc:  # sqlglot raises several unrelated types
        raise UnsafeSqlError(f"That SQL could not be parsed: {exc}") from exc

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise UnsafeSqlError(
            f"Only one statement is allowed; that was {len(statements)}. "
            "Stacked statements are rejected without being run."
        )

    statement = statements[0]

    for node_type in _FORBIDDEN_NODES:
        if isinstance(statement, node_type) or statement.find(node_type) is not None:
            raise UnsafeSqlError(
                f"Only SELECT is allowed here — {node_type.__name__.upper()} is not. "
                "This endpoint is read-only by construction."
            )

    if not isinstance(statement, exp.Select | exp.Subquery | exp.Union):
        raise UnsafeSqlError("Only SELECT statements can be run from a question.")

    # `SELECT ... INTO t` writes a table while still parsing as a Select.
    if statement.find(exp.Into) is not None:
        raise UnsafeSqlError("SELECT ... INTO writes a table, so it is not allowed.")

    _reject_banned_functions(statement)

    tables = _collect_tables(statement)
    allowed = allowlist()
    blocked = sorted(t for t in tables if t not in allowed)
    if blocked:
        raise UnsafeSqlError(
            f"{', '.join(blocked)} is not available to natural-language queries. "
            f"Answerable views: {', '.join(sorted(allowed))}."
        )
    if not tables:
        raise UnsafeSqlError("That query reads no table, so there is nothing to answer from.")

    limited, limit = _enforce_limit(statement, max_rows)
    return SafeSql(sql=limited, tables=tuple(sorted(tables)), limit=limit)


def _reject_banned_functions(statement: exp.Expression) -> None:
    for node in statement.find_all(exp.Anonymous):
        name = (node.this or "").lower() if isinstance(node.this, str) else ""
        if name in _BANNED_FUNCTIONS:
            raise UnsafeSqlError(f"The function {name}() is not allowed here.")
        if name in _CLOCK_FUNCTIONS:
            raise UnsafeSqlError(_CLOCK_MESSAGE.format(name=f"{name}()"))

    # sqlglot models the parenthesis-free spellings as their own node types, so
    # CURRENT_DATE never appears as an Anonymous function and a name-only check misses it.
    for node_type, label in (
        (exp.CurrentDate, "CURRENT_DATE"),
        (exp.CurrentTime, "CURRENT_TIME"),
        (exp.CurrentTimestamp, "CURRENT_TIMESTAMP"),
        (exp.CurrentUser, "CURRENT_USER"),
    ):
        if statement.find(node_type) is not None:
            if node_type is exp.CurrentUser:
                raise UnsafeSqlError("CURRENT_USER is not available to natural-language queries.")
            raise UnsafeSqlError(_CLOCK_MESSAGE.format(name=label))


_CLOCK_MESSAGE = (
    "{name} is not allowed: this warehouse covers a fixed period, so a query anchored to "
    "today's date returns less data every day and eventually none. Anchor to the data "
    "instead — for example `(SELECT max(month_start) FROM v_headcount_monthly)`."
)


def _collect_tables(statement: exp.Expression) -> set[str]:
    """Every real table the statement reads, with CTE self-references removed."""
    ctes = _cte_names(statement)
    tables: set[str] = set()
    for table in statement.find_all(exp.Table):
        name = (table.name or "").lower()
        if not name or name in ctes:
            continue
        # A schema-qualified name is a way to reach past the allowlist by spelling; the
        # allowlist holds bare view names, so anything qualified is rejected by not matching.
        if table.db:
            tables.add(f"{table.db.lower()}.{name}")
        else:
            tables.add(name)
    return tables


def _enforce_limit(statement: exp.Expression, max_rows: int) -> tuple[str, int]:
    """Return the SQL with a LIMIT no larger than `max_rows`.

    Rewriting the tree rather than appending text means the LIMIT lands in the right place
    for a UNION or an ORDER BY, where string concatenation would produce a syntax error or,
    worse, attach the limit to only the last branch.
    """
    existing = statement.args.get("limit")
    limit = max_rows
    if existing is not None:
        try:
            asked = int(existing.expression.name)
            limit = min(asked, max_rows) if asked > 0 else max_rows
        except (AttributeError, TypeError, ValueError):
            # A non-literal LIMIT (a parameter, an expression) is not something to reason
            # about — replace it with the cap.
            limit = max_rows

    limited = statement.limit(limit, dialect=DIALECT)
    return limited.sql(dialect=DIALECT, pretty=True), limit
