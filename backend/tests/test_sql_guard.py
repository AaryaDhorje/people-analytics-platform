"""The SQL guard, exercised adversarially.

This is the module where a bug is dangerous rather than annoying, so it gets the most
hostile tests in the suite. Every case below is a way a model could produce SQL that reads
something it should not, phrased the way a model actually phrases things — nested, aliased,
wrapped in a CTE — rather than the obvious `DROP TABLE` a keyword filter would catch.

No database and no network: the guard is pure by design, so these run in milliseconds and
would still pass on a machine with no Postgres installed.
"""

import pytest

from app.ai.sql_guard import MAX_ROWS, SafeSql, UnsafeSqlError, allowlist, validate

# --- The allowlist is derived from the view headers -------------------------


def test_allowlist_comes_from_the_view_files() -> None:
    """Restating the list in Python would let it drift from the headers. A view added in a
    later phase must be unqueryable until its own header says otherwise."""
    allowed = allowlist()

    assert "v_manager_attrition_quarterly" in allowed
    assert "v_headcount_monthly" in allowed
    assert len(allowed) > 15


def test_flight_risk_inputs_is_excluded() -> None:
    """`50_v_flight_risk_inputs.sql` is the one view marked `NL-queryable: no` — it carries
    raw per-person signals. The header is the only place that decision is recorded, so this
    test is what stops a refactor from quietly including it."""
    assert "v_flight_risk_inputs" not in allowlist()


# --- What should be allowed -------------------------------------------------


def test_a_plain_select_over_an_allowlisted_view_passes() -> None:
    safe = validate("SELECT manager_id, terminations FROM v_manager_attrition_quarterly")

    assert isinstance(safe, SafeSql)
    assert safe.tables == ("v_manager_attrition_quarterly",)
    assert "v_manager_attrition_quarterly" in safe.sql


def test_a_cte_over_allowlisted_views_passes() -> None:
    """CTEs are how the model writes anything non-trivial, so rejecting them would reject
    most real answers. The CTE's own name must not be measured against the allowlist."""
    safe = validate(
        """
        WITH totals AS (
            SELECT manager_id, SUM(terminations) AS exits
            FROM v_manager_attrition_quarterly
            GROUP BY manager_id
        )
        SELECT manager_id, exits FROM totals ORDER BY exits DESC
        """
    )

    assert safe.tables == ("v_manager_attrition_quarterly",)


def test_a_join_across_two_allowlisted_views_passes() -> None:
    safe = validate(
        """
        SELECT h.month_start, a.terminations
        FROM v_headcount_monthly h
        JOIN v_manager_attrition_quarterly a ON a.department_id = h.department_id
        """
    )

    assert safe.tables == ("v_headcount_monthly", "v_manager_attrition_quarterly")


# --- Statement type ---------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO v_headcount_monthly VALUES (1)",
        "UPDATE dim_employee SET salary = 0",
        "DELETE FROM fact_survey_response",
        "DROP TABLE dim_employee",
        "CREATE TABLE evil (id int)",
        "ALTER TABLE dim_employee ADD COLUMN x int",
        "TRUNCATE dim_employee",
        "GRANT ALL ON dim_employee TO PUBLIC",
    ],
)
def test_writes_and_ddl_are_rejected(sql: str) -> None:
    with pytest.raises(UnsafeSqlError):
        validate(sql)


def test_stacked_statements_are_rejected() -> None:
    """The classic. The first statement looks harmless and the second is the attack."""
    with pytest.raises(UnsafeSqlError, match="[Oo]nly one statement"):
        validate("SELECT 1 FROM v_headcount_monthly; DROP TABLE dim_employee")


def test_select_into_is_rejected() -> None:
    """Parses as a SELECT and writes a table anyway, so a statement-type check alone
    would wave it through."""
    with pytest.raises(UnsafeSqlError, match="INTO"):
        validate("SELECT * INTO stolen FROM v_headcount_monthly")


