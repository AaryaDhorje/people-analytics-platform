"""Batch theme extraction over open-text survey comments.

Writes `fact_comment_theme`, which is the only table in the warehouse an AI feature
populates and the reason `/api/engagement/themes` has been returning no rows since phase 3.
It is a CLI job rather than an endpoint on purpose: BUILD_PLAN section 6 requires the
dashboard never to wait on a live call, and classification is a batch problem with a
cacheable answer, not a per-request one.

**Classification keys on the distinct text, not on the response.** The warehouse holds
1,838 comments drawn from a pool of 40 distinct sentences. Classifying per response would
be 1,838 requests to answer 40 questions, and on a free-tier key that is every rate limit
at once. So: classify each distinct string once, then fan the result back out across every
response carrying it.

**One taxonomy, not one per batch.** Themes are established in the first call and passed
into later ones. Independently classifying two batches produces two disjoint vocabularies —
"Workload" and "Work-life balance" as separate bars — which makes the chart useless: the
whole value of a theme is that it aggregates.

Run it with:

    python -m app.ai.comments            # no-op if already classified
    python -m app.ai.comments --force    # reclassify from scratch
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai.cache import get_or_call
from app.ai.provider import AiUnavailableError, get_provider
from app.config import settings
from app.db import SessionLocal
from app.models.engagement import FactCommentTheme, FactSurveyResponse
from app.models.enums import Sentiment

log = logging.getLogger(__name__)

FEATURE = "comments"

#: How many distinct comments go in one request. Comfortably inside the context window; the
#: limit exists so a larger corpus degrades into several calls rather than one that fails.
CHUNK_SIZE = 60

#: Bounds on the vocabulary. Too few and everything collapses into one catch-all; too many
#: and each bar has a volume of one, which is a list of comments wearing a chart's clothes.
#: The floor was raised from 5 after the first run put 54% of all comments into a single
#: "Tooling And Process" bucket that had absorbed an unrelated cluster about a reorg.
MIN_THEMES = 6
MAX_THEMES = 10

_SENTIMENTS = [s.value for s in Sentiment]

SYSTEM_PROMPT = """\
You are classifying anonymous employee engagement survey comments for an HR analytics \
dashboard.

For each comment, assign exactly one theme and one sentiment.

Themes:
- Use a short noun phrase in Title Case, at most four words: "Workload", "Career Growth", \
"Manager Support", "Compensation".
- A theme names the *subject* a group of comments is about. Merge two themes only when a \
reader would struggle to tell them apart — never merely because one is the closest \
available bucket.
- Split rather than merge when a group of comments shares a specific subject of its own. \
Several comments about the same organisational change are their own theme, not an example \
of a general one.
- Never let one theme absorb most of the set. If a theme is heading past a third of all \
comments, it is doing too much work and the distinct subjects inside it should be separated.
- A comment expressing no real opinion belongs in a general theme with neutral sentiment, \
not in whichever specific theme it is nearest to.
- Aim for between {min_themes} and {max_themes} themes across the whole set.

Sentiment is how the employee feels about the thing they are describing, one of: \
{sentiments}. Use "mixed" only when a comment is genuinely both positive and negative \
about the same subject; use "neutral" for factual remarks with no clear valence.

Confidence is 0.0-1.0 and should reflect real uncertainty. A vague comment classified into \
the nearest theme deserves a low confidence, not a high one.

