# Architecture

Updated at the end of each phase. **Current state: phase 3 (metrics layer) complete.**

## System shape

```mermaid
flowchart LR
  subgraph client["Frontend — Vercel"]
    UI["React 19 + TypeScript<br/>Tailwind v4 · Recharts"]
    RQ["TanStack Query<br/>60s stale time"]
    UI --> RQ
  end

  subgraph api["Backend — Render"]
    R["FastAPI routes<br/>thin, no computation"]
    M["app/metrics/<br/>one module per domain"]
    AI["app/ai/<br/>NL→SQL · narrative · comments"]
    R --> M
    R --> AI
  end

  subgraph data["PostgreSQL 18<br/>local host service · Neon in prod"]
    V["sql/views/<br/>analytical views"]
    T["star schema<br/>8 dimensions · 13 facts"]
    V --> T
  end

  C["Claude API<br/>sonnet-5 · haiku-4.5"]

  RQ -->|"HTTPS + bearer · {data, meta}"| R
  M --> V
  AI --> V
  AI <--> C
```

## Layer responsibilities

| Layer | Owns | Never does |
|---|---|---|
| `app/api/routes/` | Input validation, filter parsing, envelope wrapping | Compute a metric |
| `app/metrics/` | Every formula in `docs/METRICS.md` | Touch HTTP concerns |
| `sql/views/` | Pre-aggregation to metric grain; the NL→SQL allowlist boundary | Expose base tables to generated SQL |
| `app/ai/` | Claude calls, caching, graceful degradation | Compute a metric itself |
| `frontend/` | All formatting — percent, currency, rounding, dates | Recompute a metric client-side |

---

## ERD

21 tables: 8 dimensions, 13 facts. Grain is stated in every table's SQL `COMMENT`.

