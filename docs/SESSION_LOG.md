# Session log

One entry per phase: how the work was framed, what was kept, what was thrown away and
why. The rejections are the point — they are what distinguishes directing the tool from
accepting its first answer.

---

## Phase 0 — Foundation (H0:00–H1:00 allotted)

**Prompt strategy.** One scaffolding prompt covering the whole tree: FastAPI +
SQLAlchemy 2.0 + Alembic + pytest + ruff, Vite + React + TS + Tailwind + Recharts +
TanStack Query, docker-compose, `.env.example`, `.gitignore`, a `/health` endpoint, one
smoke test, and an explicit "do not implement any metrics yet." Deliberately **no plan
mode** — scaffolding has no architectural decisions to review, so a plan would have cost
time without surfacing a choice worth rejecting; plan mode starts earning its keep in
phase 1 with the star schema. Deliberately **no subagents**: `frontend-builder` exists
but has nothing to build against, because no endpoint contract exists yet beyond
`/health`, and the phase-0 shell is under a hundred lines. The three spec documents
(`CLAUDE.md`, `docs/METRICS.md`, `docs/BUILD_PLAN.md`) were written *before* this prompt,
so the operating rules constrained the scaffold rather than being retrofitted onto it.

**Accepted.** Alembic reads `DATABASE_URL` from `app.config` instead of `alembic.ini`, so
migrations, the app, and the seed generator cannot drift onto different databases and no
credential ever lands in a tracked file. `/health` deliberately does not touch Postgres —
it is what Render polls during a ~50s cold start — with readiness split out to
`/health/db`, which returns a readable 503 rather than a stack trace. `pool_pre_ping=True`
on the engine, because Neon closes idle connections and the first query afterward would
otherwise fail instead of reconnecting. The `{data, meta}` envelope is enforced by a test
from the very first commit, since 30-odd metric endpoints will inherit it and retrofitting
a response shape later is far more expensive. The design tokens from the build plan went
into `src/index.css` as `@theme` variables *now*, with `--color-risk` commented as
reserved exclusively for risk signals — declaring that before any page exists is what
stops six separate phase-5 prompts from each drifting toward a generic admin template.

**Rejected.** Four things were thrown away. (1) The first `app/main.py` configured CORS
via `allow_origins=settings_cors := __import__("app.config", fromlist=["settings"]).settings.cors_origins`
— a walrus operator wrapped around a dynamic import for no reason whatsoever. Rewritten
immediately as a plain `from app.config import settings`; it was generated noise, not a
design, and the fact that it would have *worked* is exactly why it needed deleting.
(2) Ruff's autofix for `I001` in `alembic/env.py`, which wanted to regroup the `alembic`
import as first-party. The finding was real but the proposed fix encoded a false premise:
`alembic` is third-party, and ruff only thought otherwise because a local `alembic/`
migration directory shadows the package name. Fixed the classification with
`known-third-party = ["alembic"]` instead of accepting a reordering that would have been
wrong in every future file. (3) The stub metric and AI modules that §2's tree implies —
`metrics/acquisition.py`, `ai/nl_query.py`, and six others. Creating them would have meant
eight files containing `pass`, which `CLAUDE.md` forbids outright and the prompt's "no
metrics yet" contradicts. Created the packages with `__init__.py` docstrings that carry the
binding constraints forward instead (average-headcount denominators, `seed=42`, the
NL→SQL allowlist boundary), so the structure exists and the rules travel with it without a
single placeholder. (4) The split `tsconfig.app.json` / `tsconfig.node.json` project-
reference layout that Vite's template ships, collapsed to one `tsconfig.json` to remove a
whole class of build failure — which promptly paid off when TypeScript 7 turned out to have
**removed `baseUrl`** entirely, a one-line fix in one file rather than three.

**Deviations from the plan.** Python **3.11, not 3.12** — 3.12 is not installed on this
machine and the alternative was 3.14, new enough that a missing wheel mid-build was a real
risk. `requires-python` and ruff's `target-version` are pinned to match, and Render must be
set to 3.11.

**Numbers.** 55 files, 5,153 insertions (21 backend, 14 frontend, 9 `.claude/`, 6 root,
5 docs). 4 tests
passing. 3 endpoints live: `/`, `/health`, `/health/db`. `ruff check` clean, `ruff format
--check` clean, `tsc --noEmit` clean, `vite build` green in 245ms.

**Blocker carried into phase 1.** Docker Desktop is installed (29.3.1) but its engine is
not running, so `docker compose up -d db` fails and **no migration has ever run against a
live database**. `docker-compose.yml` validates statically and `env.py` resolves the URL
with 0 tables registered (correct for phase 0), but phase 1 ends by applying a migration
and must not be where a connection problem is first discovered.
