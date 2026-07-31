import { Fragment, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Card, PageHeader } from '@/components/Card'
import { ChartCard, DataTable } from '@/components/ChartCard'
import {
  AXIS_LINE,
  AXIS_TICK,
  CHART_MARGIN,
  ChartBody,
  ChartStat,
  ChartTooltip,
  FILL_GAP,
  GRID,
  Legend,
} from '@/components/charts/chrome'
import { Async, ChartSkeleton } from '@/components/States'
import { useMetric } from '@/hooks/useMetric'
import type {
  AttritionPoint,
  FlightRisk,
  ManagerAttrition,
  SurvivalPoint,
  TenureBand,
} from '@/lib/api'
import {
  formatCount,
  formatDecimal,
  formatMonth,
  formatQuarter,
  formatRate,
} from '@/lib/format'

const DEPARTMENTS: Record<number, string> = {
  1: 'Engineering',
  2: 'Sales',
  3: 'Support',
  4: 'Operations',
  5: 'Product',
  6: 'Marketing',
  7: 'Finance',
  8: 'People',
}

const VOLUNTARY = 'var(--color-series-1)'
const INVOLUNTARY = 'var(--color-series-2)'

export default function Retention() {
  return (
    <>
      <PageHeader
        title="Retention"
        description="Who is leaving, from which teams, at what tenure — and who is likely to leave next."
        meta="Every rate divides by average headcount for the period, never end-of-period headcount."
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="xl:col-span-2">
          <AttritionTrend />
        </div>
        <TenureDistribution />
        <CohortSurvival />
        <div className="xl:col-span-2">
          <ManagerHeatmap />
        </div>
        <div className="xl:col-span-2">
          <FlightRiskTable />
        </div>
      </div>
    </>
  )
}

// --- Attrition trend --------------------------------------------------------

function AttritionTrend() {
  const query = useMetric<AttritionPoint[]>('/api/retention/attrition')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton height={280} /></Card>}>
      {(envelope) => {
        const rows = envelope.data
        const exits = rows.reduce((sum, row) => sum + row.terminations, 0)
        const headcountMonths = rows.reduce((sum, row) => sum + (row.avg_headcount ?? 0), 0)
        const annualized = headcountMonths ? (exits * 12) / headcountMonths : null

        return (
          <ChartCard
            title="Attrition over time"
            subtitle="Exits per month, split by whether the person chose to leave."
            stat={
              <div className="flex gap-8">
                <ChartStat value={formatRate(annualized)} label="annualized, this slice" />
                <ChartStat value={formatCount(exits)} label="exits in period" />
              </div>
            }
            legend={
              <Legend
                items={[
                  { label: 'Voluntary', color: VOLUNTARY },
                  { label: 'Involuntary', color: INVOLUNTARY },
                ]}
              />
            }
            footnote="Counts share one axis. The annualized rate is stated above rather than drawn as a second y-scale — two scales on one plot invent a correlation that is not in the data."
            chart={
              <ChartBody height={280}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rows} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    <XAxis
                      dataKey="period"
                      tickFormatter={formatMonth}
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                      minTickGap={24}
                    />
                    <YAxis
                      tick={AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      width={36}
                      allowDecimals={false}
                    />
                    <Tooltip
                      cursor={{ fill: 'var(--color-ink-100)' }}
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={formatMonth(String(label))}
                            rows={[
                              {
                                label: 'Voluntary',
                                value: formatCount(payload[0]?.payload.voluntary_terminations),
                                color: VOLUNTARY,
                              },
                              {
                                label: 'Involuntary',
                                value: formatCount(payload[0]?.payload.involuntary_terminations),
                                color: INVOLUNTARY,
                              },
                            ]}
                            note={`Annualized ${formatRate(payload[0]?.payload.annualized_rate)} · avg headcount ${formatDecimal(payload[0]?.payload.avg_headcount)}`}
                          />
                        ) : null
                      }
                    />
                    <Bar
                      dataKey="voluntary_terminations"
                      stackId="exits"
                      fill={VOLUNTARY}
                      {...FILL_GAP}
                      isAnimationActive={false}
                    />
                    <Bar
                      dataKey="involuntary_terminations"
                      stackId="exits"
                      fill={INVOLUNTARY}
                      radius={[4, 4, 0, 0]}
                      {...FILL_GAP}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </ChartBody>
            }
            table={
              <DataTable
                rows={rows}
                rowKey={(row) => row.period}
                columns={[
                  { key: 'period', header: 'Month', render: (row) => formatMonth(row.period) },
                  {
                    key: 'vol',
                    header: 'Voluntary',
                    align: 'right',
                    render: (row) => formatCount(row.voluntary_terminations),
                  },
                  {
                    key: 'invol',
                    header: 'Involuntary',
                    align: 'right',
                    render: (row) => formatCount(row.involuntary_terminations),
                  },
                  {
                    key: 'avg',
                    header: 'Avg headcount',
                    align: 'right',
                    render: (row) => formatDecimal(row.avg_headcount),
                  },
                  {
                    key: 'rate',
                    header: 'Annualized',
                    align: 'right',
                    render: (row) => formatRate(row.annualized_rate),
                  },
                ]}
              />
            }
          />
        )
      }}
    </Async>
  )
}

