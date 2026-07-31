import { PageHeader } from '@/components/Card'
import { KpiCard, KpiCardSkeleton } from '@/components/KpiCard'
import { ErrorState } from '@/components/States'
import { useMetric } from '@/hooks/useMetric'
import type { Overview as OverviewData } from '@/lib/api'
import { formatMonth } from '@/lib/format'

/** The landing page: eight headline KPIs from a single request.
 *
 * One call rather than eight — this is the first thing a cold Render instance serves,
 * and eight parallel round-trips on a waking dyno is the worst available first
 * impression. The backend assembles the row; this page only renders it.
 */
export default function Overview() {
  const query = useMetric<OverviewData>('/api/overview')

  if (query.isError) {
    return (
      <>
        <PageHeader title="Overview" />
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      </>
    )
  }

  const data = query.data?.data

  return (
    <>
      <PageHeader
        title="Overview"
        description="Eight headline measures across talent acquisition, retention, engagement and productivity."
        meta={
          data ? (
            <>
              {formatMonth(data.period_from)} – {formatMonth(data.period_to)}
              <span className="mx-2 text-ink-300">·</span>
              compared with {formatMonth(data.comparison_from)} – {formatMonth(data.comparison_to)}
            </>
          ) : null
        }
      />

      <div
        className={`grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 ${
          query.isFetching && !query.isPending ? 'is-refetching' : ''
        }`}
      >
        {query.isPending
          ? Array.from({ length: 8 }, (_, index) => <KpiCardSkeleton key={index} />)
          : data?.kpis.map((kpi) => <KpiCard key={kpi.key} kpi={kpi} />)}
      </div>

      <p className="mt-6 max-w-prose font-sans text-xs leading-relaxed text-ink-500">
        Rates are annualized where the metric is a rate. Attrition denominators are average
        headcount for the period, never end-of-period headcount. A dash means the value is
        genuinely undefined for this slice rather than zero.
      </p>
    </>
  )
}