```mermaid
erDiagram
  dim_date {
    date day PK
    smallint year
    smallint quarter
    smallint month
    date month_start
    date month_end
    date quarter_start
    date week_start
    smallint iso_week
    smallint day_of_week
    boolean is_workday
    boolean is_month_end
    int tenure_day_index
  }

  dim_department {
    smallint department_id PK
    string code UK
    string name
    boolean is_billable
    boolean carries_revenue
  }

  dim_location {
    smallint location_id PK
    string code UK
    string name
    string city
    string country
    string region
  }

  dim_job_level {
    smallint job_level_id PK
    string code UK
    string name
    smallint rank
    numeric comp_band_min
    numeric comp_band_max
    boolean is_manager_level
  }

  dim_source {
    smallint source_id PK
    string code UK
    string name
    enum channel_type
  }

  dim_employee {
    string employee_id PK
    string display_name
    string manager_id FK
    date hire_date
    date termination_date
    enum termination_type
    string termination_reason
    smallint department_id FK
    smallint location_id FK
    smallint job_level_id FK
    smallint source_id FK
    numeric comp_amount
    numeric fte
  }

  dim_requisition {
    string requisition_id PK
    smallint department_id FK
    smallint location_id FK
    smallint job_level_id FK
    string hiring_manager_id FK
    enum status
    date opened_date
    date closed_date
    date target_start_date
    smallint openings
    numeric internal_cost
    numeric external_cost
  }

  dim_survey {
    smallint survey_id PK
    string code UK
    string name
    date quarter_start
    date opens_on
    date closes_on
  }

  fact_employment_event {
    bigint event_id PK
    string employee_id FK
    date event_date
    enum event_type
    smallint from_department_id FK
    smallint to_department_id FK
    smallint from_job_level_id FK
    smallint to_job_level_id FK
    string from_manager_id FK
    string to_manager_id FK
    numeric from_comp_amount
    numeric to_comp_amount
    enum termination_type
  }

  fact_monthly_headcount_snapshot {
    date month_start PK
    string employee_id PK
    smallint department_id FK
    smallint location_id FK
    smallint job_level_id FK
    string manager_id FK
    numeric comp_amount
    numeric fte
    smallint tenure_months
    boolean active_at_month_start
    boolean active_at_month_end
    boolean terminated_in_month
    boolean hired_in_month
  }

  fact_application {
    bigint application_id PK
    string requisition_id FK
    smallint source_id FK
    string candidate_ref
    date first_application_date
    enum final_stage
    date offer_extended_date
    date offer_accepted_date
    date offer_declined_date
    date rejected_date
    string hired_employee_id FK
  }

  fact_application_stage_event {
    bigint stage_event_id PK
    bigint application_id FK
    enum stage
    date entered_on
    date exited_on
  }

  fact_survey_response {
    bigint response_id PK
    smallint survey_id FK
    string employee_id FK
    date submitted_on
    smallint enps_score
    smallint driver_manager
    smallint driver_growth
    smallint driver_recognition
    smallint driver_workload
    smallint driver_belonging
    text open_text
  }

  fact_comment_theme {
    bigint comment_theme_id PK
    bigint survey_response_id FK
    string theme
    enum sentiment
    numeric confidence
    string model
    timestamptz created_at
  }

  fact_timesheet_week {
    bigint timesheet_id PK
    string employee_id FK
    smallint department_id FK
    date week_start
    numeric billable_hours
    numeric non_billable_hours
    numeric available_hours
    numeric output_units
    enum output_type
  }

  fact_goal {
    bigint goal_id PK
    string employee_id FK
    smallint department_id FK
    date quarter_start
    string title
    numeric target_value
    numeric actual_value
    enum status
  }

  fact_absence {
    bigint absence_id PK
    string employee_id FK
    date absence_date
    numeric days
    enum absence_type
    boolean is_unplanned
  }

  fact_performance_review {
    bigint review_id PK
    string employee_id FK
    string reviewer_id FK
    date review_period_start
    date review_date
    smallint rating
  }

  fact_department_revenue {
    smallint department_id PK
    date quarter_start PK
    numeric revenue_amount
  }

  fact_training {
    bigint training_id PK
    string employee_id FK
    string course_code
    string course_name
    date assigned_on
    date completed_on
    numeric hours
  }

  fact_flight_risk_score {
    string employee_id PK
    date as_of_month PK
    numeric score
    enum band
    jsonb components
    timestamptz computed_at
  }

  dim_employee      ||--o| dim_employee                    : "manages"
  dim_department    ||--o{ dim_employee                    : "employs"
  dim_location      ||--o{ dim_employee                    : "hosts"
  dim_job_level     ||--o{ dim_employee                    : "grades"
  dim_source        ||--o{ dim_employee                    : "sourced"

  dim_department    ||--o{ dim_requisition                 : "opens"
  dim_location      ||--o{ dim_requisition                 : "sited in"
  dim_job_level     ||--o{ dim_requisition                 : "graded"
  dim_employee      ||--o{ dim_requisition                 : "hiring manager"

  dim_requisition   ||--o{ fact_application                : "receives"
  dim_source        ||--o{ fact_application                : "channels"
  dim_employee      ||--o| fact_application                : "hired from"
  fact_application  ||--o{ fact_application_stage_event    : "progresses"

  dim_employee      ||--o{ fact_employment_event           : "transitions"
  dim_employee      ||--o{ fact_monthly_headcount_snapshot : "snapshot"
  dim_department    ||--o{ fact_monthly_headcount_snapshot : "as-of dept"
  dim_employee      ||--o{ fact_performance_review         : "reviewed"
  dim_employee      ||--o{ fact_absence                    : "absent"
  dim_employee      ||--o| fact_flight_risk_score          : "scored"

  dim_survey        ||--o{ fact_survey_response            : "collects"
  dim_employee      ||--o{ fact_survey_response            : "responds"
  fact_survey_response ||--o{ fact_comment_theme           : "themed"

  dim_employee      ||--o{ fact_timesheet_week             : "logs"
  dim_department    ||--o{ fact_timesheet_week             : "team"
  dim_employee      ||--o{ fact_goal                       : "owns"
  dim_department    ||--o{ fact_goal                       : "rolls up"
  dim_department    ||--o{ fact_department_revenue         : "earns"
  dim_employee      ||--o{ fact_training                   : "assigned"
```

**`dim_date` carries no foreign-key constraints.** Period columns (`month_start`,
`quarter_start`, `week_start`) join to it logically, but constraining all fifteen of them
would add no integrity the generator does not already guarantee, and would make truncating
the calendar impossible during phase 2 regeneration.

---

## Metric coverage

All 31 metrics in `docs/METRICS.md`, mapped to the tables that compute them. This matrix is
the deliverable of the pre-model coverage walk: nothing in the catalog is unbuildable.

### Talent acquisition

| Metric | Source tables |
|---|---|
| Time to Fill | `dim_requisition` (opened) + `fact_application` (offer_accepted) |
| Time to Hire | `fact_application` (first_application_date → offer_accepted_date) |
| Funnel Conversion | `fact_application_stage_event` counted per stage |
| Offer Acceptance Rate | `fact_application` (offer_extended vs offer_accepted) |
| Cost per Hire | `dim_requisition` (internal_cost + external_cost) + hire counts |
| Source Effectiveness | `fact_application` + `dim_source` + `dim_employee` (90-day retention) |
| Requisition Aging | `dim_requisition` (status, opened_date) |
| Quality of Hire | `dim_employee` (day-180 survival) + `fact_performance_review` |