// --- Tenure -----------------------------------------------------------------

/** Ordered bands, so an ordinal ramp is correct here — the categories have a natural
 *  order, unlike a value-ramp on nominal categories, which would be double-encoding. */
const TENURE_STEPS: Record<string, string> = {
  '<6m': 'var(--color-seq-250)',
  '6-12m': 'var(--color-seq-350)',
  '1-2y': 'var(--color-seq-450)',
  '2-5y': 'var(--color-seq-550)',
  '5y+': 'var(--color-seq-700)',
}

function TenureDistribution() {
  const query = useMetric<TenureBand[]>('/api/retention/tenure')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = envelope.data
        const total = rows.reduce((sum, row) => sum + row.headcount, 0)

        return (
          <ChartCard
            title="Tenure distribution"
            subtitle="Headcount by tenure band, at the latest month in range."
            stat={<ChartStat value={formatCount(total)} label="people" />}
            footnote="A distribution is a snapshot, not an accumulation — this is one month, not a sum across the period."
            chart={
              <ChartBody height={240}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rows} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    <XAxis
                      dataKey="tenure_band"
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                    />
                    <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={40} />
                    <Tooltip
                      cursor={{ fill: 'var(--color-ink-100)' }}
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={String(label)}
                            rows={[
                              {
                                label: 'Headcount',
                                value: formatCount(payload[0]?.payload.headcount),
                              },
                              {
                                label: 'Share',
                                value: formatRate(
                                  total ? payload[0]?.payload.headcount / total : null,
                                ),
                              },
                            ]}
                          />
                        ) : null
                      }
                    />
                    <Bar dataKey="headcount" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                      {rows.map((row) => (
                        <Cell
                          key={row.tenure_band}
                          fill={TENURE_STEPS[row.tenure_band] ?? 'var(--color-seq-450)'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartBody>
            }
            table={
              <DataTable
                rows={rows}
                rowKey={(row) => row.tenure_band}
                columns={[
                  { key: 'band', header: 'Tenure', render: (row) => row.tenure_band },
                  {
                    key: 'headcount',
                    header: 'Headcount',
                    align: 'right',
                    render: (row) => formatCount(row.headcount),
                  },
                  {
                    key: 'share',
                    header: 'Share',
                    align: 'right',
                    render: (row) => formatRate(total ? row.headcount / total : null),
                  },
                ]}
              />
            }
          />
        )
      }}
    </Async>
  )
}

// --- Cohort survival --------------------------------------------------------

const CLIFF_FROM = 14
const CLIFF_TO = 18

