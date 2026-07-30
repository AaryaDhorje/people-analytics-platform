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

---

## Phase 2 — Synthetic data with planted signal (H2:30–H4:30 allotted)

**Prompt strategy.** `/phase 2`, plan mode again. BUILD_PLAN §6 says to use the
`data-generator` subagent, and that was **put back to the user rather than followed**: the
subagent starts with no knowledge of the 21 tables built an hour earlier, and column-name drift
is the dominant failure mode for a 1,500-line insert script across 21 tables. Written inline
instead, with the subagent definition left committed as the record of the method that was
considered. Three other decisions were surfaced as explicit questions instead of assumed — the
three metrics with no source table, what "team" means, and which database to target — and a
`--scale` flag was added for fast iteration.

**Accepted.** The split between *forced* and *sampled* generation is what makes this work.
Ambient texture — department base rates, tenure curves, channel effects — comes from relative
monthly hazard weights. Anything the Loom says out loud is forced exactly: M-114 has precisely
six exits with precisely four rated 4+, because "four of his six leavers were high performers"
is a sentence spoken on camera and a sampled 5-of-7 would make the narration wrong. Exit
totals come from **weighted sampling without replacement to an exact count**, so the plan's
volumes hold precisely while relative patterns stay realistic; a per-month coin flip would have
produced a different headcount every time a hazard was tuned. Scenario targets live in
`scenarios.py` as typed dataclasses carrying a target *and* a tolerance, and `validate.py`
recomputes each one from the database in raw SQL written from docs/METRICS.md rather than from
generator helpers — reusing the generator's own code would only confirm it agrees with itself.
Hours were derived by solving the metric definitions backwards: overtime rate 0.22 implies
40 / 0.78 = 51.3 total hours, and utilization 0.96 implies 38.4 billable of 40 available.
Choosing hours first and hoping the ratios landed would have satisfied at most one of scenario
5's two targets.

**Rejected.** The single most valuable rejection this phase was **the first run's output**.
It completed cleanly, inserted 29,175 rows, and passed only two of six scenarios — and every
one of the four failures was a real bug that reading the code would not have surfaced.
(1) M-114 had **~30 reports, not 14**: `_assign_bad_manager_team` added reports but never
removed M-114 from the general round-robin pool, so two-thirds of the team carried no planted
signal. That diluted the manager-driver gap from 28 points to 22 and pushed the attrition
ratio to **0.99 — parity with the company**, meaning the headline demo moment was invisible in
its own chart. (2) Agency 12-month retention measured **33% against a 62% target**: stage 2
forced the exact channel exits, then stage 4's sampling added *more* exits inside the same
12-month horizon. Fixed by confining sampling for measured cohorts to months after the horizon
closes. (3) Time to fill measured **183 days against 74**: multi-opening requisitions batched
hires that were weeks apart, dragging `opened_date` backwards. (4) The reorg was transferring
outsiders *onto* M-114's team, which is why exits read 7 instead of the forced 6. Beyond the
data, four design choices were discarded: the plan's **410 requisitions** (one opening per req
is what makes time-to-fill exact, and TTF is asserted where the req count is not, so the count
rose to 770); my own **18-person team size** for M-114, resized to 14 against *measured*
company attrition of ~29% in the final three quarters rather than the 18% window average; a
**flat −28 driver offset**, split into a separate applied offset of 33 because Engineering sits
above the company mean on that driver and the mean being compared against includes the affected
team; and the **data-generator subagent** itself.

**The transferable lesson.** Both phases have now found their most serious bug by *running*
something rather than reading it — the migration by round-tripping a downgrade, the generator
by validating its output. In both cases the artifact looked correct and executed without error.
This is the argument for the validation report existing at all.

**Numbers.** 14 files (12 new under `backend/seed/` plus tests, 2 docs updated). 66 tests
passing, up from 25 — 25 new no-DB guards on scenario definitions, mix tables that must sum to
1, and the four snapshot activity flags. 3 endpoints live. **216,432 rows across 21 tables in
27s**, checksum `f7b0b9400782c277` identical across two consecutive full runs. Headcount runs
1,150 → 1,200 as designed, with 39 exits in March 2026 against a 10-16 baseline — the
post-reorg spike, visible without being pointed at. All six scenarios PASS.

**Blockers.** None for phase 3. Two notes: company time to fill measures 43.8 days against the
plan's 38 and passes only at the edge of its ±6 tolerance (Sales' 74 is exact), and
`ANTHROPIC_API_KEY` is still empty for phase 6.
