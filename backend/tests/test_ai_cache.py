"""The AI response cache.

No network. `call` is a closure, so these tests drive it with a counter — which is the
point of the design: the cache knows nothing about how an answer is produced.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.cache import cache_key, get_or_call, invalidate
from app.ai.provider import AiUnavailableError
from app.models.ai import AiCache

FEATURE = "narrative"
MODEL = "test-model-a"


@pytest.fixture
def cache_db(test_engine: Engine) -> Iterator[Session]:
    """A session with an empty `ai_cache`.

    Metric tests are read-only and share one seeded database; these write, so the table is
    cleared around each test rather than leaking rows into the next one.
    """
    factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        session.query(AiCache).delete()
        session.commit()
        yield session
        session.query(AiCache).delete()
        session.commit()


class Counter:
    """Stands in for a provider call, recording how often it ran."""

    def __init__(self, payload: dict | None = None, fail: bool = False) -> None:
        self.calls = 0
        self._payload = payload if payload is not None else {"bullets": ["a", "b"]}
        self._fail = fail

    def __call__(self) -> dict:
        self.calls += 1
        if self._fail:
            raise AiUnavailableError("provider down")
        return self._payload


INPUTS = {"department_id": 1, "date_from": "2026-01-01"}


# --- The key ----------------------------------------------------------------


def test_key_is_stable_across_dict_ordering() -> None:
    """Without `sort_keys` the same question hashes differently depending on how the dict
    was built, and the cache silently never hits."""
    a = cache_key(FEATURE, MODEL, {"a": 1, "b": 2})
    b = cache_key(FEATURE, MODEL, {"b": 2, "a": 1})

    assert a == b


def test_key_changes_with_the_model() -> None:
    """Switching model must miss. The two are not interchangeable, and the response records
    which one produced it."""
    assert cache_key(FEATURE, "model-a", INPUTS) != cache_key(FEATURE, "model-b", INPUTS)


def test_key_changes_with_the_inputs() -> None:
    assert cache_key(FEATURE, MODEL, {"department_id": 1}) != cache_key(
        FEATURE, MODEL, {"department_id": 2}
    )


def test_key_changes_with_the_feature() -> None:
    assert cache_key("narrative", MODEL, INPUTS) != cache_key("ask", MODEL, INPUTS)


# --- Read-through -----------------------------------------------------------


def test_a_miss_calls_once_and_stores(cache_db: Session) -> None:
    counter = Counter()

    result = get_or_call(cache_db, feature=FEATURE, model=MODEL, inputs=INPUTS, call=counter)

    assert counter.calls == 1
    assert result.cached is False
    assert result.payload["bullets"] == ["a", "b"]
    assert cache_db.get(AiCache, cache_key(FEATURE, MODEL, INPUTS)) is not None


def test_a_hit_does_not_call(cache_db: Session) -> None:
    counter = Counter()
    get_or_call(cache_db, feature=FEATURE, model=MODEL, inputs=INPUTS, call=counter)

    second = get_or_call(cache_db, feature=FEATURE, model=MODEL, inputs=INPUTS, call=counter)

    assert counter.calls == 1
    assert second.cached is True
    assert second.payload["bullets"] == ["a", "b"]


def test_a_hit_increments_the_counter(cache_db: Session) -> None:
    """`hits` is what lets the pre-warm script report which entries the demo path actually
    touched, instead of assuming."""
    counter = Counter()
    for _ in range(3):
        get_or_call(cache_db, feature=FEATURE, model=MODEL, inputs=INPUTS, call=counter)

    row = cache_db.get(AiCache, cache_key(FEATURE, MODEL, INPUTS))
    assert row is not None
    assert row.hits == 2  # three requests: one miss that stored, two hits


def test_different_filters_are_different_entries(cache_db: Session) -> None:
    """The narrative is per slice. Serving the company summary for a filtered view would be
    confidently wrong, which is worse than being slow."""
    counter = Counter()

    get_or_call(cache_db, feature=FEATURE, model=MODEL, inputs={"department_id": 1}, call=counter)
    get_or_call(cache_db, feature=FEATURE, model=MODEL, inputs={"department_id": 2}, call=counter)

    assert counter.calls == 2


# --- Degradation ------------------------------------------------------------


def test_a_failure_with_no_prior_entry_propagates(cache_db: Session) -> None:
    """Nothing to fall back to, so the caller decides — it turns this into
    `available: false` rather than a 500."""
    with pytest.raises(AiUnavailableError):
        get_or_call(cache_db, feature=FEATURE, model=MODEL, inputs=INPUTS, call=Counter(fail=True))


def test_a_failure_falls_back_to_an_entry_from_another_model(cache_db: Session) -> None:
    """The realistic outage: the key changed because the model changed, and the provider is
    down so the new key cannot be filled. A slightly old answer beats a blank panel, and it
    is flagged rather than passed off as fresh."""
    get_or_call(cache_db, feature=FEATURE, model="model-a", inputs=INPUTS, call=Counter())

    result = get_or_call(
        cache_db, feature=FEATURE, model="model-b", inputs=INPUTS, call=Counter(fail=True)
    )

    assert result.stale is True
    assert result.cached is True
    assert result.model == "model-a"
    assert result.payload["bullets"] == ["a", "b"]


def test_the_stale_fallback_does_not_cross_questions(cache_db: Session) -> None:
    """A stale answer to a *different* question is not a degraded answer, it is a wrong
    one. Only the same inputs qualify."""
    get_or_call(
        cache_db, feature=FEATURE, model="model-a", inputs={"department_id": 1}, call=Counter()
    )

    with pytest.raises(AiUnavailableError):
        get_or_call(
            cache_db,
            feature=FEATURE,
            model="model-b",
            inputs={"department_id": 99},
            call=Counter(fail=True),
        )


# --- Invalidation -----------------------------------------------------------


def test_invalidate_clears_one_feature_only(cache_db: Session) -> None:
    """A prompt edit does not change the cache key, so without this the old answer outlives
    the change meant to improve it."""
    get_or_call(cache_db, feature="narrative", model=MODEL, inputs=INPUTS, call=Counter())
    get_or_call(cache_db, feature="ask", model=MODEL, inputs=INPUTS, call=Counter())

    removed = invalidate(cache_db, feature="narrative")

    assert removed == 1
    assert cache_db.query(AiCache).count() == 1