function CohortSurvival() {
  const query = useMetric<SurvivalPoint[]>('/api/retention/cohort-survival')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = envelope.data
        const twelve = rows.find((row) => row.months_since_hire === 12)

        return (
          <ChartCard
            title="Cohort survival"
            subtitle="Share of a hire cohort still employed, by months since joining."
            stat={
              <ChartStat
                value={formatRate(twelve?.survival_rate ?? null)}
                label="still here at 12 months"
              />
            }
            footnote="Each offset counts only cohorts that have actually reached it — someone hired three months ago cannot inform 12-month retention, so they are excluded rather than counted as retained."
            chart={
              <ChartBody height={240}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={rows} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    {/* The planted tenure cliff. Shaded rather than annotated with a
                        dashed line, which would read as a threshold. */}
                    <ReferenceArea
                      x1={CLIFF_FROM}
                      x2={CLIFF_TO}
                      fill="var(--color-ink-100)"
                      fillOpacity={1}
                    />
                    <XAxis
                      dataKey="months_since_hire"
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                      label={{
                        value: 'months since hire',
                        position: 'insideBottom',
                        offset: -2,
                        style: { fill: 'var(--color-ink-500)', fontSize: 11 },
                      }}
                    />
                    <YAxis
                      tick={AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      width={44}
                      domain={[0, 1]}
                      tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
                    />
                    <Tooltip
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={`Month ${label}`}
                            rows={[
                              {
                                label: 'Still employed',
                                value: formatRate(payload[0]?.payload.survival_rate),
                              },
                              {
                                label: 'Cohort size',
                                value: formatCount(payload[0]?.payload.cohort_size),
                              },
                            ]}
                          />
                        ) : null
                      }
                    />
                    <Line
                      type="monotone"
                      dataKey="survival_rate"
                      stroke="var(--color-series-1)"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--color-surface)' }}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </ChartBody>
            }
            table={
              <DataTable
                rows={rows}
                rowKey={(row) => String(row.months_since_hire)}
                columns={[
                  {
                    key: 'month',
                    header: 'Months since hire',
                    render: (row) => String(row.months_since_hire),
                  },
                  {
                    key: 'cohort',
                    header: 'Cohort',
                    align: 'right',
                    render: (row) => formatCount(row.cohort_size),
                  },
                  {
                    key: 'active',
                    header: 'Still active',
                    align: 'right',
                    render: (row) => formatCount(row.still_active),
                  },
                  {
                    key: 'rate',
                    header: 'Survival',
                    align: 'right',
                    render: (row) => formatRate(row.survival_rate),
                  },
                ]}
              />
            }
          />
        )
      }}
    </Async>
  )
}

// --- Manager heatmap --------------------------------------------------------

/** Fixed thresholds, never quantiles of the current slice.
 *
 * A relative scale would repaint every surviving manager the moment a filter removed
 * one — a reader who learned "dark means bad" would be misled by a colour that only
 * means "worst of whatever is left".
 */
function heatStep(rate: number | null): { bg: string; fg: string } {
  if (rate == null) return { bg: 'transparent', fg: 'var(--color-ink-500)' }
  if (rate < 0.15) return { bg: 'var(--color-seq-100)', fg: 'var(--color-ink-900)' }
  if (rate < 0.3) return { bg: 'var(--color-seq-250)', fg: 'var(--color-ink-900)' }
  if (rate < 0.5) return { bg: 'var(--color-seq-350)', fg: 'var(--color-ink-900)' }
  if (rate < 0.75) return { bg: 'var(--color-seq-550)', fg: '#ffffff' }
  return { bg: 'var(--color-seq-700)', fg: '#ffffff' }
}

const HEAT_LEGEND = [
  { label: '<15%', bg: 'var(--color-seq-100)' },
  { label: '15–30%', bg: 'var(--color-seq-250)' },
  { label: '30–50%', bg: 'var(--color-seq-350)' },
  { label: '50–75%', bg: 'var(--color-seq-550)' },
  { label: '75%+', bg: 'var(--color-seq-700)' },
]

