import { useQueryClient } from '@tanstack/react-query'

import { Skeleton } from '@/components/States'
import { useMetric } from '@/hooks/useMetric'
import type { NarrativeSummary } from '@/lib/api'

/** The generated executive summary, above the KPI row.
 *
 * Every figure in it comes from a metric that is already on the page and already has a
 * hand-computed test behind it — the model chooses what to say, never what the number is.
 * The panel says so, because a reader deciding how much to trust a generated paragraph
 * needs to know which part was generated.
 *
 * It is deliberately quiet: no gradient, no sparkle, one accent rule down the side. A
 * summary that shouts competes with the numbers it is summarising.
 */
export function NarrativePanel() {
  const query = useMetric<NarrativeSummary>('/api/ai/narrative')
  const queryClient = useQueryClient()
  const summary = query.data?.data

  // Absent while loading, and absent for good when no key is configured. In both cases the
  // page above it is complete on its own, so the panel simply does not appear rather than
  // occupying space with an apology.
  if (query.isPending) {
    return (
      <section className="mb-4 border-l-2 border-ink-200 pl-4">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="mt-3 h-4 w-3/4" />
        <Skeleton className="mt-2 h-4 w-2/3" />
      </section>
    )
  }
  if (query.isError || !summary?.available || summary.bullets.length === 0) return null

  return (
    <section
      className="mb-6 border-l-2 border-seq-450 pl-4"
      aria-label="AI-generated summary of the metrics on this page"
    >
      {/* Constrained to the prose width so Refresh sits beside the text it refreshes.
          Left to span the grid it lands a thousand pixels away at the screen edge, next to
          nothing, reading as a stray control. */}
      <header className="flex max-w-prose flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="font-sans text-sm font-semibold tracking-tight text-ink-900">
          {summary.headline || 'Summary'}
        </h2>
        <button
          type="button"
          onClick={() => queryClient.invalidateQueries({ queryKey: ['/api/ai/narrative'] })}
          disabled={query.isFetching}
          className="font-sans text-[11px] text-ink-500 underline-offset-2 hover:text-ink-900 hover:underline disabled:no-underline"
        >
          {query.isFetching ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      <ul className={`mt-2 space-y-1.5 ${query.isFetching ? 'is-refetching' : ''}`}>
        {summary.bullets.map((bullet) => (
          <li
            key={bullet}
            className="max-w-prose font-sans text-sm leading-relaxed text-ink-700 before:mr-2 before:text-ink-300 before:content-['—']"
          >
            {bullet}
          </li>
        ))}
      </ul>

      <p className="mt-2 font-sans text-[11px] text-ink-500">
        Written by {summary.model || 'the AI layer'} from the metrics on this page — it
        selects and phrases, it never calculates.
        {summary.stale
          ? ' The provider is unavailable, so this is the last summary generated for this slice.'
          : summary.cached
            ? ' Cached, so a repeat visit costs nothing.'
            : ''}
      </p>
    </section>
  )
}
