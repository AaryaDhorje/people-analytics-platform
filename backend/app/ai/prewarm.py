"""Fill the AI cache before a demo.

Every AI response is cached, which means the *first* person to visit a slice pays for it.
On a Render free tier that person is whoever is watching the recording, and on a Gemini
free tier the payment might be a 429. So the demo path is warmed deliberately rather than
by hoping nobody clicks first.

**The number that makes this mandatory: 20 requests per day, per model.** Not per minute —
`GenerateRequestsPerDayPerProjectPerModel-FreeTier` is 20, and warming these six answers
plus a few iterations exhausted `gemini-3.6-flash` for a whole day. Consequences worth
knowing before a recording:

- The cache is not an optimisation here, it is the only thing that makes the feature
  demonstrable. An unwarmed question fails, full stop.
- Each model has its own bucket, so switching `MODEL_REASONING` buys a fresh 20 and
  re-keys the cache, regenerating every entry. That is the escape hatch when a day's quota
  is gone; the previous model's entries stay behind as the stale fallback.
- Asking a question that is not in `EXAMPLE_QUESTIONS` spends one of the 20. Improvising
  on camera is a real risk, not a hypothetical.

Run it after `alembic upgrade head` and before recording:

    python -m app.ai.prewarm
    python -m app.ai.prewarm --force    # discard and regenerate, e.g. after a prompt edit
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.ai import narrative, nl_query
from app.ai.cache import invalidate
from app.ai.provider import AiUnavailableError
from app.db import SessionLocal
from app.metrics.filters import MetricFilters

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop the cached answers first. A prompt edit does not change the cache key, "
        "so without this the old answer survives the change meant to improve it.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    failures = 0

    with SessionLocal() as db:
        if args.force:
            for feature in (narrative.SUMMARY_FEATURE, nl_query.FEATURE):
                print(f"dropped {invalidate(db, feature=feature)} cached {feature} entries")

        # The unfiltered slice: what the landing page requests on load.
        try:
            summary = narrative.executive_summary(db, MetricFilters())
            print(f"narrative  {'cached' if summary.cached else 'generated'}  {summary.headline}")
        except AiUnavailableError as exc:
            print(f"narrative  FAILED  {exc}", file=sys.stderr)
            failures += 1

        for spec in nl_query.EXAMPLE_QUESTIONS:
            question = spec["question"]
            try:
                result = nl_query.ask(db, question)
            except AiUnavailableError as exc:
                print(f"ask        FAILED  {question}\n           {exc}", file=sys.stderr)
                failures += 1
                continue
            state = "cached" if result.cached else "generated"
            outcome = "refused" if result.refused else f"{result.row_count} rows"
            print(f"ask        {state}  {outcome:<10} {question}")

    if failures:
        print(f"\n{failures} item(s) failed to warm.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
