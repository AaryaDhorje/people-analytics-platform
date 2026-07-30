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

*Resolved in phase 1, but not as written: the user redirected to the PostgreSQL 18 service
already running on the host rather than starting Docker.*

---

## Phase 1 — Schema and warehouse (H1:00–H2:30 allotted)

**Prompt strategy.** `/phase 1`, and this time **plan mode was used** — the opposite call
from phase 0, because a star schema has decisions worth rejecting where a scaffold does not.
No subagents again: `sql-view-author` owns views that do not exist until phase 3, and
`data-generator` is phase 2's. The phase-1 prompt demands walking all four metric domains to
confirm every metric is computable *before* writing models, so that walk was done first and
its output became the plan rather than a formality afterwards. It surfaced four decisions that
were put to the user as explicit questions instead of assumed: three metrics with no source
table, "team" not being a dimension, whether the two AI cache tables land now or later, and
which database to migrate against.

**Accepted.** The coverage walk earned its place immediately — Revenue per FTE, Output per
Head, and Training Hours had **no source table** anywhere in the phase-1 fact list, so writing
models straight from that list would have left three catalogued metrics silently uncomputable
until someone tried to implement them in phase 3. `fact_department_revenue`, `fact_training`,
and two columns on `fact_timesheet_week` close the gap for about 35 lines. The
average-headcount rule became *structural*: the snapshot stores `active_at_month_start` and
`active_at_month_end` as separate booleans, so the correct denominator is the one that is
easiest to reach for, and a test asserts both columns exist and are non-nullable. Type-1
dimensions plus `fact_employment_event` for history means attrition-by-manager attributes an
exit to the manager who held the report at the time rather than to whoever inherited the team.
Stage events store entry *and* exit so pipeline dwell time is a subtraction. Driver scores stay
raw 1–5 and normalize to 0–100 in views only, because the planted scenarios are written in
0–100 points and normalization drifting across two places would stop those numbers reconciling.

**Rejected.** Six things. (1) **The autogenerated migration as shipped.** It applied cleanly,
which is exactly the trap — round-tripping it revealed Alembic emits `CREATE TYPE` for native
enums on first use but never a matching `DROP`, so `downgrade base` left all 10 types orphaned
and the next `upgrade head` died with `DuplicateObject: type "channel_type" already exists`. A
one-way migration would have blocked phase 2, which regenerates the database repeatedly. Fixed
with an explicit `ENUM_TYPE_NAMES` loop, and hand edits were confined to enum lifecycle — never
to column definitions, which is where models and migration actually drift apart. Worth noting
the sequencing: the bug was found by *testing the downgrade*, not by reading the file, and
reading the file would not have found it. (2) **Writing models from the plan's fact list**, per
the coverage walk above. (3) **About 25 ORM relationships** that the pattern invites — one per
foreign key. Metrics read through SQL views, so all but one would be dead weight plus
mapper-config risk; `DimEmployee.manager`/`reports` survived because span-of-control and the
manager rollup both walk that edge, and a test asserts the self-reference resolves.
(4) **Docker as the local database.** Phase 0 ended blocked on Docker Desktop; the user
redirected to the PostgreSQL 18 service already on the host. `docker-compose.yml` was demoted
to an optional fallback on port 5433 rather than deleted, so it cannot collide with the host
service but still works on a machine with no Postgres. (5) **Storing rates, and storing
pre-normalized driver scores** — both rejected for numerator/denominator columns and raw 1–5,
so the denominator stays auditable and normalization lives in one place. (6) A **bug in my own
test**: `Settings(DATABASE_URL=url)` passes the env-var name where the field is `database_url`,
and `extra="ignore"` silently discarded it, so the assertion ran against the default value.

**Bugs found in phase 0's work.** Two, both invisible until a real database existed.
`CORS_ORIGINS` could never have been read from a `.env` file at all: pydantic-settings treats
list-typed fields as complex and attempts `json.loads()` on the raw value *before* validators
run, so `CORS_ORIGINS=http://localhost:5173` raised `SettingsError` and the `mode="before"`
validator never saw it. It passed all of phase 0 only because no `.env` existed and the default
always won — the setting was never actually exercised. Fixed with
`Annotated[list[str], NoDecode]` plus six regression tests. Separately, the `#` in the Postgres
password had to be percent-encoded as `%23`, or everything from `#` parses as a URL fragment
and the password truncates silently, presenting as an auth failure rather than a parsing bug.

**Numbers.** 17 files (10 new, 7 modified). 25 tests passing, up from 4 — 15 schema guards
asserted against metadata with no database connection needed, 6 config tests, 4 health. 3
endpoints live, and `/health/db` returns 200 for the first time. In the live database: 21
tables, 172 columns, 38 foreign keys, 10 enum types, 60 indexes — every count reconciled
against the ERD rather than against the models. `alembic check` reports no drift;
downgrade→upgrade round-trips cleanly.

**Blockers.** None carried into phase 2. Two open items: `ANTHROPIC_API_KEY` is still empty
(needed in phase 6), and the database password appears in this session's transcript, so it
should be rotated if the session is ever shared.