### Retention

| Metric | Source tables |
|---|---|
| Headcount | `fact_monthly_headcount_snapshot.active_at_month_end` |
| Attrition Rate (annualized) | snapshot: `terminated_in_month` ÷ avg of both active flags |
| Voluntary vs Involuntary | snapshot + `dim_employee.termination_type` |
| Regretted Attrition | `dim_employee` + last `fact_performance_review` before exit |
| Tenure Distribution | `fact_monthly_headcount_snapshot.tenure_months` |
| New Hire 12-Month Retention | `dim_employee.hire_date` + snapshot survival by cohort |
| Attrition by Manager | snapshot `manager_id` — as-of-month, not current |
| Internal Mobility Rate | `fact_employment_event` (promotion + lateral_transfer) |
| Flight Risk Score | snapshot + `fact_employment_event` + `fact_survey_response` + `dim_job_level` comp band → `fact_flight_risk_score` |

### Engagement

| Metric | Source tables |
|---|---|
| eNPS | `fact_survey_response.enps_score` |
| Engagement Index | mean of the 5 `driver_*` columns, normalized in view |
| Driver Breakdown | the 5 `driver_*` columns by department |
| Survey Participation | `fact_survey_response` ÷ eligible from snapshot |
| Engagement → Attrition Link | `fact_survey_response` quartiles × snapshot attrition |
| Comment Themes | `fact_survey_response.open_text` → `fact_comment_theme` |
| Absenteeism Rate | `fact_absence.is_unplanned` ÷ `dim_date.is_workday` × headcount |

### Productivity

| Metric | Source tables |
|---|---|
| Revenue per FTE | `fact_department_revenue` ÷ snapshot `fte` |
| Utilization | `fact_timesheet_week` (billable ÷ available) |
| Overtime Rate | `fact_timesheet_week` (hours over 40 ÷ total) |
| Span of Control | `fact_monthly_headcount_snapshot.manager_id` counts |
| Goal Attainment | `fact_goal` (actual ÷ target, capped 1.5 in metric layer) |
| Output per Head | `fact_timesheet_week.output_units` ÷ active FTE |
| Training Hours | `fact_training` (hours, completion via `completed_on`) |

**Three tables exist because of this walk.** `fact_department_revenue`, `fact_training`, and
the `output_units`/`output_type` columns on `fact_timesheet_week` had no counterpart in the
phase-1 fact list, but Revenue per FTE, Training Hours, and Output per Head are all in the
catalog. Without them, three metrics would have been silently uncomputable.

---

## Decisions and why

- **Type-1 dimensions plus an event fact.** `dim_employee` holds current state;
  `fact_employment_event` holds transitions; `fact_monthly_headcount_snapshot` holds
  as-of-month state. Attrition by manager therefore attributes an exit to the manager who
  held the report *at the time*, not to whoever inherited the team.
- **Average headcount is structural.** The snapshot stores `active_at_month_start` and
  `active_at_month_end` separately, so `(SUM(start) + SUM(end)) / 2` needs no lag join.
  `CLAUDE.md` calls the wrong denominator the most common bug in HR analytics; making the
  right one the easy one beats catching it 31 times in review.
- **Rates are never stored.** Facts carry numerators and denominators; division happens in a
  view or the metric layer, keeping the denominator auditable.
- **Stage events store entry *and* exit**, so pipeline dwell time is a subtraction and a
  re-entered stage produces two honest rows instead of a double-counted funnel step.
- **Driver scores stored raw 1–5, normalized to 0–100 in views** via `(raw − 1) / 4 × 100`.
  The planted scenarios are written in 0–100 points, so normalization lives in one place.
- **`Numeric`, never `Float`, for money and hours** — enforced by a test that scans every
  column type.
- **Text employee keys, managers prefixed `M-`.** The bad-manager scenario names `M-114` and
  the Loom reads it aloud; one ID space, no collision.
- **Views as the read surface.** They pre-aggregate to metric grain *and* form the security
  boundary for NL→SQL — generated SQL selects from allowlisted views only, never base tables.
- **`/health` never touches the database.** Render polls it during cold start; readiness is a
  separate check at `/health/db`.
- **`pool_pre_ping=True`** — Neon closes idle connections, and without it the first query
  after an idle period fails instead of reconnecting.
- **Alembic reads `DATABASE_URL` from `app.config`, not `alembic.ini`**, so migrations, the
  app, and the seed generator cannot drift onto different databases and no credential lands in
  a tracked file.

