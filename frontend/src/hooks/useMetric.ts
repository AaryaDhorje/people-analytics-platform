import { useQuery } from '@tanstack/react-query'

import { apiGet, type Envelope, type MetricFilters } from '@/lib/api'
import { useFilters } from '@/hooks/useFilters'

/** One hook for every metric endpoint.
 *
 * The filters are part of the query key, so TanStack Query caches each slice
 * separately and switching back to a previously-seen filter combination is instant
 * rather than a refetch.
 *
 * `placeholderData` holds the previous result while a new slice loads. Without it,
 * every filter change drops the page back to skeletons and the layout jumps — the
 * "skeleton flash on refetch" the data-viz guidance calls out. The stale render is
 * dimmed via `is-refetching` instead.
 */
export function useMetric<T>(
  path: string,
  options: { extraParams?: Record<string, unknown>; enabled?: boolean } = {},
) {
  const { filters } = useFilters()
  const params: Record<string, unknown> = { ...filters, ...options.extraParams }

  return useQuery<Envelope<T>>({
    queryKey: [path, params],
    queryFn: () => apiGet<T>(path, params),
    enabled: options.enabled ?? true,
    placeholderData: (previous) => previous,
    retry: (failureCount, error) => {
      // A 400 means this filter is not available for this metric, and a 401 means the
      // token is wrong. Neither improves by asking again.
      const status = (error as { status?: number })?.status
      if (status === 400 || status === 401 || status === 422) return false
      return failureCount < 2
    },
  })
}

/** Same, but ignoring the global filter bar — for endpoints that take none. */
export function useUnfilteredMetric<T>(
  path: string,
  extraParams?: Record<string, unknown>,
) {
  return useQuery<Envelope<T>>({
    queryKey: [path, extraParams ?? {}],
    queryFn: () => apiGet<T>(path, extraParams),
    placeholderData: (previous) => previous,
  })
}

export type { MetricFilters }
