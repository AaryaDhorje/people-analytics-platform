/** Typed client for the People Analytics API.
 *
 * Every backend response uses one envelope, so it is decoded in exactly one place.
 * Callers get `data` and `meta` already typed and never touch `fetch`.
 */

export interface Meta {
  /** ISO-8601 UTC timestamp at which the backend computed the response. */
  as_of: string
  filters_applied: Record<string, unknown>
  row_count: number
}

export interface Envelope<T> {
  data: T
  meta: Meta
}

export interface HealthPayload {
  status: string
  env: string
  version: string
}

/** The filter set every metric endpoint accepts. */
export interface MetricFilters {
  date_from?: string
  date_to?: string
  department_id?: number
  location_id?: number
  level?: number
  manager_id?: string
}

// --- Response shapes, mirroring app/schemas/metrics.py ----------------------

export interface Kpi {
  key: string
  label: string
  value: number | null
  previous: number | null
  delta: number | null
  delta_pct: number | null
  unit: 'people' | 'rate' | 'days' | 'currency' | 'score'
  higher_is_better: boolean | null
  sparkline: (number | null)[]
}

export interface Overview {
  as_of: string | null
  period_from: string | null
  period_to: string | null
  comparison_from: string | null
  comparison_to: string | null
  kpis: Kpi[]
}

export interface HeadcountPoint {
  period: string
  headcount: number
  active_start: number
  active_end: number
  avg_headcount: number | null
  hires: number
  terminations: number
  total_fte: number | null
}

export interface AttritionPoint {
  period: string
  terminations: number
  voluntary_terminations: number
  involuntary_terminations: number
  avg_headcount: number | null
  annualized_rate: number | null
}

export interface ManagerAttrition {
  period: string
  manager_id: string
  department_id: number | null
  reports: number
  avg_reports: number | null
  terminations: number
  voluntary_terminations: number
  headcount_months: number | null
  annualized_rate: number | null
}

/** One manager over a trailing window, already ranked worst-first by the API.
 *
 * `window_from`, `window_to`, `months` and `company_annualized_rate` describe the window
 * rather than the manager and repeat on every row — the same denormalisation
 * `RequisitionAging.threshold_days` uses, so the response stays a plain list.
 */
export interface ManagerAttritionTrailing {
  manager_id: string
  department_id: number | null
  window_from: string
  window_to: string
  months: number
  quarters: number
  months_observed: number
  peak_reports: number
  avg_reports: number
  terminations: number
  voluntary_terminations: number
  headcount_months: number
  annualized_rate: number | null
  company_annualized_rate: number | null
}

export interface TenureBand {
  tenure_band: string
  headcount: number
}

export interface SurvivalPoint {
  months_since_hire: number
  cohort_size: number
  still_active: number
  survival_rate: number
}

export interface FunnelStage {
  stage: string
  applications: number
  conversion_from_previous: number | null
  mean_dwell_days: number | null
  still_in_stage: number
}

export interface Enps {
  responses: number
  promoters: number
  passives: number
  detractors: number
  enps: number | null
}

export interface EnpsPoint {
  period: string
  responses: number
  promoters: number
  detractors: number
  enps: number | null
}

/** Driver keys are added dynamically by the backend, hence the index signature. */
export interface DriverDepartmentPoint {
  department_id: number | null
  responses: number
  engagement_index: number | null
  [driver: string]: number | null
}

export interface Participation {
  survey_id: number
  period: string
  responses: number
  eligible_employees: number
  participation_rate: number | null
}

export interface QuartileAttrition {
  quartile: number
  respondent_observations: number
  terminations: number
  headcount_months: number
  annualized_rate: number | null
}

export interface CommentTheme {
  theme: string
  sentiment: string
  volume: number
  mean_confidence: number | null
}

export interface TimeToFill {
  requisitions: number
  filled_positions: number
  day_sum: number
  mean_days: number | null
}

export interface TimeToFillPoint {
  period: string
  filled_positions: number
  mean_days: number | null
}