## Environments

| | Local development | Production (phase 7) |
|---|---|---|
| Database | PostgreSQL 18 service on the host, port 5432 | Neon, pooled connection string |
| Set via | `backend/.env` (gitignored) | Render env var |
| Fallback | `docker-compose.yml` on port **5433** — for a machine with no Postgres installed; the offset port means it cannot collide with the host service | — |

`pool_pre_ping=True` is set for Neon's idle disconnects and is harmless locally.

## The generator (`backend/seed/`)

Not part of the running application — a build-time tool that fills the warehouse. Its structure
mirrors `app/models/` so a table and the code that populates it are easy to line up.

| Module | Responsibility |
|---|---|
| `util.py` | Pure date and decimal helpers. No RNG, no database. |
| `reference.py` | The 36-month window, fixed dimension rows, surrogate-key maps, name pools. |
| `scenarios.py` | The six planted scenarios as typed targets with tolerances, plus company baselines. |
| `spine.py` | `dim_date`, including the holiday list behind `is_workday`. |
| `people.py` | Employees, employment events, the monthly snapshot, and the hazard model. |
| `recruiting.py` | Requisitions, applications, funnel stage events. |
| `engagement.py` | Survey responses, driver scores, themed open text. |
| `productivity.py` | Timesheets, absence, goals, revenue, training, reviews. |
| `generate.py` | Orchestration and CLI: `--scale`, `--reset`, `--no-validate`. |
| `validate.py` | The five-section report and the six scenario assertions. |

**Two generation modes, used deliberately.** Ambient patterns are *sampled* from relative
monthly hazard weights. Any number the demo says out loud is *forced* exactly — M-114 has
precisely six exits with four rated 4+. Exit totals use weighted sampling **without replacement
to an exact count**, so stated volumes hold while relative patterns stay realistic.

**Determinism is verified, not asserted.** `random.seed(42)` and
`numpy.random.default_rng(42)` are necessary but insufficient: surrogate keys are identity
columns, so `--reset` truncates with `RESTART IDENTITY CASCADE` and sequences are resynced
afterwards (otherwise phase 6's first insert into a seeded table would collide on a primary
key). `python -m seed.validate --checksum` hashes row counts plus key aggregates; two
consecutive full runs must produce the same digest.

**Validation recomputes independently.** Every assertion in `validate.py` is written in raw SQL
from `docs/METRICS.md`, never by calling generator helpers — otherwise it would only confirm the
generator agrees with itself. The current report lives in `docs/SEED_VALIDATION.md`.

## What exists now (phase 1)

- 21 tables as ORM models across 7 modules in `app/models/`, all registered in
  `app/models/__init__.py` so Alembic autogenerate can see them.
- **Migration `871a493d0d3e` applied to a live database.** `alembic check` reports no drift
  between models and schema, and `downgrade base` → `upgrade head` round-trips cleanly.
- Verified in the live database: 21 tables, 172 columns, 38 foreign keys, 10 enum types, 60
  indexes. Counts reconciled against the ERD above rather than against the models.
- 25 passing tests: 15 schema guards (metadata only, no connection needed), 6 config, 4 health.
- `/health/db` returns 200.

## What exists now (phase 2)

- **216,432 rows** across 21 tables, generated in 27s. 1,850 employees, headcount running
  1,150 → 1,200; 43,693 snapshot rows; 88,484 timesheet weeks; 8,692 applications converting to
  700 hires; 5,044 survey responses; 770 requisitions.
- **All six planted scenarios verified present** within tolerance — see
  `docs/SEED_VALIDATION.md`.
- 66 passing tests, up from 25.
- `fact_flight_risk_score` and `fact_comment_theme` remain deliberately empty; they are written
  in phases 3 and 6.
- Still **zero views and zero metric implementations** — phase 3.

### Deviations from BUILD_PLAN §3 volumes

- **770 requisitions, not 410.** One opening per requisition is what makes time to fill exact;
  batching hires weeks apart dragged `opened_date` backwards and measured 183 days against a
  74-day target. Time to fill is an asserted scenario number, the requisition count is not.
- **8,692 applications** against "~9,200" — a consequence of per-channel conversion rates.
- **Managers never terminate**, so `manager_id` always points at an active employee and span of
  control stays stable.
- **Company time to fill is 43.8 days** against the plan's 38, passing at the edge of its ±6
  tolerance. Sales' 74 is exact.

### One migration trap worth remembering

