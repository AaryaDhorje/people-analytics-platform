# People Analytics Platform — 24-Hour Build Plan (Claude Code execution)

**Owner:** Aarya
**Created:** 30 Jul 2026
**Target:** Working deployed product + 4–5 min Loom + repo, ~80% authored by Claude Code
**Working budget:** 19 active hours + 5 hours sleep/buffer inside the 24-hour window

---

## 0. Decisions already made (do not re-litigate mid-build)

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 + Alembic, Python 3.12 | Your PulseAI stack — zero learning curve |
| DB | PostgreSQL on **Neon** (free tier) | Serverless, instant connection string, no container to babysit |
| Metrics layer | SQL views + typed Python service module | Views make the "warehouse" story credible in the demo |
| Frontend | Vite + React + TypeScript + Tailwind + Recharts + TanStack Query | Fast, and Recharts is what Claude Code writes most reliably |
| Deploy | Backend → **Render** web service; Frontend → **Vercel** | Two free deploys, both give you a public URL in <10 min |
| AI features | Claude API: (1) NL→SQL "Ask your people data", (2) attrition-risk narrative, (3) survey comment theming | Directly relevant to an AI-Augmented Analytics role |
| Models | `claude-sonnet-5` for reasoning/NL→SQL, `claude-haiku-4-5-20251001` for bulk comment classification | Confirm current strings at docs.claude.com before hardcoding |
| Auth | Single hardcoded demo user + bearer token | Do not burn hours on auth. Say so out loud in the Loom. |
| Data | Fully synthetic, seeded, ~1,200 employees × 3 years | "Own data" without any privacy exposure |

**The one rule that saves this project:** the synthetic data must contain *planted signal*. A dashboard on random data shows flat lines and no story. Section 3 covers this — it is the highest-leverage 45 minutes in the whole build.

---

## 1. Metric catalog (lock this before writing code)

This is your contract. Claude Code will implement exactly these, and your pytest fixtures will verify each formula by hand. Write this into `docs/METRICS.md` in hour 1 — it becomes the spec Claude Code reads on every phase.

### 1.1 Talent Acquisition

| Metric | Formula | Grain |
|---|---|---|
| Time to Fill | `AVG(offer_accepted_date - requisition_opened_date)` | Req, dept, month |
| Time to Hire | `AVG(offer_accepted_date - first_application_date)` | Req, source |
| Funnel Conversion | `stage_n_count / stage_n-1_count` across Applied → Screen → Interview → Offer → Hired | Source, dept |
| Offer Acceptance Rate | `offers_accepted / offers_extended` | Dept, level, month |
| Cost per Hire | `(internal_cost + external_cost) / hires_in_period` | Dept, quarter |
| Source Effectiveness | `hires_from_source / applications_from_source`, plus 90-day retention of those hires | Source |
| Requisition Aging | `COUNT(reqs WHERE status='open' AND age_days > 60)` | Dept |
| Quality of Hire | `% of new hires still employed at day 180 AND performance_rating >= 3` | Source, manager |

### 1.2 Retention

| Metric | Formula | Grain |
|---|---|---|
| Headcount | `COUNT(active employees)` at month-end snapshot | Dept, location, level |
| Attrition Rate (annualized) | `(terminations_in_month / avg_headcount_in_month) * 12` | Dept, manager, month |
| Voluntary vs Involuntary | Split of the above by `termination_type` | Dept |
| Regretted Attrition | `voluntary_exits WHERE last_performance_rating >= 4 / total_voluntary_exits` | Dept |
| Tenure Distribution | Bucketed: <6m, 6–12m, 1–2y, 2–5y, 5y+ | Dept |
| New Hire 12-Month Retention | `% of a hire cohort still active at month 12` (cohort survival curve) | Hire quarter, source |
| Attrition by Manager | Attrition rate where `manager_id = X`, min 8 reports | Manager |
| Internal Mobility Rate | `(promotions + lateral_transfers) / avg_headcount` | Dept, year |
| Flight Risk Score | Logistic-style weighted score: tenure band, months since last promotion, engagement delta, manager attrition rate, comp percentile vs band | Employee |

