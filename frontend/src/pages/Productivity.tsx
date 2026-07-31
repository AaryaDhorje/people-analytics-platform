import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
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
  GRID,
  Legend,
} from '@/components/charts/chrome'
import { Async, ChartSkeleton } from '@/components/States'
import { useMetric } from '@/hooks/useMetric'
import type {
  GoalAttainment,
  OvertimeMonth,
  RevenuePerFte,
  SpanByLevel,
  Training,
  UtilizationWeek,
} from '@/lib/api'
import {
  formatCount,
  formatCurrency,
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

const LEVELS: Record<number, string> = {
  1: 'L1 Associate',
  2: 'L2 Analyst',
  3: 'L3 Senior',
  4: 'L4 Lead',
  5: 'L5 Manager',
  6: 'L6 Director',
}

/** Fixed slots, assigned by department id and never by rank — filtering one department
 *  out must not repaint the survivors. */
const DEPT_COLOR: Record<number, string> = {
  1: 'var(--color-series-1)',
  2: 'var(--color-series-2)',
  3: 'var(--color-series-3)',
  4: 'var(--color-series-4)',
  5: 'var(--color-series-5)',
}

export default function Productivity() {
  return (
    <>
      <PageHeader
        title="Productivity"
        description="Revenue against capacity, how hard teams are working, and whether goals land."
        meta="Denominators here are FTE and available hours, not headcount — two half-timers are one FTE, not twice the capacity of one person."
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="xl:col-span-2">
          <RevenueTrend />
        </div>
        <div className="xl:col-span-2">
          <UtilizationHeatmap />
        </div>
        <OvertimeTrend />
        <SpanOfControl />
        <div className="xl:col-span-2">
          <GoalsAndTraining />
        </div>
      </div>
    </>
  )
}

// --- Revenue per FTE --------------------------------------------------------

function RevenueTrend() {
  const query = useMetric<RevenuePerFte[]>('/api/productivity/revenue-per-fte')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = envelope.data
        const departments = [...new Set(rows.map((row) => row.department_id ?? 0))].sort()

        // One row per quarter, one column per department — Recharts needs the series
        // side by side rather than stacked long.
        const byQuarter = new Map<string, Record<string, number | string | null>>()
        for (const row of rows) {
          const entry = byQuarter.get(row.period) ?? { period: row.period }
          entry[`d${row.department_id}`] = row.revenue_per_fte
          byQuarter.set(row.period, entry)
        }
        const series = [...byQuarter.values()].sort((a, b) =>
          String(a.period).localeCompare(String(b.period)),
        )

        const latest = rows.filter((row) => row.period === series[series.length - 1]?.period)
        const best = [...latest].sort(
          (a, b) => (b.revenue_per_fte ?? 0) - (a.revenue_per_fte ?? 0),
        )[0]

        return (
          <ChartCard
            title="Revenue per FTE"
            subtitle="By department and quarter, over average full-time equivalents."
            stat={
              best ? (
                <ChartStat
                  value={formatCurrency(best.revenue_per_fte)}
                  label={`highest — ${DEPARTMENTS[best.department_id ?? 0]}, ${formatQuarter(best.period)}`}
                />
              ) : undefined
            }
            legend={
              <Legend
                items={departments.map((id) => ({
                  label: DEPARTMENTS[id] ?? `Dept ${id}`,
                  color: DEPT_COLOR[id] ?? 'var(--color-series-1)',
                }))}
              />
            }
            footnote="Only departments that carry revenue appear. The denominator is average FTE across the quarter's months, not month-end FTE — measuring at the end flatters a growing team and penalises a shrinking one."
            chart={
              <ChartBody height={280}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={series} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    <XAxis
                      dataKey="period"
                      tickFormatter={(value: string) => formatQuarter(value)}
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                      minTickGap={20}
                    />
                    <YAxis
                      tick={AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      width={52}
                      tickFormatter={(value: number) => `$${Math.round(value / 1000)}k`}
                    />
                    <Tooltip
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={formatQuarter(String(label))}
                            rows={payload
                              .filter((item) => item.value != null)
                              .map((item) => ({
                                label:
                                  DEPARTMENTS[Number(String(item.dataKey).slice(1))] ??
                                  String(item.dataKey),
                                value: formatCurrency(Number(item.value)),
                                color: String(item.color),
                              }))}
                          />
                        ) : null
                      }
                    />
                    {departments.map((id) => (
                      <Line
                        key={id}
                        type="monotone"
                        dataKey={`d${id}`}
                        stroke={DEPT_COLOR[id] ?? 'var(--color-series-1)'}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--color-surface)' }}
                        connectNulls
                        isAnimationActive={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </ChartBody>
            }
            table={
              <DataTable
                rows={[...rows].sort((a, b) => b.period.localeCompare(a.period))}
                rowKey={(row) => `${row.period}-${row.department_id}`}
                columns={[
                  { key: 'q', header: 'Quarter', render: (row) => formatQuarter(row.period) },
                  {
                    key: 'dept',
                    header: 'Department',
                    render: (row) => DEPARTMENTS[row.department_id ?? 0] ?? '—',
                  },
                  {
                    key: 'rev',
                    header: 'Revenue',
                    align: 'right',
                    render: (row) => formatCurrency(row.revenue_amount),
                  },
                  {
                    key: 'fte',
                    header: 'Avg FTE',
                    align: 'right',
                    render: (row) => formatDecimal(row.avg_fte),
                  },
                  {
                    key: 'per',
                    header: 'Per FTE',
                    align: 'right',
                    render: (row) => formatCurrency(row.revenue_per_fte),
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

// --- Utilization heatmap ----------------------------------------------------

/** A full year. 26 weeks left half the card empty, and a year is the unit anyone reading
 *  a utilization chart already thinks in. */
const WEEKS_SHOWN = 52

function utilizationStep(rate: number | null): { bg: string; fg: string } {
  if (rate == null) return { bg: 'var(--color-ink-50)', fg: 'var(--color-ink-500)' }
  if (rate >= 0.95) return { bg: 'var(--color-seq-700)', fg: '#ffffff' }
  if (rate >= 0.9) return { bg: 'var(--color-seq-550)', fg: '#ffffff' }
  if (rate >= 0.8) return { bg: 'var(--color-seq-350)', fg: 'var(--color-ink-900)' }
  if (rate >= 0.7) return { bg: 'var(--color-seq-250)', fg: 'var(--color-ink-900)' }
  return { bg: 'var(--color-seq-100)', fg: 'var(--color-ink-900)' }
}

const UTILIZATION_LEGEND = [
  { label: '<70%', bg: 'var(--color-seq-100)' },
  { label: '70–80%', bg: 'var(--color-seq-250)' },
  { label: '80–90%', bg: 'var(--color-seq-350)' },
  { label: '90–95%', bg: 'var(--color-seq-550)' },
  { label: '95%+', bg: 'var(--color-seq-700)' },
]

function UtilizationHeatmap() {
  const query = useMetric<UtilizationWeek[]>('/api/productivity/utilization/by-week')

  return (
    <Async
      query={query}
      skeleton={<Card><ChartSkeleton /></Card>}
      empty={{
        title: 'No timesheets in this slice',
        hint: 'Utilization applies only to billable departments — Engineering, Support and Operations.',
      }}
    >
      {(envelope) => {
        const rows = envelope.data
        const weeks = [...new Set(rows.map((row) => row.period))].sort().slice(-WEEKS_SHOWN)
        const weekSet = new Set(weeks)
        const teams = [...new Set(rows.map((row) => row.department_id ?? 0))].sort()

        const lookup = new Map<string, number | null>()
        for (const row of rows) {
          if (weekSet.has(row.period)) {
            lookup.set(`${row.department_id}-${row.period}`, row.utilization)
          }
        }

        const busiest = teams
          .map((id) => {
            const values = weeks
              .map((week) => lookup.get(`${id}-${week}`))
              .filter((value): value is number => value != null)
            const mean = values.length
              ? values.reduce((sum, value) => sum + value, 0) / values.length
              : null
            return { id, mean }
          })
          .sort((a, b) => (b.mean ?? 0) - (a.mean ?? 0))[0]

        return (
          <ChartCard
            title="Utilization by team by week"
            subtitle={`Billable hours over available hours. Most recent ${weeks.length} weeks.`}
            stat={
              busiest ? (
                <ChartStat
                  value={formatRate(busiest.mean)}
                  label={`busiest team — ${DEPARTMENTS[busiest.id]}`}
                />
              ) : undefined
            }
            legend={
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className="font-sans text-xs text-ink-500">Utilization</span>
                {UTILIZATION_LEGEND.map((step) => (
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
            footnote="The scale uses fixed bands, so a cell's shade means the same thing whichever slice is on screen. Only billable departments file timesheets; the rest have no utilization rather than a utilization of zero."
            chart={
              <div className="overflow-x-auto">
                <table className="border-collapse">
                  <tbody>
                    {teams.map((id) => (
                      <tr key={id}>
                        <th
                          scope="row"
                          className="sticky left-0 z-10 bg-white pr-3 text-right font-sans text-xs font-medium whitespace-nowrap text-ink-700"
                        >
                          {DEPARTMENTS[id] ?? `Dept ${id}`}
                        </th>
                        {weeks.map((week) => {
                          const value = lookup.get(`${id}-${week}`) ?? null
                          const step = utilizationStep(value)
                          return (
                            <td key={week} className="p-[1px]">
                              {/* The hairline ring is load-bearing. The lightest band and
                                  the no-data fill are both near-white, so without a
                                  boundary those cells read as holes in the grid rather
                                  than as low utilization. */}
                              <span
                                title={`${DEPARTMENTS[id]} · week of ${week} · ${formatRate(value)}`}
                                className="block h-6 w-4 rounded-[2px] ring-1 ring-inset ring-ink-200/70"
                                style={{ backgroundColor: step.bg }}
                              />
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                    <tr>
                      <td />
                      {weeks.map((week, index) => (
                        // `relative` + an absolutely positioned label is the point. A label
                        // in normal flow is ~30px wide against an 18px cell, and a table
                        // column sizes to its widest member — so every labelled column grew,
                        // and the extra width showed up as a white stripe running down the
                        // whole heatmap once every N columns. Taking the label out of flow
                        // keeps every column exactly one cell wide.
                        <td key={week} className="relative h-4 p-0 align-top">
                          {index % 6 === 0 && (
                            <span
                              className={`absolute top-1 font-sans text-[9px] whitespace-nowrap text-ink-500 ${
                                index === 0 ? 'left-0' : 'left-1/2 -translate-x-1/2'
                              }`}
                            >
                              {week.slice(5, 10)}
                            </span>
                          )}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            }
            table={
              <DataTable
                rows={teams.map((id) => {
                  const values = weeks
                    .map((week) => lookup.get(`${id}-${week}`))
                    .filter((value): value is number => value != null)
                  return {
                    id,
                    weeks: values.length,
                    mean: values.length
                      ? values.reduce((sum, value) => sum + value, 0) / values.length
                      : null,
                    peak: values.length ? Math.max(...values) : null,
                  }
                })}
                rowKey={(row) => String(row.id)}
                columns={[
                  { key: 'team', header: 'Team', render: (row) => DEPARTMENTS[row.id] ?? '—' },
                  {
                    key: 'weeks',
                    header: 'Weeks',
                    align: 'right',
                    render: (row) => formatCount(row.weeks),
                  },
                  {
                    key: 'mean',
                    header: 'Mean utilization',
                    align: 'right',
                    render: (row) => formatRate(row.mean),
                  },
                  {
                    key: 'peak',
                    header: 'Peak week',
                    align: 'right',
                    render: (row) => formatRate(row.peak),
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

// --- Overtime ---------------------------------------------------------------

function OvertimeTrend() {
  const query = useMetric<OvertimeMonth[]>('/api/productivity/overtime/trend')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = envelope.data
        const teams = [...new Set(rows.map((row) => row.department_id ?? 0))].sort()

        const byMonth = new Map<string, Record<string, number | string | null>>()
        for (const row of rows) {
          const entry = byMonth.get(row.period) ?? { period: row.period }
          entry[`d${row.department_id}`] = row.overtime_rate
          byMonth.set(row.period, entry)
        }
        const series = [...byMonth.values()].sort((a, b) =>
          String(a.period).localeCompare(String(b.period)),
        )

        const worst = teams
          .map((id) => {
            const values = rows
              .filter((row) => (row.department_id ?? 0) === id && row.overtime_rate != null)
              .map((row) => row.overtime_rate as number)
            return {
              id,
              mean: values.length
                ? values.reduce((sum, value) => sum + value, 0) / values.length
                : 0,
            }
          })
          .sort((a, b) => b.mean - a.mean)[0]

        return (
          <ChartCard
            title="Overtime rate"
            subtitle="Hours beyond 40 in a week, over total hours logged."
            stat={
              worst ? (
                <ChartStat
                  value={formatRate(worst.mean)}
                  label={`highest — ${DEPARTMENTS[worst.id]}`}
                />
              ) : undefined
            }
            legend={
              <Legend
                items={teams.map((id) => ({
                  label: DEPARTMENTS[id] ?? `Dept ${id}`,
                  color: DEPT_COLOR[id] ?? 'var(--color-series-1)',
                }))}
              />
            }
            footnote="The 40-hour line is applied to each week before anything is summed. Applied to a quarter's total instead, almost every hour would count as overtime."
            chart={
              <ChartBody height={240}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={series} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    <XAxis
                      dataKey="period"
                      tickFormatter={(value: string) => formatMonth(value)}
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                      minTickGap={28}
                    />
                    <YAxis
                      tick={AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      width={44}
                      tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
                    />
                    <Tooltip
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={formatMonth(String(label))}
                            rows={payload
                              .filter((item) => item.value != null)
                              .map((item) => ({
                                label:
                                  DEPARTMENTS[Number(String(item.dataKey).slice(1))] ??
                                  String(item.dataKey),
                                value: formatRate(Number(item.value)),
                                color: String(item.color),
                              }))}
                          />
                        ) : null
                      }
                    />
                    {teams.map((id) => (
                      <Line
                        key={id}
                        type="monotone"
                        dataKey={`d${id}`}
                        stroke={DEPT_COLOR[id] ?? 'var(--color-series-1)'}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--color-surface)' }}
                        connectNulls
                        isAnimationActive={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </ChartBody>
            }
            table={
              <DataTable
                rows={[...rows].sort((a, b) => b.period.localeCompare(a.period)).slice(0, 60)}
                rowKey={(row) => `${row.period}-${row.department_id}`}
                columns={[
                  { key: 'm', header: 'Month', render: (row) => formatMonth(row.period) },
                  {
                    key: 'team',
                    header: 'Team',
                    render: (row) => DEPARTMENTS[row.department_id ?? 0] ?? '—',
                  },
                  {
                    key: 'ot',
                    header: 'Overtime hours',
                    align: 'right',
                    render: (row) => formatDecimal(row.overtime_hours),
                  },
                  {
                    key: 'rate',
                    header: 'Overtime rate',
                    align: 'right',
                    render: (row) => formatRate(row.overtime_rate),
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

// --- Span of control --------------------------------------------------------

/** Keyed by level, not by row position — only L5 and L6 currently hold reports, and a
 *  positional ramp would paint whichever two levels appear the two lightest shades. */
const LEVEL_STEPS: Record<number, string> = {
  1: 'var(--color-seq-100)',
  2: 'var(--color-seq-250)',
  3: 'var(--color-seq-350)',
  4: 'var(--color-seq-450)',
  5: 'var(--color-seq-550)',
  6: 'var(--color-seq-700)',
}

function SpanOfControl() {
  const query = useMetric<SpanByLevel[]>('/api/productivity/span-of-control/by-level')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        // Roll department out: the question is how wide a level's teams are.
        const byLevel = new Map<number, { managers: number; reports: number }>()
        for (const row of envelope.data) {
          const level = row.job_level_id ?? 0
          const entry = byLevel.get(level) ?? { managers: 0, reports: 0 }
          entry.managers += row.managers
          entry.reports += row.direct_reports
          byLevel.set(level, entry)
        }

        // The view is grained by month, so these sums are manager-months and
        // report-months. Their ratio is the period-weighted average span, which is the
        // number that means something; the counts themselves are labelled as months.
        const rows = [...byLevel.entries()]
          .map(([level, value]) => ({
            level,
            label: LEVELS[level] ?? `L${level}`,
            managerMonths: value.managers,
            reportMonths: value.reports,
            span: value.managers ? value.reports / value.managers : null,
          }))
          .sort((a, b) => a.level - b.level)

        const overall = rows.reduce(
          (acc, row) => ({ m: acc.m + row.managerMonths, r: acc.r + row.reportMonths }),
          { m: 0, r: 0 },
        )

        return (
          <ChartCard
            title="Span of control"
            subtitle="Average direct reports per manager, by the manager's own level."
            stat={
              <ChartStat
                value={formatDecimal(overall.m ? overall.r / overall.m : null)}
                label="company average"
              />
            }
            footnote="Only people who actually have reports are counted — treating every employee as a manager of zero would pull the average below one and describe nobody. Counts are manager-months rather than managers, because a manager present for the whole period should weigh more than one who arrived last month; the ratio of the two is the average span."
            chart={
              <ChartBody height={240}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rows} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    <XAxis
                      dataKey="label"
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                    />
                    <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={36} />
                    <Tooltip
                      cursor={{ fill: 'var(--color-ink-100)' }}
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={String(label)}
                            rows={[
                              {
                                label: 'Average span',
                                value: formatDecimal(payload[0]?.payload.span),
                              },
                              {
                                label: 'Manager-months',
                                value: formatCount(payload[0]?.payload.managerMonths),
                              },
                              {
                                label: 'Report-months',
                                value: formatCount(payload[0]?.payload.reportMonths),
                              },
                            ]}
                          />
                        ) : null
                      }
                    />
                    {/* Only two levels hold reports. Without a cap, Recharts divides the
                        full width between them and draws two 300px slabs. */}
                    <Bar
                      dataKey="span"
                      radius={[4, 4, 0, 0]}
                      maxBarSize={72}
                      isAnimationActive={false}
                    >
                      {rows.map((row) => (
                        <Cell
                          key={row.level}
                          fill={LEVEL_STEPS[row.level] ?? 'var(--color-seq-450)'}
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
                rowKey={(row) => String(row.level)}
                columns={[
                  { key: 'lvl', header: 'Level', render: (row) => row.label },
                  {
                    key: 'm',
                    header: 'Manager-months',
                    align: 'right',
                    render: (row) => formatCount(row.managerMonths),
                  },
                  {
                    key: 'r',
                    header: 'Report-months',
                    align: 'right',
                    render: (row) => formatCount(row.reportMonths),
                  },
                  {
                    key: 's',
                    header: 'Average span',
                    align: 'right',
                    render: (row) => formatDecimal(row.span),
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

// --- Goals and training -----------------------------------------------------

function GoalsAndTraining() {
  const goals = useMetric<GoalAttainment>('/api/productivity/goal-attainment')
  const training = useMetric<Training>('/api/productivity/training')

  return (
    <Card title="Goals and training" subtitle="Attainment against target, and learning hours per head.">
      <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        <ChartStat
          value={formatDecimal(goals.data?.data.attainment ?? null)}
          label={`goal attainment, capped at ${formatDecimal(goals.data?.data.cap ?? 1.5)}`}
        />
        <ChartStat
          value={formatCount(goals.data?.data.completed_goals ?? null)}
          label={`completed of ${formatCount(goals.data?.data.goals ?? null)} goals`}
        />
        <ChartStat
          value={formatDecimal(training.data?.data.hours_per_head ?? null)}
          label="training hours per head"
        />
        <ChartStat
          value={formatRate(training.data?.data.completion_rate ?? null)}
          label="course completion"
        />
      </div>

      <p className="mt-4 font-sans text-[11px] leading-relaxed text-ink-500">
        Each goal is capped at 1.5 before averaging, not after — one goal delivering 400% would
        otherwise drag a whole team's average up before the cap ever bit. Training hours divide by
        average headcount across the period, so a team present for half of it counts as half.
      </p>
    </Card>
  )
}