export interface SourceCost {
  source_id: number | null
  hires: number
  total_cost: number | null
  external_cost: number | null
  cost_per_hire: number | null
}

export interface CohortRetention {
  source_id: number | null
  months_since_hire: number
  cohort_size: number
  still_active: number
  retention_rate: number | null
}

export interface RequisitionAging {
  department_id: number | null
  open_requisitions: number
  aged_requisitions: number
  max_age_days: number | null
  threshold_days: number
}

export interface RevenuePerFte {
  department_id: number | null
  period: string
  revenue_amount: number
  fte_months: number
  months_observed: number
  avg_fte: number | null
  revenue_per_fte: number | null
}

export interface UtilizationWeek {
  period: string
  department_id: number | null
  billable_hours: number
  available_hours: number
  utilization: number | null
}

export interface OvertimeMonth {
  period: string
  department_id: number | null
  total_hours: number
  overtime_hours: number
  overtime_rate: number | null
}

export interface SpanByLevel {
  department_id: number | null
  job_level_id: number | null
  managers: number
  direct_reports: number
  span: number | null
}

export interface GoalAttainment {
  goals: number
  goals_with_target: number
  capped_attainment_sum: number
  completed_goals: number
  missed_goals: number
  cap: number
  attainment: number | null
}

export interface Training {
  training_hours: number
  assigned: number
  completed: number
  completion_rate: number | null
  headcount_months: number
  months: number
  avg_headcount: number | null
  hours_per_head: number | null
}

export interface FlightRisk {
  employee_id: string
  as_of_month: string
  score: number
  band: 'low' | 'moderate' | 'elevated' | 'high'
  components: Record<string, { score: number; weight: number; contribution: number }>
}

export interface RiskBandCount {
  band: string
  employees: number
}

// --- Transport --------------------------------------------------------------

const BASE_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')
const DEMO_TOKEN = import.meta.env.VITE_DEMO_TOKEN ?? ''

/** Thrown for any non-2xx response, carrying enough detail to render a useful
 *  error state rather than a generic "something went wrong". */
export class ApiError extends Error {
  readonly status: number
  readonly path: string

  constructor(status: number, path: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.path = path
  }

  /** What the user should actually do about it. An error state that does not say
   *  this is just a red box. */
  get remedy(): string {
    if (this.status === 0) return 'The API may still be starting up. Retry in a moment.'
    if (this.status === 401) return 'The demo token is missing or wrong. Check VITE_DEMO_TOKEN.'
    if (this.status === 400) return 'This filter is not available for this metric. Clear it and try again.'
    if (this.status >= 500) return 'The API failed on its side. Retrying may help.'
    return 'Try clearing the filters.'
  }
}

function toQueryString(params: Record<string, unknown> | undefined): string {
  if (!params) return ''
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.append(key, String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

export async function apiGet<T>(
  path: string,
  params?: Record<string, unknown>,
): Promise<Envelope<T>> {
  const url = `${BASE_URL}${path}${toQueryString(params)}`

  let response: Response
  try {
    response = await fetch(url, {
      headers: DEMO_TOKEN ? { Authorization: `Bearer ${DEMO_TOKEN}` } : {},
    })
  } catch {
    // Distinguish "the API is not reachable" from "the API said no" — on a Render
    // free tier the first is usually a cold start, and the UI should say so.
    throw new ApiError(0, path, 'Could not reach the API. It may still be starting up.')
  }

  if (!response.ok) {
    let detail = ''
    try {
      const body = (await response.json()) as { detail?: string }
      detail = body.detail ?? ''
    } catch {
      detail = await response.text().catch(() => '')
    }
    throw new ApiError(response.status, path, detail || `Request failed (${response.status})`)
  }

  return (await response.json()) as Envelope<T>
}

export function healthQuery() {
  return {
    queryKey: ['health'] as const,
    queryFn: () => apiGet<HealthPayload>('/health'),
  }
}