### 1.3 Engagement

| Metric | Formula | Grain |
|---|---|---|
| eNPS | `%promoters (9–10) − %detractors (0–6)` | Company, dept, quarter |
| Engagement Index | Mean of 5 driver scores, normalized 0–100 | Dept, quarter |
| Driver Breakdown | Mean score per driver: Manager, Growth, Recognition, Workload, Belonging | Dept |
| Survey Participation | `responses / eligible_employees` | Dept, survey |
| Engagement → Attrition Link | Attrition rate of employees in bottom engagement quartile vs top quartile | Dept |
| Comment Themes | Claude-extracted themes from open text, with sentiment and volume | Dept, quarter |
| Absenteeism Rate | `unplanned_absence_days / available_workdays` | Dept, month |

### 1.4 Productivity

| Metric | Formula | Grain |
|---|---|---|
| Revenue per FTE | `revenue_in_period / avg_FTE` | Dept, quarter |
| Utilization | `billable_hours / available_hours` | Employee, team, week |
| Overtime Rate | `hours_over_40 / total_hours` | Team, month |
| Span of Control | `AVG(direct_reports per manager)` | Dept, level |
| Goal Attainment | `AVG(goal_actual / goal_target)` capped at 1.5 | Team, quarter |
| Output per Head | Tickets closed or story points per active FTE | Team, sprint |
| Training Hours | `SUM(training_hours) / headcount`, plus completion rate | Dept |

**MVP cut line:** if you fall behind, ship 5–6 metrics per domain, not all of them. Depth on Retention (the domain HR leaders actually buy) beats thin coverage everywhere.

---

## 2. Repository layout

Give Claude Code this exact tree in the first prompt. Fighting a layout it invented costs more than dictating one.

```
people-analytics/
├── CLAUDE.md                      # Claude Code operating rules
├── README.md
├── docs/
│   ├── METRICS.md                 # Section 1 of this plan, verbatim
│   ├── ARCHITECTURE.md
│   └── DEMO_SCRIPT.md
├── .claude/
│   ├── settings.json              # hooks
│   ├── commands/                  # /phase, /verify, /metric, /wrap
│   └── agents/                    # subagent definitions
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/                # SQLAlchemy ORM
│   │   ├── schemas/               # Pydantic response models
│   │   ├── metrics/               # one module per domain
│   │   │   ├── acquisition.py
│   │   │   ├── retention.py
│   │   │   ├── engagement.py
│   │   │   ├── productivity.py
│   │   │   └── flight_risk.py
│   │   ├── ai/
│   │   │   ├── nl_query.py        # NL → SQL, allowlisted
│   │   │   ├── narrative.py       # exec summary + risk explanations
│   │   │   └── comments.py        # theme extraction
│   │   └── api/routes/
│   ├── alembic/
│   ├── sql/views/                 # one .sql per analytical view
│   ├── seed/
│   │   ├── generate.py            # synthetic data generator
│   │   └── scenarios.py           # planted signal definitions
│   └── tests/
│       ├── test_metrics_*.py      # hand-computed fixtures
│       └── fixtures/tiny_org.py   # 12-employee org, math done by hand
├── frontend/
│   └── src/
│       ├── pages/                 # Overview, Acquisition, Retention, Engagement, Productivity, Ask
│       ├── components/            # KpiCard, TrendChart, FunnelChart, HeatmapTable, CohortCurve
│       ├── lib/api.ts
│       └── hooks/
└── docker-compose.yml             # local Postgres only
```

---

## 3. Synthetic data with planted signal — the part that makes the demo land

Write `backend/seed/scenarios.py` as an explicit list of stories the data must tell. Then the generator honours them. Every chart in your dashboard will have something to point at in the Loom.

**Planted scenarios (use these):**

