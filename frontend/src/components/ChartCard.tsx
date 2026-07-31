import { useId, useState, type ReactNode } from 'react'

/** A chart card with a table-view twin.
 *
 * Every chart ships one. Three reasons, all of which apply here:
 *
 * - three slots in the validated palette sit below 3:1 contrast on white, and the
 *   relief rule for that is visible labels **or** a table view;
 * - a value reachable only by hovering is unreachable by keyboard and by anyone
 *   reading a screenshot;
 * - it is the WCAG-clean equivalent of any colour-encoded scale, which the heatmap
 *   table and the risk bands both are.
 *
 * The toggle is per card rather than global because a reader wants the numbers behind
 * one chart, not to leave chart mode entirely.
 */
export function ChartCard({
  title,
  subtitle,
  stat,
  chart,
  table,
  legend,
  footnote,
}: {
  title: string
  subtitle?: string
  stat?: ReactNode
  chart: ReactNode
  table: ReactNode
  legend?: ReactNode
  footnote?: string
}) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const panelId = useId()

  return (
    <section className="rounded-lg border border-ink-200 bg-white p-5">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="font-sans text-sm font-semibold tracking-tight text-ink-900">{title}</h2>
          {subtitle && (
            <p className="mt-0.5 font-sans text-xs leading-relaxed text-ink-500">{subtitle}</p>
          )}
        </div>

        <div
          className="flex shrink-0 rounded border border-ink-200 p-0.5"
          role="tablist"
          aria-label={`${title} view`}
        >
          {(['chart', 'table'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              role="tab"
              aria-selected={view === mode}
              aria-controls={panelId}
              onClick={() => setView(mode)}
              className={[
                'rounded px-2 py-0.5 font-sans text-xs capitalize transition-colors',
                view === mode ? 'bg-ink-100 font-medium text-ink-900' : 'text-ink-500 hover:text-ink-700',
              ].join(' ')}
            >
              {mode}
            </button>
          ))}
        </div>
      </header>

      {stat && <div className="mb-4">{stat}</div>}

      <div id={panelId} role="tabpanel">
        {view === 'chart' ? (
          <>
            {chart}
            {legend}
          </>
        ) : (
          <div className="overflow-x-auto">{table}</div>
        )}
      </div>

      {footnote && (
        <p className="mt-3 font-sans text-[11px] leading-relaxed text-ink-500">{footnote}</p>
      )}
    </section>
  )
}

/** A plain data table — the table view's body, and used standalone where a table is
 *  the right form in its own right. */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyMessage = 'No rows for this slice.',
}: {
  columns: { key: string; header: string; align?: 'left' | 'right'; render: (row: T) => ReactNode }[]
  rows: T[]
  rowKey: (row: T) => string
  emptyMessage?: string
}) {
  if (rows.length === 0) {
    return <p className="py-6 text-center font-sans text-sm text-ink-500">{emptyMessage}</p>
  }

  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-ink-200">
          {columns.map((column) => (
            <th
              key={column.key}
              scope="col"
              className={`px-2 py-2 font-sans text-xs font-medium text-ink-500 ${
                column.align === 'right' ? 'text-right' : 'text-left'
              }`}
            >
              {column.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={rowKey(row)} className="border-b border-ink-100 last:border-0">
            {columns.map((column) => (
              <td
                key={column.key}
                className={`px-2 py-1.5 font-sans text-sm text-ink-900 ${
                  // Tabular figures where digits align vertically — table rows and axis
                  // ticks only, never on a large standalone number.
                  column.align === 'right' ? 'tnum text-right' : 'text-left'
                }`}
              >
                {column.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