Return one assignment per input comment, in the same order, using the given index."""


@dataclass(frozen=True, slots=True)
class Assignment:
    theme: str
    sentiment: str
    confidence: float


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "The comment's index"},
                        "theme": {"type": "string"},
                        "sentiment": {"type": "string", "enum": _SENTIMENTS},
                        "confidence": {"type": "number"},
                    },
                    "required": ["index", "theme", "sentiment", "confidence"],
                },
            }
        },
        "required": ["assignments"],
    }


def distinct_comments(db: Session) -> list[str]:
    """Every distinct non-empty comment, ordered so the batch is reproducible."""
    stmt = (
        select(FactSurveyResponse.open_text)
        .where(FactSurveyResponse.open_text.is_not(None))
        .where(func.length(func.trim(FactSurveyResponse.open_text)) > 0)
        .distinct()
        .order_by(FactSurveyResponse.open_text)
    )
    return [row[0] for row in db.execute(stmt).all()]


def _classify_chunk(
    provider: Any, model: str, comments: list[str], known_themes: list[str]
) -> dict[int, Assignment]:
    vocabulary = (
        "Themes already in use — reuse these wherever a comment fits:\n"
        + "\n".join(f"- {t}" for t in sorted(known_themes))
        if known_themes
        else "No themes exist yet. Establish them from this set."
    )
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(comments))
    user = f"{vocabulary}\n\nComments:\n{numbered}"

    completion = provider.complete_json(
        system=SYSTEM_PROMPT.format(
            min_themes=MIN_THEMES, max_themes=MAX_THEMES, sentiments=", ".join(_SENTIMENTS)
        ),
        user=user,
        schema=_schema(),
        model=model,
    )

    out: dict[int, Assignment] = {}
    for raw in completion.data.get("assignments", []):
        try:
            index = int(raw["index"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= index < len(comments):
            continue
        sentiment = str(raw.get("sentiment", "")).strip().lower()
        if sentiment not in _SENTIMENTS:
            # The schema constrains this, but a wrong value must not become a database
            # constraint violation half way through a batch.
            sentiment = Sentiment.NEUTRAL.value
        out[index] = Assignment(
            theme=str(raw.get("theme", "")).strip()[:64] or "Unclassified",
            sentiment=sentiment,
            confidence=_clamp(raw.get("confidence")),
        )
    return out


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def classify(
    db: Session,
    *,
    force: bool = False,
    provider: Any | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Classify every distinct comment and write one row per survey response.

    Idempotent: a second run with existing rows is a no-op unless `force` is set.

    `provider` and `model` are injectable so the tests can drive the whole fan-out with a
    stub and stay offline — the interesting logic here is the distinct-text join, not the
    HTTP call.
    """
    existing = db.execute(select(func.count()).select_from(FactCommentTheme)).scalar_one()
    if existing and not force:
        return {
            "status": "skipped",
            "reason": f"{existing} rows already classified",
            "rows": existing,
        }

    provider = provider or get_provider()
    if provider is None:
        raise AiUnavailableError(
            "No AI key configured. Set GOOGLE_API_KEY or ANTHROPIC_API_KEY in backend/.env."
        )

    model = model or settings.resolved_models[1]
    if not model:
        raise AiUnavailableError("No bulk model resolved; set MODEL_BULK.")

    comments = distinct_comments(db)
    if not comments:
        return {"status": "empty", "reason": "no open-text comments in the warehouse", "rows": 0}

    # Cached on the exact corpus, so re-running after a TRUNCATE costs nothing and a demo
    # can rebuild the table offline.
    def call() -> dict[str, Any]:
        assignments: dict[int, Assignment] = {}
        themes: list[str] = []
        for start in range(0, len(comments), CHUNK_SIZE):
            chunk = comments[start : start + CHUNK_SIZE]
            log.info("classifying comments %d-%d of %d", start, start + len(chunk), len(comments))
            result = _classify_chunk(provider, model, chunk, themes)
            for local_index, assignment in result.items():
                assignments[start + local_index] = assignment
                if assignment.theme not in themes:
                    themes.append(assignment.theme)
        return {
            "assignments": {
                str(i): {"theme": a.theme, "sentiment": a.sentiment, "confidence": a.confidence}
                for i, a in assignments.items()
            }
        }

    cached = get_or_call(
        db, feature=FEATURE, model=model, inputs={"comments": comments}, call=call
    )
    raw_assignments = cached.payload.get("assignments", {})

    by_text: dict[str, Assignment] = {}
    for key, value in raw_assignments.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(comments):
            by_text[comments[index]] = Assignment(
                theme=value["theme"],
                sentiment=value["sentiment"],
                confidence=float(value["confidence"]),
            )

    unclassified = [c for c in comments if c not in by_text]
    if unclassified:
        log.warning("%d comments came back unclassified and are skipped", len(unclassified))

    return _write_rows(db, by_text, model=model, cached=cached.cached, force=force)


def _write_rows(
    db: Session, by_text: dict[str, Assignment], *, model: str, cached: bool, force: bool
) -> dict[str, Any]:
    """Fan the per-text classification out across every response carrying that text.

    The join is on the text, which is why 40 classifications populate 1,838 rows.
    """
    if force:
        db.execute(delete(FactCommentTheme))
        db.commit()

    stmt = select(FactSurveyResponse.response_id, FactSurveyResponse.open_text).where(
        FactSurveyResponse.open_text.is_not(None)
    )
    rows = [
        FactCommentTheme(
            survey_response_id=response_id,
            theme=assignment.theme,
            sentiment=Sentiment(assignment.sentiment),
            confidence=Decimal(f"{assignment.confidence:.3f}"),
            model=model,
        )
        for response_id, text in db.execute(stmt).all()
        if (assignment := by_text.get(text)) is not None
    ]

    db.add_all(rows)
    db.commit()

    return {
        "status": "classified",
        "distinct_comments": len(by_text),
        "rows": len(rows),
        "themes": sorted({a.theme for a in by_text.values()}),
        "model": model,
        "from_cache": cached,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Delete existing themes and reclassify."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with SessionLocal() as db:
        try:
            result = classify(db, force=args.force)
        except AiUnavailableError as exc:
            print(f"AI unavailable: {exc}", file=sys.stderr)
            return 1

    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