Alembic's autogenerate emits `CREATE TYPE` for a native enum on first use but never a matching
`DROP TYPE`. Left alone, `downgrade base` orphans all 10 types and the next `upgrade head` fails
with `DuplicateObject`. The initial revision therefore ends `downgrade()` with an explicit
`ENUM_TYPE_NAMES` drop loop. **Any future revision that adds an enum must do the same** — phase 2
regenerates this database repeatedly, so a one-way migration is a live obstacle, not a
hypothetical one.

## The metrics layer (`sql/views/` + `app/metrics/`)

**Views pre-aggregate; Python filters and divides.** A view cannot take a parameter, so each is
built at the finest grain any of its metrics needs and exposes **numerator and denominator as
separate columns**. The caller applies filters, aggregates, then divides. That enforces the
average-headcount rule once per metric family rather than 31 times — `v_headcount_monthly`
emits `avg_headcount`, and nothing downstream can reach for end-of-period headcount by
accident.

**Two thresholds deliberately live in SQL**, against that rule, because they apply per row and
cannot be recovered after aggregation:

| Threshold | Where | Why it cannot move to Python |
|---|---|---|
| Overtime's 40-hour line | `40_v_timesheet_weekly.sql` | 30 hours one week and 50 the next is 10 hours of overtime; the 80-hour fortnight shows none |
| Goal attainment's 1.5 cap | `43_v_goal_attainment.sql` | Capping a team average is a different calculation from capping each goal and averaging |

**Three grain rules learned the hard way**, each from a bug:

- **A threshold does not survive aggregation the way a sum does.** `v_manager_attrition_quarterly`
  is grained by `(quarter, manager)` and nothing finer, because splitting a manager across
  department and location rows made every slice fail the 8-report floor. The floor itself
  applies to *average* team size, not to the count of people who passed through.
- **A pre-divided average can only be re-aggregated along dimensions it was not divided by.**
  `v_mobility_monthly` and `v_training_monthly` are monthly rather than yearly for this reason;
  summing per-year averages across years reported an average headcount of 4,760 for a company
  of 1,194.
- **A distribution is a snapshot, not an accumulation.** Tenure distribution is point-in-time at
  the latest month in range; summing across months produced person-months.

**One filter implementation.** `MetricFilters` is built by a single FastAPI dependency and
applied by `apply_filters(stmt, view, filters, period_column=...)`. The period column is passed
explicitly because views name it differently (`month_start`, `quarter_start`, `week_start`,
`hire_quarter`). A filter a view cannot honour raises `UnsupportedFilterError` → **HTTP 400**;
it is never silently dropped, because a 200 carrying data for a slice nobody asked for is
undetectable from the client.

**Flight risk is a transparent weighted score, not a model.** Five components — tenure band,
months since last promotion, engagement delta against the department mean, the manager's
trailing-12-month attrition, and position in the pay band — with weights summing to exactly
1.0. Each component's raw score, weight and contribution is stored in JSONB, and `explain()`
renders one sentence per component ordered by contribution. `/api/flight-risk/weights` exposes
the weighting over HTTP so the score is auditable from the API rather than only from source.

## Verification: two independent guards

1. **`tests/fixtures/tiny_org.py`** — a 12-employee, 18-month organization small enough that
   every metric is a few-term sum, with the arithmetic written into each test as a comment. It
   runs against a separate `people_analytics_test` database built from `Base.metadata.create_all`
   plus **the real view files**, so a metric cannot pass its test and be wrong in production.
2. **The `metric-verifier` subagent** — a fresh-context agent that recomputes every metric in
   raw SQL from `docs/METRICS.md` against base tables only, never the views.

The second guard exists because the first cannot catch a shared misreading. It found four real
bugs, including one where a view's own header comment described behaviour the view did not
implement *and* `seed/validate.py`'s supposedly independent check of the same scenario carried
the identical error — because the same author wrote both.

## What exists now (phase 3)

- **21 views** and **31 of 31 metrics**, each with a hand-computed test.
- **41 endpoints** across five routers, all using the shared filter dependency and the
  `{data, meta}` envelope. 40 return non-empty data; `/api/engagement/themes` is correctly
  empty until phase 6 populates `fact_comment_theme`.
- **170 tests passing.** 33 flight-risk tests, 28 of which need no database because the scoring
  functions are pure.
- 1,200 employees scored and persisted: 10 low, 663 moderate, 515 elevated, 12 high.

### Known gap

Tests call metric functions directly and never cross the Pydantic boundary, so a response-model
mismatch reached a live endpoint as an HTTP 500 with a green suite. Phase 4 should add
route-level tests through `TestClient`.

## Next

Phase 4 completes the API surface: demo bearer-token auth, CORS for the Vercel origin, and
`/api/overview` returning the eight headline KPIs in a single call.
