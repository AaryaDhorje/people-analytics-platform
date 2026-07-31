import type { ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
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
} from '@/components/charts/chrome'
import { Async, ChartSkeleton, ErrorState } from '@/components/States'
import { useMetric } from '@/hooks/useMetric'
import type {
  CohortRetention,
  FunnelStage,
  RequisitionAging,
  SourceCost,
  TimeToFill,
  TimeToFillPoint,
} from '@/lib/api'
import {
  formatCount,
  formatCurrency,
  formatDays,
  formatMonth,
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

const SOURCES: Record<number, string> = {
  1: 'Referral',
  2: 'Agency',
  3: 'Job board',
  4: 'Inbound',
  5: 'Campus',
  6: 'Internal',
}

const STAGE_LABELS: Record<string, string> = {
  applied: 'Applied',
  screen: 'Screen',
  interview: 'Interview',
  offer: 'Offer',
  hired: 'Hired',
}

export default function Acquisition() {
  return (
    <>
      <PageHeader
        title="Talent Acquisition"
        description="Where candidates get stuck, how long roles stay open, and which channels produce hires that stay."
        meta="Time to fill runs from the requisition opening; time to hire runs from the candidate applying. They answer different questions."
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Funnel />
        <TimeToFillTrend />
        <div className="xl:col-span-2">
          <SourceEffectiveness />
        </div>
        <div className="xl:col-span-2">
          <RequisitionAgingTable />
        </div>
      </div>
    </>
  )
}

// --- Funnel -----------------------------------------------------------------

/** Ordered stages, so the ordinal ramp is correct — validated light-to-dark with the
 *  light end clearing 2:1 against the white card. */
const STAGE_STEPS = [
  'var(--color-seq-250)',
  'var(--color-seq-350)',
  'var(--color-seq-450)',
  'var(--color-seq-550)',
  'var(--color-seq-700)',
]

function Funnel() {
  const query = useMetric<FunnelStage[]>('/api/acquisition/funnel')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = envelope.data
        const worst = rows
          .filter((row) => row.mean_dwell_days != null)
          .sort((a, b) => (b.mean_dwell_days ?? 0) - (a.mean_dwell_days ?? 0))[0]

        return (
          <ChartCard
            title="Hiring funnel"
            subtitle="Candidates reaching each stage, with average time spent in it."
            stat={
              worst ? (
                <ChartStat
                  value={formatDays(worst.mean_dwell_days)}
                  label={`slowest stage — ${STAGE_LABELS[worst.stage] ?? worst.stage}`}
                />
              ) : undefined
            }
            footnote="Counts are distinct candidates, not stage events, so a candidate who re-entered a stage cannot make the funnel widen as it descends. Candidates still sitting in a stage are excluded from its dwell average — counting them as zero days would flatter exactly the stage that is slowest."
            chart={
              <ChartBody height={260}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rows} layout="vertical" margin={{ ...CHART_MARGIN, left: 24 }}>
                    <CartesianGrid {...GRID} horizontal={false} vertical />
                    <XAxis
                      type="number"
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="stage"
                      tickFormatter={(stage: string) => STAGE_LABELS[stage] ?? stage}
                      tick={AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      width={72}
                    />
                    <Tooltip
                      cursor={{ fill: 'var(--color-ink-100)' }}
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null
                        const row = payload[0]?.payload as FunnelStage
                        return (
                          <ChartTooltip
                            title={STAGE_LABELS[row.stage] ?? row.stage}
                            rows={[
                              { label: 'Candidates', value: formatCount(row.applications) },
                              {
                                label: 'From previous',
                                value: formatRate(row.conversion_from_previous),
                              },
                              { label: 'Avg dwell', value: formatDays(row.mean_dwell_days) },
                            ]}
                            note={
                              row.still_in_stage
                                ? `${formatCount(row.still_in_stage)} still in this stage`
                                : undefined
                            }
                          />
                        )
                      }}
                    />
                    <Bar dataKey="applications" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                      {rows.map((row, index) => (
                        <Cell key={row.stage} fill={STAGE_STEPS[index] ?? STAGE_STEPS[4]} />
                      ))}
                      {/* Direct labels rather than a number on every mark elsewhere — the
                          count is the point of a funnel. */}
                      <LabelList
                        dataKey="applications"
                        position="right"
                        formatter={(value: ReactNode) => formatCount(Number(value))}
                        style={{ fill: 'var(--color-ink-700)', fontSize: 11 }}
                      />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartBody>
            }
            table={
              <DataTable
                rows={rows}
                rowKey={(row) => row.stage}
                columns={[
                  {
                    key: 'stage',
                    header: 'Stage',
                    render: (row) => STAGE_LABELS[row.stage] ?? row.stage,
                  },
                  {
                    key: 'n',
                    header: 'Candidates',
                    align: 'right',
                    render: (row) => formatCount(row.applications),
                  },
                  {
                    key: 'conv',
                    header: 'Conversion',
                    align: 'right',
                    render: (row) => formatRate(row.conversion_from_previous),
                  },
                  {
                    key: 'dwell',
                    header: 'Avg dwell',
                    align: 'right',
                    render: (row) => formatDays(row.mean_dwell_days),
                  },
                  {
                    key: 'open',
                    header: 'Still in stage',
                    align: 'right',
                    render: (row) => formatCount(row.still_in_stage),
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

// --- Time to fill -----------------------------------------------------------

function TimeToFillTrend() {
  const trend = useMetric<TimeToFillPoint[]>('/api/acquisition/time-to-fill/trend')
  const total = useMetric<TimeToFill>('/api/acquisition/time-to-fill')

  return (
    <Async query={trend} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = envelope.data.filter((row) => row.mean_days != null)

        return (
          <ChartCard
            title="Time to fill"
            subtitle="Days from a requisition opening to an offer accepted, by month opened."
            stat={
              <div className="flex gap-8">
                <ChartStat
                  value={formatDays(total.data?.data.mean_days ?? null)}
                  label="average, this slice"
                />
                <ChartStat
                  value={formatCount(total.data?.data.filled_positions ?? null)}
                  label="positions filled"
                />
              </div>
            }
            footnote="Requisitions with nothing accepted contribute to neither side of the average, so an unfilled role cannot pull the mean toward zero. Filter to Sales to see the interview bottleneck."
            chart={
              <ChartBody height={260}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={rows} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    <XAxis
                      dataKey="period"
                      tickFormatter={formatMonth}
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                      minTickGap={28}
                    />
                    <YAxis
                      tick={AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      width={40}
                      tickFormatter={(value: number) => `${value}d`}
                    />
                    <Tooltip
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={formatMonth(String(label))}
                            rows={[
                              {
                                label: 'Time to fill',
                                value: formatDays(payload[0]?.payload.mean_days),
                              },
                              {
                                label: 'Positions filled',
                                value: formatCount(payload[0]?.payload.filled_positions),
                              },
                            ]}
                          />
                        ) : null
                      }
                    />
                    <Line
                      type="monotone"
                      dataKey="mean_days"
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
                rowKey={(row) => row.period}
                columns={[
                  { key: 'm', header: 'Month opened', render: (row) => formatMonth(row.period) },
                  {
                    key: 'filled',
                    header: 'Filled',
                    align: 'right',
                    render: (row) => formatCount(row.filled_positions),
                  },
                  {
                    key: 'days',
                    header: 'Time to fill',
                    align: 'right',
                    render: (row) => formatDays(row.mean_days),
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

// --- Source effectiveness ---------------------------------------------------

interface ChannelPoint {
  source_id: number
  name: string
  cost_per_hire: number
  retention: number
  hires: number
}

function SourceEffectiveness() {
  const cost = useMetric<SourceCost[]>('/api/acquisition/cost-per-hire/by-source')
  const retention = useMetric<CohortRetention[]>('/api/retention/cohort-retention', {
    extraParams: { months: 12 },
  })

  // This card is the one place two endpoints are joined client-side: cost lives on the
  // requisition and 12-month retention lives on the employee, so no single view carries
  // both. The states are handled explicitly rather than through <Async>, which takes one
  // query — passing it whichever of two differently-typed queries failed does not type.
  if (cost.isPending || retention.isPending) {
    return (
      <Card>
        <ChartSkeleton height={320} />
      </Card>
    )
  }
  if (cost.isError) {
    return <ErrorState error={cost.error} onRetry={() => cost.refetch()} />
  }
  if (retention.isError) {
    return <ErrorState error={retention.error} onRetry={() => retention.refetch()} />
  }

  const retentionBySource = new Map(
    (retention.data?.data ?? []).map((row) => [row.source_id, row.retention_rate]),
  )

  const points: ChannelPoint[] = (cost.data?.data ?? [])
    .map((row) => ({
      source_id: row.source_id ?? 0,
      name: SOURCES[row.source_id ?? 0] ?? `Source ${row.source_id}`,
      cost_per_hire: row.cost_per_hire ?? 0,
      retention: retentionBySource.get(row.source_id ?? 0) ?? 0,
      hires: row.hires,
    }))
    .filter((point) => point.cost_per_hire > 0 && point.retention > 0)

  const dearest = [...points].sort((a, b) => b.cost_per_hire - a.cost_per_hire)[0]

  // Agency sits at roughly three times any other channel's cost, which squeezes the
  // remaining five into the left third of the plot — where a label above each bubble
  // overlaps its neighbour. Labels therefore sit beside the bubble, on the side with room.
  // A label runs to the right unless something is in the way: either the plot edge, or a
  // near neighbour up and to the right whose bubble the text would cross.
  const maxCost = Math.max(...points.map((p) => p.cost_per_hire), 1)
  const labelSide = new Map(
    points.map((point) => {
      const crowdedRight = points.some(
        (other) =>
          other.name !== point.name &&
          other.cost_per_hire > point.cost_per_hire &&
          other.cost_per_hire - point.cost_per_hire < 0.2 * maxCost &&
          Math.abs(other.retention - point.retention) < 0.05,
      )
      const nearRightEdge = point.cost_per_hire / maxCost > 0.66
      return [point.name, nearRightEdge || crowdedRight ? 'left' : 'right'] as const
    }),
  )

  return (
    <ChartCard
      title="Source effectiveness"
      // The y-axis carried a rotated 'retention ↑' label that Recharts clipped to
      // "retention 1" inside the 48px axis gutter. The axis is named here instead, where
      // it cannot be cut off.
      subtitle="Cost per hire (across) against 12-month retention (up). Bubble size is hires."
      stat={
        dearest ? (
          <ChartStat
            value={formatCurrency(dearest.cost_per_hire)}
            label={`most expensive channel — ${dearest.name}, retaining ${formatRate(dearest.retention)}`}
          />
        ) : undefined
      }
      footnote="Every point is one colour and carries its own label. Identity here comes from the label, not from hue: a scatter compares all pairs of series at once, and six hues cannot stay distinguishable under colour-vision deficiency at that grain. Upper-left is cheap and sticky; lower-right is expensive and churning."
      chart={
        <ChartBody height={380}>
          <ResponsiveContainer width="100%" height="100%">
            {/* Right margin holds the widest side label; left holds Agency's. */}
            <ScatterChart margin={{ top: 16, right: 72, bottom: 24, left: 8 }}>
              <CartesianGrid {...GRID} vertical />
              <XAxis
                type="number"
                dataKey="cost_per_hire"
                name="Cost per hire"
                tick={AXIS_TICK}
                axisLine={AXIS_LINE}
                tickLine={false}
                tickFormatter={(value: number) => `$${Math.round(value / 1000)}k`}
                label={{
                  value: 'cost per hire →  more expensive',
                  position: 'insideBottom',
                  offset: -12,
                  style: { fill: 'var(--color-ink-500)', fontSize: 11 },
                }}
              />
              <YAxis
                type="number"
                dataKey="retention"
                name="12-month retention"
                tick={AXIS_TICK}
                axisLine={false}
                tickLine={false}
                width={48}
                domain={[0.5, 1]}
                tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
              />
              {/* Bubble area encodes hires. Minimum size keeps a small channel clickable. */}
              <ZAxis type="number" dataKey="hires" range={[120, 900]} name="Hires" />
              <Tooltip
                cursor={{ strokeDasharray: '0', stroke: 'var(--color-ink-300)' }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const point = payload[0]?.payload as ChannelPoint
                  return (
                    <ChartTooltip
                      title={point.name}
                      rows={[
                        { label: 'Cost per hire', value: formatCurrency(point.cost_per_hire) },
                        { label: '12-month retention', value: formatRate(point.retention) },
                        { label: 'Hires', value: formatCount(point.hires) },
                      ]}
                    />
                  )
                }}
              />
              <Scatter
                data={points}
                fill="var(--color-series-1)"
                fillOpacity={0.75}
                stroke="var(--color-surface)"
                strokeWidth={2}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey="name"
                  content={(props) => {
                    const { x, y, value } = props as { x: number; y: number; value: string }
                    const side = labelSide.get(value) ?? 'right'
                    // The bubble radius varies with hires; 18px clears the largest of them.
                    const dx = side === 'right' ? 18 : -18
                    return (
                      <text
                        x={x + dx}
                        y={y}
                        dy={4}
                        textAnchor={side === 'right' ? 'start' : 'end'}
                        style={{ fill: 'var(--color-ink-700)', fontSize: 11 }}
                      >
                        {value}
                      </text>
                    )
                  }}
                />
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </ChartBody>
      }
      table={
        <DataTable
          rows={[...points].sort((a, b) => b.cost_per_hire - a.cost_per_hire)}
          rowKey={(row) => String(row.source_id)}
          columns={[
            { key: 'name', header: 'Channel', render: (row) => row.name },
            {
              key: 'hires',
              header: 'Hires',
              align: 'right',
              render: (row) => formatCount(row.hires),
            },
            {
              key: 'cost',
              header: 'Cost per hire',
              align: 'right',
              render: (row) => formatCurrency(row.cost_per_hire),
            },
            {
              key: 'ret',
              header: '12-month retention',
              align: 'right',
              render: (row) => formatRate(row.retention),
            },
          ]}
        />
      }
    />
  )
}

// --- Requisition aging ------------------------------------------------------

function RequisitionAgingTable() {
  const query = useMetric<RequisitionAging[]>('/api/acquisition/requisition-aging')

  return (
    <Async
      query={query}
      skeleton={<Card><ChartSkeleton /></Card>}
      empty={{ title: 'No open requisitions', hint: 'Nothing is currently open in this slice.' }}
    >
      {(envelope) => {
        const rows = [...envelope.data].sort((a, b) => b.aged_requisitions - a.aged_requisitions)
        const open = rows.reduce((sum, row) => sum + row.open_requisitions, 0)
        const aged = rows.reduce((sum, row) => sum + row.aged_requisitions, 0)
        const threshold = rows[0]?.threshold_days ?? 60

        return (
          <Card
            title="Requisition aging"
            subtitle={`Open requisitions, and how many have been open beyond ${threshold} days.`}
          >
            <div className="mb-4 flex gap-8">
              <ChartStat value={formatCount(open)} label="open now" />
              <ChartStat
                value={formatCount(aged)}
                label={`open past ${threshold} days`}
                tone={aged > 0 ? 'risk' : 'default'}
              />
            </div>

            <DataTable
              rows={rows}
              rowKey={(row) => String(row.department_id)}
              columns={[
                {
                  key: 'dept',
                  header: 'Department',
                  render: (row) => DEPARTMENTS[row.department_id ?? 0] ?? '—',
                },
                {
                  key: 'open',
                  header: 'Open',
                  align: 'right',
                  render: (row) => formatCount(row.open_requisitions),
                },
                {
                  key: 'aged',
                  header: `Past ${threshold}d`,
                  align: 'right',
                  render: (row) =>
                    row.aged_requisitions > 0 ? (
                      // Aged requisitions are a staffing risk, but they are not a person
                      // about to leave — so this gets weight, not the reserved accent.
                      <span className="font-medium text-ink-900">
                        {formatCount(row.aged_requisitions)}
                      </span>
                    ) : (
                      formatCount(0)
                    ),
                },
                {
                  key: 'max',
                  header: 'Oldest',
                  align: 'right',
                  render: (row) =>
                    // A whole number of days. `formatDecimal` rendered "114.0d", which
                    // implies a precision the column does not have.
                    row.max_age_days == null ? '—' : `${formatCount(row.max_age_days)}d`,
                },
              ]}
            />

            <p className="mt-3 font-sans text-[11px] leading-relaxed text-ink-500">
              Age is measured to the last day the warehouse covers, not to today — the data is a
              fixed window, so wall-clock ageing would drift every day the demo is not run.
            </p>
          </Card>
        )
      }}
    </Async>
  )
}
