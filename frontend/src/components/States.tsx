import type { ReactNode } from 'react'

import { ApiError } from '@/lib/api'

/** Loading, empty and error states.
 *
 * The build plan asks for "empty/error states that say what happened and what to do".
 * A red box reading "Error" satisfies neither half, so `ApiError` carries a `remedy`
 * and it is rendered here alongside the cause.
 */

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-ink-100 ${className}`} aria-hidden="true" />
}

/** Matches the shape of the content it replaces, so nothing jumps when data lands. */
export function ChartSkeleton({ height = 260 }: { height?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="w-full" />
      <div style={{ height }} className="animate-pulse rounded bg-ink-100" />
      <span className="sr-only">Loading chart</span>
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : null
  const message = error instanceof Error ? error.message : 'Unknown error.'

  return (
    <div
      role="alert"
      className="rounded-lg border border-ink-200 bg-white p-6"
    >
      <p className="font-sans text-sm font-semibold text-ink-900">
        {apiError?.status === 401
          ? 'Not authorised'
          : apiError?.status === 400
            ? 'That filter is not available here'
            : 'Could not load this'}
      </p>
      <p className="mt-1 font-sans text-sm leading-relaxed text-ink-700">{message}</p>
      {apiError && (
        <p className="mt-2 font-sans text-sm leading-relaxed text-ink-500">{apiError.remedy}</p>
      )}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded border border-ink-300 px-3 py-1.5 font-sans text-sm text-ink-900 transition-colors hover:bg-ink-50"
        >
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-ink-200 bg-white p-8 text-center">
      <p className="font-sans text-sm font-medium text-ink-700">{title}</p>
      {hint && <p className="mt-1 font-sans text-sm text-ink-500">{hint}</p>}
    </div>
  )
}

/** True for the `{ data, meta }` shape every metric endpoint returns.
 *
 * `Async` is handed the whole envelope, not the payload, so the emptiness test has to
 * look one level in. Testing the envelope itself always failed — an envelope is an
 * object, never an array — which silently disabled every `empty` prop in the app. The
 * only visible symptom was a card that rendered its header and then nothing, which is
 * why this survived a green build and was caught by looking at the page.
 */
function unwrap(value: unknown): unknown {
  return value !== null &&
    typeof value === 'object' &&
    'data' in value &&
    'meta' in value
    ? (value as { data: unknown }).data
    : value
}

/** The four states in one place, so no page can forget one.
 *
 * `isFetching` dims a stale render rather than replacing it with a skeleton, which is
 * what stops the page flashing every time a filter moves.
 */
export function Async<T>({
  query,
  children,
  empty,
  skeleton,
}: {
  query: {
    data?: T
    isPending: boolean
    isFetching: boolean
    isError: boolean
    error: unknown
    refetch: () => void
  }
  children: (data: T) => ReactNode
  empty?: { title: string; hint?: string }
  skeleton?: ReactNode
}) {
  if (query.isPending) return <>{skeleton ?? <ChartSkeleton />}</>
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  if (query.data === undefined) return <EmptyState title={empty?.title ?? 'No data'} />

  const payload = unwrap(query.data)
  const isEmptyArray = Array.isArray(payload) && payload.length === 0
  if (isEmptyArray && empty) return <EmptyState title={empty.title} hint={empty.hint} />

  return <div className={query.isFetching ? 'is-refetching' : undefined}>{children(query.data)}</div>
}
