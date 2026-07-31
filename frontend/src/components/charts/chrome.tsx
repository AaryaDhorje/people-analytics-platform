import type { ReactNode } from 'react'

/** Shared chart chrome: axes, grid, tooltip.
 *
 * Defined once so six pages cannot drift into six different-looking charts, and so the
 * mark specs are applied by construction rather than remembered:
 *
 * - gridlines are **solid hairlines**, one shade off the surface, horizontal only.
 *   Dashed grid reads as "projection" or "threshold" when it is just a grid.
 * - axes are recessive; the data is the loud thing.
 * - lines are 2px, markers at least 8px.
 * - stacked and adjacent fills carry a 2px surface stroke, which renders as a gap
 *   between segments rather than as a border drawn around them.
 */

export const AXIS_TICK = { fill: 'var(--color-ink-500)', fontSize: 11 } as const
export const AXIS_LINE = { stroke: 'var(--color-axis)' } as const
export const GRID = {
  stroke: 'var(--color-grid)',
  strokeWidth: 1,
  vertical: false,
} as const

/** A 2px stroke in the surface colour, which separates stacked segments and adjacent
 *  bars without drawing a visible border around each mark. */
export const FILL_GAP = {
  stroke: 'var(--color-surface)',
  strokeWidth: 2,
} as const

export const CHART_MARGIN = { top: 8, right: 12, bottom: 4, left: 4 } as const

export interface TooltipRow {
  label: string
  value: string
  color?: string
}

/** Tooltips enhance, never gate — every value here is also in the table view. */
export function ChartTooltip({
  title,
  rows,
  note,
}: {
  title: string
  rows: TooltipRow[]
  note?: string
}) {
  return (
    <div className="rounded-md border border-ink-200 bg-white px-3 py-2 shadow-sm">
      <p className="font-sans text-xs font-medium text-ink-900">{title}</p>
      <ul className="mt-1.5 space-y-0.5">
        {rows.map((row) => (
          <li key={row.label} className="flex items-center gap-2">
            {row.color && (
              <span
                aria-hidden="true"
                className="h-2 w-2 shrink-0 rounded-[2px]"
                style={{ backgroundColor: row.color }}
              />
            )}
            {/* Text wears text tokens, never the series colour — the swatch carries
                identity so the label stays readable. */}
            <span className="font-sans text-xs text-ink-700">{row.label}</span>
            <span className="tnum ml-auto font-sans text-xs font-medium text-ink-900">
              {row.value}
            </span>
          </li>
        ))}
      </ul>
      {note && <p className="mt-1.5 font-sans text-[11px] text-ink-500">{note}</p>}
    </div>
  )
}

/** A legend is always present for two or more series; a single series needs none,
 *  because the card title already names it. */
export function Legend({ items }: { items: { label: string; color: string }[] }) {
  if (items.length < 2) return null
  return (
    <ul className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="h-2 w-2 rounded-[2px]"
            style={{ backgroundColor: item.color }}
          />
          <span className="font-sans text-xs text-ink-700">{item.label}</span>
        </li>
      ))}
    </ul>
  )
}

/** Sits above a chart to state the headline number, so the card answers its question
 *  before the reader parses the plot. */
export function ChartStat({
  value,
  label,
  tone = 'default',
}: {
  value: string
  label: string
  tone?: 'default' | 'risk'
}) {
  return (
    <div>
      <p
        className={`font-sans text-2xl leading-none font-semibold tracking-tight ${
          tone === 'risk' ? 'text-risk' : 'text-ink-900'
        }`}
      >
        {value}
      </p>
      <p className="mt-1 font-sans text-xs text-ink-500">{label}</p>
    </div>
  )
}

export function ChartBody({ height, children }: { height: number; children: ReactNode }) {
  // The container includes the x-axis band. Sizing it to the plot alone clips the axis
  // labels and produces a tiny nested scrollbar inside the card.
  return (
    <div style={{ height }} className="w-full">
      {children}
    </div>
  )
}