function ManagerHeatmap() {
  const query = useMetric<ManagerAttrition[]>('/api/retention/attrition/by-manager')

  return (
    <Async
      query={query}
      skeleton={<Card><ChartSkeleton /></Card>}
      empty={{
        title: 'No managers clear the reporting threshold',
        hint: 'Attrition by manager is only reported for teams averaging at least 8 reports, because a rate over four people is noise.',
      }}
    >
      {(envelope) => {
        const rows = [...envelope.data].sort(
          (a, b) => (b.annualized_rate ?? 0) - (a.annualized_rate ?? 0),
        )
        const worst = rows[0]

        return (
          <ChartCard
            title="Attrition by manager"
            subtitle="Quarterly, for teams averaging at least eight reports."
            stat={
              worst ? (
                <ChartStat
                  value={formatRate(worst.annualized_rate)}
                  label={`highest — ${worst.manager_id}, ${formatQuarter(worst.period)}`}
                />
              ) : undefined
            }
            legend={
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className="font-sans text-xs text-ink-500">Annualized attrition</span>
                {HEAT_LEGEND.map((step) => (
                  <span key={step.label} className="flex items-center gap-1.5">
                    <span
                      aria-hidden="true"
                      className="h-3 w-5 rounded-[2px] ring-1 ring-ink-200"
                      style={{ backgroundColor: step.bg }}
                    />
                    <span className="tnum font-sans text-xs text-ink-700">{step.label}</span>
                  </span>
                ))}
              </div>
            }
            footnote="The colour scale uses fixed bands, not quantiles of the current filter — so a manager's shade means the same thing whichever slice you are looking at. Rate alone favours small teams; read it beside the report count."
            chart={
              // A bare `overflow-y-auto` clips the final row through its middle, which in a
              // screenshot or a recording reads as a rendering fault rather than as "there
              // is more below". Sticky header, an explicit count, and a fade at the cut make
              // the boundary intentional.
              <div>
                <div className="relative">
                  <div className="max-h-[26rem] overflow-y-auto">
                  <DataTable
                    stickyHeader
                    rows={rows.slice(0, 40)}
                    rowKey={(row) => `${row.period}-${row.manager_id}`}
                    columns={[
                      { key: 'mgr', header: 'Manager', render: (row) => row.manager_id },
                      {
                        key: 'dept',
                        header: 'Department',
                        render: (row) => DEPARTMENTS[row.department_id ?? 0] ?? '—',
                      },
                      { key: 'q', header: 'Quarter', render: (row) => formatQuarter(row.period) },
                      {
                        key: 'reports',
                        header: 'Avg team',
                        align: 'right',
                        render: (row) => formatDecimal(row.avg_reports),
                      },
                      {
                        key: 'exits',
                        header: 'Exits',
                        align: 'right',
                        render: (row) => formatCount(row.terminations),
                      },
                      {
                        key: 'rate',
                        header: 'Annualized',
                        align: 'right',
                        render: (row) => {
                          const step = heatStep(row.annualized_rate)
                          return (
                            <span
                              className="tnum inline-block min-w-[4.5rem] rounded px-2 py-0.5 text-right font-medium"
                              style={{ backgroundColor: step.bg, color: step.fg }}
                            >
                              {formatRate(row.annualized_rate)}
                            </span>
                          )
                        },
                      },
                    ]}
                    />
                  </div>

                  {/* The fade belongs to the scroll box, not to the card. Hung on the outer
                      wrapper it covered the caption below instead of the cut edge above. */}
                  {rows.length > 40 && (
                    <div
                      aria-hidden="true"
                      className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-white to-transparent"
                    />
                  )}
                </div>

                <p className="mt-2 font-sans text-xs text-ink-500">
                  Showing the {Math.min(40, rows.length)} highest of {formatCount(rows.length)}{' '}
                  manager-quarters. Switch to Table for all of them.
                </p>
              </div>
            }
            table={
              <DataTable
                rows={rows}
                rowKey={(row) => `${row.period}-${row.manager_id}-t`}
                columns={[
                  { key: 'mgr', header: 'Manager', render: (row) => row.manager_id },
                  {
                    key: 'dept',
                    header: 'Department',
                    render: (row) => DEPARTMENTS[row.department_id ?? 0] ?? '—',
                  },
                  { key: 'q', header: 'Quarter', render: (row) => formatQuarter(row.period) },
                  {
                    key: 'reports',
                    header: 'Distinct reports',
                    align: 'right',
                    render: (row) => formatCount(row.reports),
                  },
                  {
                    key: 'avg',
                    header: 'Avg team',
                    align: 'right',
                    render: (row) => formatDecimal(row.avg_reports),
                  },
                  {
                    key: 'exits',
                    header: 'Exits',
                    align: 'right',
                    render: (row) => formatCount(row.terminations),
                  },
                  {
                    key: 'vol',
                    header: 'Voluntary',
                    align: 'right',
                    render: (row) => formatCount(row.voluntary_terminations),
                  },
                  {
                    key: 'rate',
                    header: 'Annualized',
                    align: 'right',
                    render: (row) => formatRate(row.annualized_rate),
                  },
                ]}
              />
            }
          />
        )
      }}
    </Async>
  )
}