def test_a_trailing_semicolon_is_fine() -> None:
    """Models emit one habitually; rejecting it would fail on style, not on safety."""
    assert validate("SELECT * FROM v_headcount_monthly;").tables == ("v_headcount_monthly",)


# --- Reaching a base table --------------------------------------------------
#
# The reason this module parses instead of matching strings. In each case the base table is
# somewhere a naive "word after FROM" check does not look.


def test_a_base_table_in_the_top_level_from_is_rejected() -> None:
    with pytest.raises(UnsafeSqlError, match="dim_employee"):
        validate("SELECT employee_id FROM dim_employee")


def test_a_base_table_inside_a_subquery_is_rejected() -> None:
    with pytest.raises(UnsafeSqlError, match="dim_employee"):
        validate("SELECT * FROM (SELECT employee_id FROM dim_employee) AS x")


def test_a_base_table_inside_a_cte_is_rejected() -> None:
    """The CTE binds the name `v_headcount_monthly`, so a validator that only checked the
    final SELECT would see an allowlisted name and pass a query reading dim_employee."""
    with pytest.raises(UnsafeSqlError, match="dim_employee"):
        validate(
            """
            WITH v_headcount_monthly AS (SELECT * FROM dim_employee)
            SELECT * FROM v_headcount_monthly
            """
        )


def test_a_base_table_in_a_where_clause_subquery_is_rejected() -> None:
    with pytest.raises(UnsafeSqlError, match="dim_employee"):
        validate(
            """
            SELECT month_start FROM v_headcount_monthly
            WHERE department_id IN (SELECT department_id FROM dim_employee)
            """
        )


def test_a_base_table_reached_through_a_union_is_rejected() -> None:
    with pytest.raises(UnsafeSqlError, match="dim_employee"):
        validate(
            "SELECT department_id FROM v_headcount_monthly "
            "UNION ALL SELECT department_id FROM dim_employee"
        )


def test_a_table_hidden_behind_a_comment_is_rejected() -> None:
    """The case that most cleanly separates a parser from a regex. A validator scanning for
    the word after `FROM` reads the commented-out view name and approves a query against
    `dim_employee`; the parser discards comments before the tree exists."""
    with pytest.raises(UnsafeSqlError, match="dim_employee"):
        validate("SELECT * FROM /* v_headcount_monthly */ dim_employee")


def test_a_base_table_in_a_lateral_join_is_rejected() -> None:
    with pytest.raises(UnsafeSqlError, match="dim_employee"):
        validate(
            "SELECT * FROM v_headcount_monthly h, "
            "LATERAL (SELECT * FROM dim_employee) d"
        )


def test_a_base_table_in_a_scalar_subquery_is_rejected() -> None:
    """The table appears in the SELECT list rather than in any FROM clause."""
    with pytest.raises(UnsafeSqlError, match="dim_employee"):
        validate(
            "SELECT (SELECT max(salary) FROM dim_employee) FROM v_headcount_monthly"
        )


def test_a_writing_cte_is_rejected() -> None:
    """Postgres allows DELETE ... RETURNING inside a CTE, so a query that is a SELECT at
    the top level can still delete rows two lines down."""
    with pytest.raises(UnsafeSqlError, match="DELETE"):
        validate("WITH x AS (DELETE FROM dim_employee RETURNING *) SELECT * FROM x")


def test_the_non_queryable_view_is_rejected_like_any_other_table() -> None:
    with pytest.raises(UnsafeSqlError, match="v_flight_risk_inputs"):
        validate("SELECT * FROM v_flight_risk_inputs")


def test_a_schema_qualified_name_does_not_bypass_the_allowlist() -> None:
    """`public.v_headcount_monthly` resolves to an allowlisted view, but accepting the
    qualified spelling also accepts `pg_catalog.pg_authid`. The allowlist holds bare names,
    so qualified references simply do not match."""
    with pytest.raises(UnsafeSqlError):
        validate("SELECT * FROM pg_catalog.pg_authid")


