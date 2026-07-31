"""Comment classification, offline.

The interesting logic is not the HTTP call — it is the join that turns N distinct comments
into a row per survey response. In the real warehouse that is 40 classifications populating
1,838 rows, and getting it wrong in either direction is invisible in the chart: too few
rows and volumes are understated, too many and every comment is double-counted.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import comments
from app.ai.provider import AiUnavailableError, Completion
from app.models.ai import AiCache
from app.models.engagement import FactCommentTheme, FactSurveyResponse

MODEL = "test-bulk-model"


@pytest.fixture
def db(test_engine: Engine) -> Iterator[Session]:
    """A session with an empty comment-theme table, restored afterwards.

    `tiny_org` seeds two `fact_comment_theme` rows, and `test_metrics_engagement` asserts
    on them. `classify` commits, so a plain rollback will not undo these tests — the rows
    are snapshotted and put back instead. Deleting without restoring broke an unrelated
    engagement test, which is how this was found.
    """
    factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        seeded = [
            {
                "survey_response_id": row.survey_response_id,
                "theme": row.theme,
                "sentiment": row.sentiment,
                "confidence": row.confidence,
                "model": row.model,
            }
            for row in session.query(FactCommentTheme).all()
        ]
        session.query(FactCommentTheme).delete()
        session.query(AiCache).delete()
        session.commit()

        yield session

        session.rollback()
        session.query(FactCommentTheme).delete()
        session.query(AiCache).delete()
        session.add_all(FactCommentTheme(**values) for values in seeded)
        session.commit()


class FakeProvider:
    """Assigns a theme by position, so an assertion can predict every row."""

    name = "fake"

    def __init__(self) -> None:
        self.calls = 0
        self.last_user_prompt = ""

    def complete_json(self, *, system: str, user: str, schema: dict, model: str, **_: Any):
        self.calls += 1
        self.last_user_prompt = user
        count = sum(1 for line in user.splitlines() if line[:1].isdigit() and ". " in line)
        return Completion(
            data={
                "assignments": [
                    {
                        "index": i,
                        "theme": "Workload" if i % 2 == 0 else "Career Growth",
                        "sentiment": "negative" if i % 2 == 0 else "positive",
                        "confidence": 0.9,
                    }
                    for i in range(count)
                ]
            },
            model=model,
        )


def _distinct_count(session: Session) -> int:
    return len(comments.distinct_comments(session))


def _responses_with_text(session: Session) -> int:
    return session.execute(
        select(func.count())
        .select_from(FactSurveyResponse)
        .where(FactSurveyResponse.open_text.is_not(None))
    ).scalar_one()


# --- The fan-out ------------------------------------------------------------


def test_one_row_is_written_per_response_not_per_distinct_comment(db: Session) -> None:
    """The whole reason classification keys on the text. If this wrote one row per distinct
    comment, theme volumes would be the size of the sentence pool rather than the number of
    people who said it."""
    expected_rows = _responses_with_text(db)
    distinct = _distinct_count(db)
    assert distinct < expected_rows, "fixture must reuse comment text for this to mean anything"

    result = comments.classify(db, provider=FakeProvider(), model=MODEL)

    assert result["distinct_comments"] == distinct
    assert result["rows"] == expected_rows
    assert db.execute(select(func.count()).select_from(FactCommentTheme)).scalar_one() == (
        expected_rows
    )


def test_the_provider_sees_each_comment_once(db: Session) -> None:
    """40 distinct strings must cost 40 classifications, not 1,838."""
    provider = FakeProvider()

    comments.classify(db, provider=provider, model=MODEL)

    numbered = [line for line in provider.last_user_prompt.splitlines() if line[:1].isdigit()]
    assert len(numbered) == _distinct_count(db)


def test_every_row_carries_the_model_that_produced_it(db: Session) -> None:
    """`fact_comment_theme.model` exists for auditability — a theme set has to be
    attributable to the model that wrote it."""
    comments.classify(db, provider=FakeProvider(), model=MODEL)

    models = {row.model for row in db.query(FactCommentTheme).all()}
    assert models == {MODEL}


def test_responses_sharing_text_get_the_same_theme(db: Session) -> None:
    comments.classify(db, provider=FakeProvider(), model=MODEL)

    rows = db.execute(
        select(FactSurveyResponse.open_text, FactCommentTheme.theme).join(
            FactCommentTheme,
            FactCommentTheme.survey_response_id == FactSurveyResponse.response_id,
        )
    ).all()
    by_text: dict[str, set[str]] = {}
    for text, theme in rows:
        by_text.setdefault(text, set()).add(theme)

    assert all(len(themes) == 1 for themes in by_text.values())


# --- Idempotency ------------------------------------------------------------


def test_a_second_run_is_a_no_op(db: Session) -> None:
    """Running the CLI twice must not double every volume in the chart."""
    provider = FakeProvider()
    first = comments.classify(db, provider=provider, model=MODEL)

    second = comments.classify(db, provider=provider, model=MODEL)

    assert second["status"] == "skipped"
    assert second["rows"] == first["rows"]
    assert provider.calls == 1


def test_force_reclassifies_without_duplicating(db: Session) -> None:
    """`--force` deletes before writing. Without the delete the table would accumulate a
    full set of rows on every run."""
    first = comments.classify(db, provider=FakeProvider(), model=MODEL)

    second = comments.classify(db, force=True, provider=FakeProvider(), model="other-model")

    assert second["rows"] == first["rows"]
    assert (
        db.execute(select(func.count()).select_from(FactCommentTheme)).scalar_one()
        == (first["rows"])
    )


def test_the_classification_is_cached_so_a_rebuild_is_free(db: Session) -> None:
    """After a TRUNCATE the table can be rebuilt with no API call, which is what makes a
    demo recoverable on a rate-limited key."""
    provider = FakeProvider()
    comments.classify(db, provider=provider, model=MODEL)
    db.query(FactCommentTheme).delete()
    db.commit()

    result = comments.classify(db, provider=provider, model=MODEL)

    assert provider.calls == 1
    assert result["from_cache"] is True
    assert result["rows"] > 0


# --- Degradation ------------------------------------------------------------


def test_no_provider_raises_a_readable_error(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comments, "get_provider", lambda: None)

    with pytest.raises(AiUnavailableError, match="No AI key configured"):
        comments.classify(db)


def test_an_out_of_range_index_is_ignored_rather_than_crashing(db: Session) -> None:
    """A model that returns index 999 for a 40-comment batch must not take the job down
    with a KeyError half way through writing."""

    class Wild(FakeProvider):
        def complete_json(self, **kwargs: Any):
            return Completion(
                data={
                    "assignments": [
                        {"index": 0, "theme": "Workload", "sentiment": "negative", "confidence": 1},
                        {
                            "index": 999,
                            "theme": "Nowhere",
                            "sentiment": "negative",
                            "confidence": 1,
                        },
                    ]
                },
                model=MODEL,
            )

    result = comments.classify(db, provider=Wild(), model=MODEL)

    assert result["themes"] == ["Workload"]
    assert result["rows"] > 0


def test_an_invalid_sentiment_falls_back_rather_than_violating_the_enum(db: Session) -> None:
    """`sentiment` is a Postgres enum. A value outside it would fail the insert for the
    whole batch, so it is coerced at the boundary."""

    class BadSentiment(FakeProvider):
        def complete_json(self, **kwargs: Any):
            return Completion(
                data={
                    "assignments": [
                        {"index": 0, "theme": "Workload", "sentiment": "furious", "confidence": 1}
                    ]
                },
                model=MODEL,
            )

    result = comments.classify(db, provider=BadSentiment(), model=MODEL)

    assert result["rows"] > 0
    assert {row.sentiment.value for row in db.query(FactCommentTheme).all()} == {"neutral"}
