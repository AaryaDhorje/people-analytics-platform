import { Area, AreaChart, ResponsiveContainer } from 'recharts'

import type { Kpi } from '@/lib/api'
import { deltaTone, formatByUnit, formatDelta } from '@/lib/format'

/** A stat tile: value, period-over-period delta, sparkline.
 *
 * This is the right form here rather than a chart — the data's job is "one current
 * value plus a trend", and a one-bar bar chart would be the wrong answer to it.
 *
 * The value uses proportional figures, not `tabular-nums`: equal-width digits make a
 * large standalone number look loose. Tabular figures are for columns that align.
 */

const TONE_CLASS = {
  good: 'text-good-text',
  bad: 'text-risk',
  neutral: 'text-ink-500',
} as const

const TONE_GLYPH = {
  good: '↑',
  bad: '↑',
  neutral: '→',
} as const

export function KpiCard({ kpi }: { kpi: Kpi }) {
  const tone = deltaTone(kpi.delta_pct, kpi.higher_is_better)
  const rising = (kpi.delta_pct ?? 0) > 0
  // The glyph follows the data; the colour follows whether that direction is good.
  // Separating them is what stops a green arrow appearing on rising attrition.
  const glyph = tone === 'neutral' ? TONE_GLYPH.neutral : rising ? '↑' : '↓'

  const points = kpi.sparkline
    .map((value, index) => ({ index, value }))
    .filter((point) => point.value !== null)

  return (
    <article className="rounded-lg border border-ink-200 bg-white p-4">
      <h3 className="font-sans text-xs font-medium tracking-wide text-ink-500 uppercase">
        {kpi.label}
      </h3>

      <p className="mt-2 font-sans text-3xl leading-none font-semibold tracking-tight text-ink-900">
        {formatByUnit(kpi.value, kpi.unit)}
      </p>

      <div className="mt-2 flex items-baseline gap-1.5">
        {kpi.delta_pct == null ? (
          <span className="font-sans text-xs text-ink-500">no prior period</span>
        ) : (
          <>
            <span className={`font-sans text-xs font-medium ${TONE_CLASS[tone]}`}>
              <span aria-hidden="true">{glyph}</span> {formatDelta(kpi.delta_pct)}
            </span>
            <span className="font-sans text-xs text-ink-500">vs prior</span>
          </>
        )}
      </div>

      {points.length > 1 && (
        <div className="mt-3 h-10" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`spark-${kpi.key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-seq-450)" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="var(--color-seq-450)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="value"
                stroke="var(--color-seq-450)"
                strokeWidth={2}
                fill={`url(#spark-${kpi.key})`}
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* The sparkline is decorative — every value it encodes is reachable in the
          domain page's own chart and table. Screen readers get the number above. */}
      <p className="sr-only">
        {kpi.label}: {formatByUnit(kpi.value, kpi.unit)}
        {kpi.delta_pct != null && `, ${formatDelta(kpi.delta_pct)} versus the prior period`}
      </p>
    </article>
  )
}

export function KpiCardSkeleton() {
  return (
    <div className="rounded-lg border border-ink-200 bg-white p-4">
      <div className="h-3 w-24 animate-pulse rounded bg-ink-100" />
      <div className="mt-3 h-8 w-28 animate-pulse rounded bg-ink-100" />
      <div className="mt-3 h-3 w-20 animate-pulse rounded bg-ink-100" />
      <div className="mt-3 h-10 w-full animate-pulse rounded bg-ink-100" />
    </div>
  )
}