def test_a_query_reading_no_table_is_rejected() -> None:
    """`SELECT 1` is harmless but is never an answer, and allowing it means allowing
    `SELECT pg_sleep(60)` shaped things through the same door."""
    with pytest.raises(UnsafeSqlError, match="reads no table"):
        validate("SELECT 1")


# --- Banned functions -------------------------------------------------------


def test_pg_sleep_is_rejected() -> None:
    with pytest.raises(UnsafeSqlError, match="pg_sleep"):
        validate("SELECT pg_sleep(60) FROM v_headcount_monthly")


def test_file_reads_are_rejected() -> None:
    with pytest.raises(UnsafeSqlError, match="pg_read_file"):
        validate("SELECT pg_read_file('/etc/passwd') FROM v_headcount_monthly")


@pytest.mark.parametrize(
    "expression",
    ["CURRENT_DATE", "CURRENT_TIMESTAMP", "now()", "clock_timestamp()"],
)
def test_wall_clock_functions_are_rejected(expression: str) -> None:
    """Not a security rule — a correctness one, and a real observed failure. Asked for "the
    last year" the model generated `quarter_start >= CURRENT_DATE - INTERVAL '1 year'`. The
    warehouse ends at a fixed date, so that answer decays daily and eventually returns
    nothing. The message tells the user what to anchor to instead."""
    with pytest.raises(UnsafeSqlError, match="fixed period"):
        validate(f"SELECT * FROM v_headcount_monthly WHERE month_start >= {expression}")


def test_the_clock_message_names_a_real_alternative() -> None:
    """A rejection that does not say what to do instead just moves the dead end."""
    with pytest.raises(UnsafeSqlError) as caught:
        validate("SELECT * FROM v_headcount_monthly WHERE month_start >= CURRENT_DATE")

    assert "max(month_start)" in str(caught.value)


# --- LIMIT ------------------------------------------------------------------


def test_a_missing_limit_is_added() -> None:
    safe = validate("SELECT * FROM v_headcount_monthly")

    assert safe.limit == MAX_ROWS
    assert f"LIMIT {MAX_ROWS}" in safe.sql.upper()


def test_a_smaller_limit_is_kept() -> None:
    """The model asking for 10 rows is a better answer than 500; only the ceiling matters."""
    safe = validate("SELECT * FROM v_headcount_monthly LIMIT 10")

    assert safe.limit == 10


def test_an_oversized_limit_is_clamped() -> None:
    safe = validate("SELECT * FROM v_headcount_monthly LIMIT 100000")

    assert safe.limit == MAX_ROWS


def test_a_limit_survives_order_by() -> None:
    """Appending ` LIMIT 500` as text to a query ending in ORDER BY happens to work; doing
    it to a UNION does not. Rewriting the tree is correct in both cases."""
    safe = validate("SELECT month_start FROM v_headcount_monthly ORDER BY month_start DESC")

    assert safe.limit == MAX_ROWS
    assert safe.sql.upper().rindex("LIMIT") > safe.sql.upper().rindex("ORDER BY")


def test_a_union_gets_one_limit_at_the_end() -> None:
    safe = validate(
        "SELECT department_id FROM v_headcount_monthly "
        "UNION SELECT department_id FROM v_absenteeism_monthly"
    )

    assert safe.sql.upper().count("LIMIT") == 1


# --- Malformed input --------------------------------------------------------


@pytest.mark.parametrize("sql", ["", "   ", "\n"])
def test_empty_sql_is_rejected(sql: str) -> None:
    with pytest.raises(UnsafeSqlError, match="no SQL"):
        validate(sql)


def test_unparseable_sql_is_rejected_with_the_parser_error() -> None:
    with pytest.raises(UnsafeSqlError):
        validate("SELECT FROM WHERE ((((")