1. **The bad-manager cluster.** One Engineering manager (`M-114`) has 2.4× company attrition over the last 3 quarters, engagement Manager-driver score 28 points below company mean, and 4 of 6 exits rated 4+ (regretted). → Your flight-risk model and manager heatmap both surface it independently. This is your headline demo moment.
2. **Sourcing channel decay.** Agency hires had 62% 12-month retention vs 88% for referrals, while agency cost per hire is 3× higher. → Cost per hire and quality of hire disagree with each other, which is exactly the insight HR wants.
3. **Post-reorg engagement dip.** Company reorg in Q3 of year 2 drops Belonging and Growth drivers by 15 points, followed by an attrition spike two quarters later. → Proves the engagement→attrition lag on your chart.
4. **Sales pipeline bottleneck.** Sales reqs sit 41 days at Interview stage vs 12 days elsewhere; time to fill 74 days vs company 38. → Funnel chart has an obvious pinch point.
5. **Burnout in Support.** Overtime rate 22% and absenteeism climbing over 6 months, utilization above 95%, engagement Workload driver lowest in company. → Cross-domain story linking Productivity and Engagement.
6. **Tenure cliff.** Elevated attrition at the 14–18 month mark for the two most recent hire cohorts. → Cohort survival curve shows a visible knee.

**Volumes:** 1,200 active employees, ~1,850 total employee records over 36 months, 8 departments, 4 locations, 6 job levels, 410 requisitions, 9,200 applications, 6 quarterly surveys × ~70% participation, 3 years of weekly timesheets for billable teams, ~2,400 goals.

**Determinism:** hardcode `random.seed(42)` and `numpy.random.default_rng(42)`. You will regenerate this database at least four times. Non-deterministic data means your pytest fixtures break and your Loom narration stops matching the screen.

---

## 4. CLAUDE.md — write this before your first build prompt

This file is why the project stays coherent. Paste this in, then let Claude Code extend it.

```markdown
# People Analytics Platform — Claude Code Operating Rules

## What this is
An HR analytics platform: PostgreSQL warehouse of synthetic HR data, FastAPI
metric services, React dashboard, Claude-powered natural-language querying.
Deadline-driven MVP. Working software over completeness.

## Non-negotiables
- Metric definitions live in docs/METRICS.md. Never invent a formula. If a metric
  is ambiguous, stop and ask rather than guessing.
- Every metric function gets a pytest test against tests/fixtures/tiny_org.py,
  where the expected value was computed by hand. Test first, then implement.
- No placeholders, no TODO comments, no `pass  # implement later`. Ship complete files.
- Seeded randomness only. seed=42 everywhere.
- Money and rates: return raw numbers from the API, format in the frontend.
- Dates: all DB columns are `date` or `timestamptz`. Never store dates as text.
- Attrition denominators are AVERAGE headcount for the period, not end headcount.
  This is the single most common bug in HR analytics.

## Conventions
- Backend: FastAPI, SQLAlchemy 2.0 typed ORM, Pydantic v2 response models,
  ruff for lint+format, pytest. Routes thin, logic in app/metrics/.
- Every metric endpoint accepts optional filters: date_from, date_to,
  department_id, location_id, level, manager_id. Implement filters once as a
  shared dependency, not per route.
- Frontend: TypeScript strict. TanStack Query for all fetching, no raw useEffect
  fetches. Recharts only. Tailwind utility classes, no CSS files.
- API responses are always `{ data: ..., meta: { as_of, filters_applied, row_count } }`.

## Testing
- `cd backend && pytest -q` must pass before any phase is considered done.
- `cd frontend && npm run build` must pass with zero TS errors.

## Definition of done for a phase
Tests pass, build passes, endpoints return non-empty data against the seeded DB,
and you have printed a one-paragraph summary of what changed.

## Do not
- Do not modify docs/METRICS.md without being asked.
- Do not add authentication beyond the existing demo token.
- Do not add new dependencies without saying why in one sentence.
- Do not refactor working code for elegance while the deadline is open.
```

---

## 5. Claude Code setup that pays for itself

### 5.1 Hooks — `.claude/settings.json`

Auto-format and auto-test on every edit. This catches the drift that otherwise surfaces at hour 18.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "cd backend && ruff format --quiet . && ruff check --fix --quiet . || true"
          }
        ]
      },
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "cd backend && pytest -q tests/ -x --no-header 2>&1 | tail -5 || true"
          }
        ]
      }
    ]
  }
}
```