// --- Flight risk ------------------------------------------------------------

/** Only HIGH earns the reserved accent. The whole design direction rests on the only
 *  red on screen meaning "a person is likely to leave" — spending it on `elevated`
 *  would make it mean "somewhat", which is to say nothing. */
const BAND_STYLE: Record<string, string> = {
  high: 'bg-risk-soft text-risk font-medium',
  elevated: 'bg-ink-100 text-ink-900',
  moderate: 'bg-ink-50 text-ink-700',
  low: 'bg-ink-50 text-ink-500',
}

const COMPONENT_LABELS: Record<string, string> = {
  tenure: 'Tenure band',
  promotion_gap: 'Months since last promotion',
  engagement_delta: 'Engagement vs department mean',
  manager_attrition: "Manager's team attrition",
  comp_percentile: 'Position in pay band',
}

function FlightRiskTable() {
  const query = useMetric<FlightRisk[]>('/api/flight-risk', { extraParams: { limit: 25 } })
  const [expanded, setExpanded] = useState<string | null>(null)

  return (
    <Async
      query={query}
      skeleton={<Card><ChartSkeleton /></Card>}
      empty={{
        title: 'No scores yet',
        hint: 'Flight risk is computed by the backend and stored; run the scorer to populate it.',
      }}
    >
      {(envelope) => (
        <Card
          title="Flight risk"
          subtitle="Highest scores first. Expand a row to see why."
        >
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-ink-200">
                {['Employee', 'Score', 'Band', ''].map((header, index) => (
                  <th
                    key={header || index}
                    scope="col"
                    className={`px-2 py-2 font-sans text-xs font-medium text-ink-500 ${
                      index === 1 ? 'text-right' : 'text-left'
                    }`}
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {envelope.data.map((row) => {
                const isOpen = expanded === row.employee_id
                const parts = Object.entries(row.components).sort(
                  (a, b) => b[1].contribution - a[1].contribution,
                )
                return (
                  // A keyed Fragment, not `<>`: a bare fragment returned from a map has
                  // no key and React warns on every render.
                  <Fragment key={row.employee_id}>
                    <tr className="border-b border-ink-100">
                      <td className="px-2 py-1.5 font-sans text-sm text-ink-900">
                        {row.employee_id}
                      </td>
                      <td className="tnum px-2 py-1.5 text-right font-sans text-sm font-medium text-ink-900">
                        {formatDecimal(row.score)}
                      </td>
                      <td className="px-2 py-1.5">
                        <span
                          className={`rounded px-2 py-0.5 font-sans text-xs capitalize ${
                            BAND_STYLE[row.band] ?? ''
                          }`}
                        >
                          {row.band}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <button
                          type="button"
                          aria-expanded={isOpen}
                          onClick={() => setExpanded(isOpen ? null : row.employee_id)}
                          className="rounded px-2 py-0.5 font-sans text-xs text-ink-700 underline-offset-2 hover:underline"
                        >
                          {isOpen ? 'Hide' : 'Why?'}
                        </button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="border-b border-ink-100">
                        <td colSpan={4} className="bg-ink-50 px-4 py-3">
                          <ul className="space-y-1.5">
                            {parts.map(([name, part]) => (
                              <li key={name} className="flex items-center gap-3">
                                <span className="w-56 shrink-0 font-sans text-xs text-ink-700">
                                  {COMPONENT_LABELS[name] ?? name}
                                </span>
                                <span className="h-1.5 w-40 shrink-0 overflow-hidden rounded-full bg-ink-200">
                                  <span
                                    className="block h-full rounded-full bg-seq-450"
                                    style={{ width: `${part.score}%` }}
                                  />
                                </span>
                                <span className="tnum font-sans text-xs text-ink-900">
                                  {formatDecimal(part.score)}/100
                                </span>
                                <span className="tnum font-sans text-xs text-ink-500">
                                  weight {Math.round(part.weight * 100)}% · contributes{' '}
                                  {formatDecimal(part.contribution)}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>

          <p className="mt-3 font-sans text-[11px] leading-relaxed text-ink-500">
            A transparent weighted score, not a model — five components, fixed weights summing
            to 1.0, each explainable in one sentence. Filter by manager to see one team's risk.
          </p>
        </Card>
      )}
    </Async>
  )
}
