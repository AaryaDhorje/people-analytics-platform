import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import type { MetricFilters } from '@/lib/api'

/** Global filter state, held in the URL rather than in React state.
 *
 * The build plan asks for filters "wired to URL search params so every view is
 * shareable", and that is the whole reason: a filtered view someone can paste into
 * Slack is worth more than one they have to describe. It also means the back button
 * works, a reload keeps the slice, and the Loom can jump straight to a URL rather
 * than clicking through four dropdowns on camera.
 *
 * Filters live above every page and scope all of them at once — never per chart.
 */

export interface FilterState extends MetricFilters {}

const NUMERIC_KEYS = ['department_id', 'location_id', 'level'] as const
const STRING_KEYS = ['date_from', 'date_to', 'manager_id'] as const

export function useFilters() {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = useMemo<FilterState>(() => {
    const next: FilterState = {}
    for (const key of NUMERIC_KEYS) {
      const raw = searchParams.get(key)
      if (raw !== null && raw !== '') {
        const parsed = Number(raw)
        if (Number.isFinite(parsed)) next[key] = parsed
      }
    }
    for (const key of STRING_KEYS) {
      const raw = searchParams.get(key)
      if (raw) next[key] = raw
    }
    return next
  }, [searchParams])

  const setFilter = useCallback(
    (key: keyof FilterState, value: string | number | undefined) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous)
          if (value === undefined || value === '' || value === null) {
            next.delete(key)
          } else {
            next.set(key, String(value))
          }
          return next
        },
        // Replace rather than push: dragging a filter should not bury the previous
        // page under twenty history entries.
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const clearFilters = useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: true })
  }, [setSearchParams])

  const activeCount = Object.keys(filters).length

  return { filters, setFilter, clearFilters, activeCount }
}