### 5.2 Custom slash commands — `.claude/commands/`

**`verify.md`**
```markdown
Run the full verification suite and report results as a table:
1. cd backend && ruff check .
2. cd backend && pytest -q
3. cd frontend && npm run build
4. Hit every registered endpoint with curl against the local server and report
   HTTP status + whether `data` is non-empty.
Report failures with file and line. Fix nothing unless I say so.
```

**`metric.md`**
```markdown
Implement the metric named $ARGUMENTS.
Order of work, no deviation:
1. Quote the exact formula from docs/METRICS.md.
2. Write the pytest test against tests/fixtures/tiny_org.py with the expected
   value computed by hand — show me the arithmetic in a comment.
3. Run it, confirm it fails for the right reason.
4. Implement in the correct app/metrics/ module.
5. Run it, confirm green.
6. Expose the endpoint, register it, curl it, paste the response.
```

**`phase.md`**
```markdown
We are starting phase $ARGUMENTS of docs/BUILD_PLAN.md.
Read the phase section. Enter plan mode. Produce a file-by-file plan with
estimated line counts. Do not write code until I approve the plan.
```

**`wrap.md`**
```markdown
End-of-phase wrap:
1. Run /verify.
2. git add -A and commit with a conventional-commit message describing the phase.
3. Update docs/ARCHITECTURE.md if the architecture changed.
4. Print: files changed, tests passing count, endpoints live, next phase, blockers.
```

### 5.3 Subagents — `.claude/agents/`

Define these so you can parallelize and keep the main context clean:

- **`data-generator`** — owns `backend/seed/`. Knows the scenarios in section 3. Never touches app code.
- **`metric-verifier`** — read-only. Given a metric name, independently recomputes it with raw SQL against the seeded DB and compares to the API response. This is your hallucination check on the numbers, and it maps directly onto your standing code-review protocol.
- **`frontend-builder`** — owns `frontend/`. Given an endpoint contract, builds the page and components. Never touches backend.
- **`sql-view-author`** — owns `backend/sql/views/`. Writes and explains analytical views.

### 5.4 MCP servers to enable before you start

- **Postgres MCP** → let Claude Code introspect the live schema instead of guessing column names. Biggest single accuracy win.
- **Context7** (already connected) → current FastAPI / SQLAlchemy 2.0 / Recharts / TanStack Query docs. Prevents SQLAlchemy 1.x-style code.
- **Chrome / Playwright MCP** → let Claude Code screenshot the dashboard and critique its own layout. Also gives you Loom-ready stills.
- **Vercel MCP** (already connected) → deploy and read build logs without leaving the terminal.
- **Mermaid Chart MCP** (already connected) → generate the architecture diagram for the Loom in about 90 seconds.

### 5.5 Session hygiene

- Run **plan mode** (`Shift+Tab` twice) at the start of every phase. Read the plan. Reject bad plans — a rejected plan costs 30 seconds, a bad implementation costs an hour.
- `/clear` between phases. Do not carry frontend context into backend work.
- `/compact` the moment context passes ~70%.
- Commit at the end of every phase, no exceptions. `git worktree` for the frontend if you want to run two Claude Code sessions in parallel during the UI block.
- Keep a `docs/SESSION_LOG.md` appended after each phase — this becomes your Loom notes and your README's "how it was built" section.

---

## 6. The 24-hour schedule

Hour numbers are elapsed from your start. Each phase ends with `/wrap`.

### Phase 0 — Foundation (H0:00–H1:00)

Manual, not Claude Code:
1. Create Neon project, copy the pooled connection string.
2. `mkdir people-analytics && cd people-analytics && git init`
3. Write `CLAUDE.md` (section 4), `docs/METRICS.md` (section 1), `docs/BUILD_PLAN.md` (this file).
4. Create `.claude/commands/*.md`, `.claude/settings.json`, `.claude/agents/*.md`.
5. Commit. **You now have the spec before the first line of code — this is what makes 19 hours enough.**

