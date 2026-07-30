/** Typed client for the People Analytics API.
 *
 * Every backend response uses one envelope, so it is decoded in exactly one
 * place. Callers get `data` and `meta` already typed and never touch `fetch`.
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

/** A filter set understood by every metric endpoint. */
export interface MetricFilters {
  date_from?: string
  date_to?: string
  department_id?: number
  location_id?: number
  level?: number
  manager_id?: string
}

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
    const detail = await response.text().catch(() => '')
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
