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