First Claude Code prompt:

> Read CLAUDE.md, docs/METRICS.md, and docs/BUILD_PLAN.md. Scaffold the repository exactly as laid out in the BUILD_PLAN tree: backend with FastAPI + SQLAlchemy 2.0 + Alembic + pytest + ruff, frontend with Vite + React + TypeScript + Tailwind + Recharts + TanStack Query, docker-compose with Postgres for local dev, .env.example, .gitignore. Include a `/health` endpoint and one smoke test. Do not implement any metrics yet. Then run both build commands and show me they pass.

### Phase 1 — Schema and warehouse (H1:00–H2:30)

> Design and implement the star schema for this platform. Dimensions: employee (with self-referencing manager_id, hire_date, termination_date, termination_type, level, department_id, location_id, comp_band, comp_amount), department, location, job_level, source, requisition, survey, date spine. Facts: employment_event, monthly_headcount_snapshot, application, application_stage_event, survey_response (including nullable open_text), timesheet_week, goal, absence, performance_review. Every metric in docs/METRICS.md must be computable from this schema — walk through all four domains and confirm each one before writing the models. Generate the Alembic migration and apply it. Then print the ERD as Mermaid into docs/ARCHITECTURE.md.

Then: `/wrap`.

### Phase 2 — Synthetic data with planted signal (H2:30–H4:30)

Use the `data-generator` subagent.

> Using the data-generator subagent: implement backend/seed/scenarios.py and backend/seed/generate.py. Read section 3 of docs/BUILD_PLAN.md — all six planted scenarios must be verifiably present in the output. Volumes and seed as specified. After generating, print a validation report: headcount by month, attrition rate by department by quarter, funnel counts by stage, engagement driver means by department by quarter, overtime rate by team. I will check that report against the six scenarios myself before we continue.

**Do not skip reading that validation report.** If the planted signal isn't there, every downstream chart is boring and no amount of frontend polish fixes it.

Then: `/wrap`.

### Phase 3 — Metrics layer + tests (H4:30–H7:30) ← the credibility phase

> Build tests/fixtures/tiny_org.py: a 12-employee, 18-month organization small enough that every metric can be computed by hand. Include at least one termination, one promotion, one open req with a full funnel, two survey waves, and a quarter of timesheets. Then, for each of the four metric domains, work strictly test-first: write the pytest with hand-computed expected values shown as arithmetic in comments, confirm it fails, implement the metric in the right module, confirm green. Start with Retention, then Acquisition, then Engagement, then Productivity. Use the average-headcount denominator for all rate metrics. Stop and report after each domain.

After all four domains:

> Using the metric-verifier subagent: independently recompute every metric with raw SQL against the seeded database and compare against the Python implementations. Report any discrepancy over 0.5% as a table with metric name, SQL result, Python result, and delta. Do not fix anything yet.

Then implement `flight_risk.py` (transparent weighted score, no ML — you must be able to explain it live in the Loom), expose all endpoints with the shared filter dependency, and `/wrap`.

### Phase 4 — API surface complete (H7:30–H8:30)

> Complete the API: shared filter dependency (date_from, date_to, department_id, location_id, level, manager_id) applied to every metric route, consistent `{data, meta}` envelope, Pydantic response models for everything, demo bearer-token auth, CORS for the Vercel origin, and a /api/overview endpoint returning the 8 headline KPIs for the landing page in a single call. Then run /verify and paste the endpoint table.

**Then sleep. H8:30–H13:30.** Ship-quality work at hour 20 requires this. Commit and push first.

### Phase 5 — Frontend (H13:30–H18:30)

Use the `frontend-builder` subagent, one page per prompt.

