"""NL→SQL, driven by a fake provider.

The live model is well behaved — six adversarial questions were refused by the prompt alone.
That is not what these tests check. They check what happens when the prompt *fails*: the
guard must reject the model's SQL regardless of how the model was asked, because a prompt is
a request and a validator is a rule. Confusing the two is how these features go wrong.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai import nl_query
from app.ai.nl_query import ask
from app.ai.provider import AiUnavailableError, Completion
from app.models.ai import AiCache

MODEL = "test-reasoning-model"


@pytest.fixture
def db(test_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        session.query(AiCache).delete()
        session.commit()
        yield session
        session.rollback()
        session.query(AiCache).delete()
        session.commit()


class Fake:
    """Returns whatever answer the test wants the model to have produced."""

    name = "fake"

    def __init__(self, **answer: Any) -> None:
        self.answer = {
            "sql": "",
            "explanation": "",
            "refused": False,
            "refusal_reason": "",
            **answer,
        }
        self.calls = 0
        self.last_system = ""

    def complete_json(self, *, system: str, user: str, schema: dict, model: str, **_: Any):
        self.calls += 1
        self.last_system = system
        return Completion(data=dict(self.answer), model=model)


# --- The happy path ---------------------------------------------------------


def test_a_valid_query_runs_and_returns_rows(db: Session) -> None:
    provider = Fake(
        sql="SELECT month_start, active_end FROM v_headcount_monthly ORDER BY month_start",
        explanation="Month-end headcount over the window.",
    )

    result = ask(db, "how has headcount changed?", provider=provider)

    assert result.refused is False, result.refusal_reason
    assert result.row_count > 0
    assert "month_start" in result.columns
    assert result.tables == ("v_headcount_monthly",)


def test_the_sql_is_returned_with_the_answer(db: Session) -> None:
    """The auditability requirement. An answer whose query you cannot see is a number to be
    taken on faith, which is the thing this product exists not to ask for."""
    provider = Fake(sql="SELECT month_start FROM v_headcount_monthly")

    result = ask(db, "headcount please", provider=provider)

    assert result.sql is not None
    assert "v_headcount_monthly" in result.sql
    assert "LIMIT" in result.sql.upper()


def test_a_missing_limit_is_imposed_before_execution(db: Session) -> None:
    provider = Fake(sql="SELECT month_start FROM v_headcount_monthly")

    result = ask(db, "headcount", provider=provider)

    assert result.row_count <= nl_query.MAX_ROWS


# --- The model refusing -----------------------------------------------------


def test_a_model_refusal_is_passed_through_without_touching_the_database(db: Session) -> None:
    provider = Fake(refused=True, refusal_reason="The warehouse holds no salary data.")

    result = ask(db, "what is everyone paid?", provider=provider)

    assert result.refused is True
    assert "salary" in result.refusal_reason
    assert result.sql is None
    assert result.rows == []


def test_a_refusal_with_no_reason_still_says_something(db: Session) -> None:
    """An empty refusal renders as a blank panel, which reads as a bug rather than an
    answer."""
    result = ask(db, "?", provider=Fake(refused=True, refusal_reason=""))

    assert result.refusal_reason


# --- The model misbehaving --------------------------------------------------
#
# The prompt asked for none of these. The guard is what makes them safe anyway.


@pytest.mark.parametrize(
    ("label", "sql"),
    [
        ("a base table", "SELECT * FROM dim_employee"),
        ("a write", "DELETE FROM fact_survey_response"),
        ("stacked statements", "SELECT 1 FROM v_headcount_monthly; DROP TABLE dim_employee"),
        ("the non-queryable view", "SELECT * FROM v_flight_risk_inputs"),
        (
            "a wall-clock anchor",
            "SELECT * FROM v_headcount_monthly WHERE month_start > CURRENT_DATE",
        ),
        ("a table behind a comment", "SELECT * FROM /* v_headcount_monthly */ dim_employee"),
    ],
)
def test_unsafe_model_output_is_rejected_by_the_guard(db: Session, label: str, sql: str) -> None:
    result = ask(db, f"do something involving {label}", provider=Fake(sql=sql))

    assert result.refused is True, f"{label} was not rejected"
    assert result.rows == []
    # The rejected SQL is shown, so the refusal is checkable rather than mysterious.
    assert result.sql == sql


def test_empty_sql_from_the_model_is_a_refusal_not_a_crash(db: Session) -> None:
    result = ask(db, "anything", provider=Fake(sql="", refused=False))

    assert result.refused is True


def test_sql_that_is_valid_but_fails_to_run_is_reported_not_raised(db: Session) -> None:
    """A column that does not exist passes the guard — the guard checks tables, not
    columns — and fails in Postgres. That has to reach the user as a message."""
    provider = Fake(sql="SELECT no_such_column FROM v_headcount_monthly")

    result = ask(db, "something", provider=provider)

    assert result.refused is True
    assert "failed to run" in result.refusal_reason


def test_a_failed_query_leaves_the_session_usable(db: Session) -> None:
    """A read-only transaction left open would poison every later request on a pooled
    connection — the next caller would get InFailedSqlTransaction from unrelated code."""
    ask(db, "bad", provider=Fake(sql="SELECT nope FROM v_headcount_monthly"))

    good = ask(db, "good", provider=Fake(sql="SELECT month_start FROM v_headcount_monthly"))

    assert good.refused is False
    assert good.row_count > 0


def test_the_read_only_flag_does_not_leak_into_later_writes(db: Session) -> None:
    """`SET LOCAL transaction_read_only` must not survive the transaction it was set in."""
    ask(db, "read", provider=Fake(sql="SELECT month_start FROM v_headcount_monthly"))

    db.add(AiCache(cache_key="probe", feature="probe", model="m", payload={}))
    db.commit()

    assert db.get(AiCache, "probe") is not None


# --- Caching ----------------------------------------------------------------


def test_the_same_question_is_only_sent_once(db: Session) -> None:
    provider = Fake(sql="SELECT month_start FROM v_headcount_monthly")

    ask(db, "How has headcount changed?", provider=provider)
    second = ask(db, "how has headcount CHANGED?", provider=provider)

    # Case-insensitive: the same question typed differently is the same question.
    assert provider.calls == 1
    assert second.cached is True


def test_rows_are_not_cached_only_the_sql_is(db: Session) -> None:
    """The warehouse can change under a cached question. Re-running the query is cheap;
    serving numbers that are quietly out of date is not."""
    provider = Fake(sql="SELECT month_start FROM v_headcount_monthly")

    first = ask(db, "headcount", provider=provider)
    second = ask(db, "headcount", provider=provider)

    assert second.cached is True
    assert second.row_count == first.row_count > 0  # re-executed, not replayed


# --- Configuration ----------------------------------------------------------


def test_no_provider_raises_so_the_route_can_report_it(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(nl_query, "get_provider", lambda: None)

    with pytest.raises(AiUnavailableError, match="AI key"):
        ask(db, "anything")


def test_an_empty_question_is_rejected_before_any_call(db: Session) -> None:
    provider = Fake()

    with pytest.raises(ValueError, match="question is required"):
        ask(db, "   ", provider=provider)

    assert provider.calls == 0


# --- The prompt -------------------------------------------------------------


def test_the_prompt_describes_the_real_schema(db: Session) -> None:
    """Built from information_schema rather than maintained by hand, so it cannot drift
    into describing columns that no longer exist."""
    provider = Fake(sql="SELECT month_start FROM v_headcount_monthly")

    ask(db, "headcount", provider=provider)

    assert "v_headcount_monthly(" in provider.last_system
    assert "headcount_months" in provider.last_system
    # The non-queryable view must not be advertised.
    assert "v_flight_risk_inputs(" not in provider.last_system


def test_the_prompt_states_the_average_headcount_rule(db: Session) -> None:
    """CLAUDE.md's single most important metric rule. If the model never hears it, it will
    divide by end-of-period headcount, which is the most common bug in HR analytics."""
    provider = Fake(sql="SELECT month_start FROM v_headcount_monthly")

    ask(db, "headcount", provider=provider)

    assert "AVERAGE headcount" in provider.last_system
    assert "never" in provider.last_system.lower()


def test_the_prompt_forbids_wall_clock_anchoring(db: Session) -> None:
    """A real observed failure, not a hypothetical: the model's first generated query used
    `CURRENT_DATE - INTERVAL '1 year'`."""
    provider = Fake(sql="SELECT month_start FROM v_headcount_monthly")

    ask(db, "headcount", provider=provider)

    assert "CURRENT_DATE" in provider.last_system
    assert "max(month_start)" in provider.last_system