> Using the frontend-builder subagent: build the app shell — sidebar navigation (Overview, Talent Acquisition, Retention, Engagement, Productivity, Ask), a global filter bar wired to URL search params so every view is shareable, TanStack Query client with 60s stale time, loading skeletons, and empty/error states that say what happened and what to do. Then build the Overview page against /api/overview: 8 KPI cards each with value, period-over-period delta, and sparkline.

Then one prompt per domain page:

- **Acquisition:** funnel chart (stage conversion), time-to-fill trend, source effectiveness scatter (cost per hire × 12-month retention, bubble size = hires), req aging table
- **Retention:** attrition trend with voluntary/involuntary split, manager heatmap table sorted by attrition, tenure distribution histogram, cohort survival curves, flight-risk table with expandable per-employee reason breakdown
- **Engagement:** eNPS gauge + trend, driver radar by department, participation rate, engagement-quartile vs attrition bar chart, Claude-generated comment themes as cards with sentiment and volume
- **Productivity:** revenue per FTE trend, utilization heatmap by team by week, overtime rate, span of control by level, goal attainment

Design direction — decide once, apply everywhere. Do not let Claude Code default to a generic admin template. Pick something specific to the subject: HR data is about *people over time*, so make time the structural spine (consistent left-to-right chronology, cohorts as horizontal bands) and reserve your single accent colour exclusively for risk signals — so the only red on the screen always means "a person is likely to leave." Muted greys and blues everywhere else, one strong accent, generous whitespace, real type hierarchy with a distinct display face for KPI numbers and a clean utility face for table data. State this direction in the prompt so it survives across pages.

`/wrap` after each page. Commit each page.

### Phase 6 — AI layer (H18:30–H20:00)

> Implement the three AI features.
> 1. app/ai/nl_query.py — natural language to SQL. Hard constraints: SELECT only, allowlisted views only (never base tables), mandatory LIMIT 500, statement timeout, and the generated SQL is returned to the user alongside the results so the answer is auditable. Prefill the assistant response to force clean JSON output. Reject anything that fails validation with a clear message rather than executing it.
> 2. app/ai/narrative.py — takes the current filter context and the computed metrics, returns a 3-bullet executive summary naming the specific departments and numbers. Also produces the plain-English explanation for an individual flight-risk score from its component weights.
> 3. app/ai/comments.py — batch-classify open-text survey comments into themes with sentiment using the Haiku model, cached in a table so the dashboard never waits on a live call.
> Cache all AI responses. Every AI feature must degrade gracefully to a clear message if the API call fails — the demo cannot show a stack trace.

Then build the **Ask** page: query box, generated SQL shown in a collapsible panel, result table, and one-click example questions. Seed those examples with questions that hit your planted scenarios — "which managers have the worst attrition?" is a guaranteed win.

### Phase 7 — Deploy (H20:00–H21:30)

> Prepare production deployment. Backend: Render web service with a render.yaml, gunicorn + uvicorn workers, env vars documented in .env.example, migrations and seed run on first boot via a release command. Frontend: Vercel with VITE_API_URL, SPA rewrites. Verify CORS between the two production origins. Then walk the full user journey against the deployed URLs and report any endpoint that fails or returns empty data.

Buffer here is deliberate — first deploys always cost more than planned. Cold starts on Render free tier take ~50s: **hit the URL 2 minutes before you record** so it's warm.

### Phase 8 — Loom + README (H21:30–H23:00)

Recording script below. Then:

> Write the README: what this is, the four metric domains with the headline metrics, architecture diagram from docs/ARCHITECTURE.md, live demo link, local setup in 5 commands, the synthetic data disclaimer stated prominently, a "Built with Claude Code" section pulled from docs/SESSION_LOG.md, and an honest "Not in scope / next steps" section.

**H23:00–H24:00 — submit with an hour to spare.** Do not use the last hour for one more feature.

---

## 7. Loom script (4:30 target)

| Time | Beat | What's on screen |
|---|---|---|
| 0:00–0:30 | The problem: HR teams have data in six systems and answer questions in spreadsheets weeks late. This gives them the answer in one screen. | Overview page, live |
| 0:30–1:00 | Architecture in 30 seconds: Postgres star schema → SQL views → FastAPI metric services → React → Claude layer on top. 1,850 employee records, 3 years, all synthetic. | Mermaid architecture diagram |
| 1:00–1:30 | Talent Acquisition: point at the Sales interview bottleneck in the funnel, then the source-effectiveness scatter. Say the line: *agency is our most expensive channel and our worst-retaining one.* | Acquisition page |
| 1:30–2:30 | Retention — spend the most time here. Attrition trend, then the manager heatmap surfacing M-114, then the flight-risk table, expand one employee and read the reasons aloud. | Retention page |
| 2:30–3:00 | Engagement: eNPS trend, the post-reorg dip in Belonging, and the engagement-quartile vs attrition chart proving the lag. Show Claude-extracted comment themes. | Engagement page |
| 3:00–3:20 | Productivity: the Support burnout story — overtime up, utilization over 95%, workload driver lowest. Tie it back to the attrition chart. | Productivity page |
| 3:20–4:00 | Ask the data: type *"which managers have the highest regretted attrition this year?"* Show the generated SQL. Emphasize it's auditable, view-scoped, and read-only. | Ask page |
| 4:00–4:30 | How it was built: ~80% authored by Claude Code. Show CLAUDE.md, the metric-verifier subagent output, the test suite passing. Then one honest sentence on what's out of scope. | Terminal + CLAUDE.md |

**Recording notes:** write the exact opening and closing sentences out and read them — improvised intros eat 40 seconds. Record in one take with the page already warm. Zoom to 125% so numbers are legible in playback.

---

## 8. Making the "80% Claude Code" claim verifiable

They will look for this. Make it trivial to see:

1. **Commit the `.claude/` directory.** Your CLAUDE.md, commands, hooks, and subagent definitions are the strongest possible evidence of deliberate methodology.
2. **Co-author trailers.** Keep `Co-Authored-By: Claude <noreply@anthropic.com>` on Claude-authored commits. Your git log becomes the audit trail.
3. **`docs/SESSION_LOG.md`** — one paragraph per phase: the prompt strategy, what you accepted, what you rejected and why. The rejections matter most; they show judgement rather than autocomplete.
4. **Screenshot plan mode at least twice.** A plan you reviewed and corrected is the artifact that separates "used an AI tool" from "directed an AI tool."
5. **Name the 20% you did yourself** in the README: schema design decisions, the metric formulas, the planted-scenario design, the six rejected plans, deployment config. Owning the boundary honestly reads far better than claiming everything.

---

## 9. Risks and pre-decided cut lines

| Risk | Mitigation / cut |
|---|---|
| Metric numbers are wrong and someone notices live | The tiny_org hand-computed fixtures plus the metric-verifier subagent. Non-negotiable, phase 3. |
| Frontend eats the schedule | Cut Productivity page to 3 KPI cards + one chart. Never cut Retention. |
| NL→SQL is unreliable in the demo | Ship 4 pre-tested example questions as buttons. Demo those. Free-text stays available but isn't the demo path. |
| Render cold start kills the recording | Warm the URL 2 min before recording. Have a local fallback recording ready. |
| Data has no visible story | Validate the report in phase 2. This is why phase 2 gets 2 full hours. |
| Claude Code context drift on long sessions | `/clear` between phases, `/compact` at 70%, commit every phase. |
| Scope creep at hour 20 | Feature freeze at H20:00. Written down here so you can point at it. |

**If you are 3+ hours behind at H13:30:** cut the Ask page, cut Productivity to KPI cards only, cut cohort survival curves. Keep Overview + Acquisition + Retention + Engagement + narrative summaries + deploy. That is still a strong submission. An undeployed 100% is worth less than a deployed 70%.

---

## 10. Your first three commands

```bash
mkdir people-analytics && cd people-analytics && git init
# write CLAUDE.md, docs/METRICS.md, docs/BUILD_PLAN.md, .claude/* first — 45 min, do not skip
claude
```

Then, inside Claude Code:

```
/phase 0
```
