import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
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
} from '@/components/charts/chrome'
import { GRID } from '@/components/charts/chrome'
import { Async, ChartSkeleton } from '@/components/States'
import { useMetric } from '@/hooks/useMetric'
import type {
  CommentTheme,
  DriverDepartmentPoint,
  Enps,
  EnpsPoint,
  Participation,
  QuartileAttrition,
} from '@/lib/api'
import { formatCount, formatDecimal, formatQuarter, formatRate, formatScore } from '@/lib/format'

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

const DRIVERS = ['manager', 'growth', 'recognition', 'workload', 'belonging'] as const
type DriverKey = (typeof DRIVERS)[number]

/** Keyed to the driver union rather than to `string`, so indexing it returns `string`
 *  and not `string | undefined` — the labels are exhaustive by construction. */
const DRIVER_LABELS: Record<DriverKey, string> = {
  manager: 'Manager',
  growth: 'Growth',
  recognition: 'Recognition',
  workload: 'Workload',
  belonging: 'Belonging',
}

/** The response carries driver keys through an index signature, so reads come back
 *  possibly-undefined. Normalising to `null` here keeps the "undefined is not a
 *  measurement" distinction the formatters rely on. */
function driverScore(row: DriverDepartmentPoint, driver: DriverKey): number | null {
  return row[driver] ?? null
}

export default function Engagement() {
  return (
    <>
      <PageHeader
        title="Engagement"
        description="How people feel, which drivers move, and whether disengagement actually precedes leaving."
        meta="Driver scores are collected on a 1–5 scale and reported 0–100. eNPS is a signed score from −100 to +100, not a percentage."
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <EnpsCard />
        <Participation />
        <div className="xl:col-span-2">
          <DriverHeatmap />
        </div>
        <QuartileAttritionCard />
        <CommentThemes />
      </div>
    </>
  )
}

// --- eNPS -------------------------------------------------------------------

/** A meter, not a dial.
 *
 * eNPS runs −100 to +100, so "where on the range are we" is a real question and a track
 * with a marker answers it honestly. A semicircular gauge would spend a lot of pixels
 * on the same one number and imply a speedometer's arbitrary red zone.
 */
function EnpsMeter({ score }: { score: number | null }) {
  if (score == null) return null
  const position = ((score + 100) / 200) * 100

  return (
    <div className="mt-3">
      <div className="relative h-1.5 w-full rounded-full bg-ink-200">
        <span
          aria-hidden="true"
          className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-seq-450"
          style={{ left: `${position}%` }}
        />
        {/* Zero is the meaningful landmark on this scale — more detractors than
            promoters, or fewer. */}
        <span
          aria-hidden="true"
          className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-ink-300"
          style={{ left: '50%' }}
        />
      </div>
      <div className="mt-1 flex justify-between font-sans text-[11px] text-ink-500">
        <span>−100</span>
        <span>0</span>
        <span>+100</span>
      </div>
    </div>
  )
}

function EnpsCard() {
  const current = useMetric<Enps>('/api/engagement/enps')
  const trend = useMetric<EnpsPoint[]>('/api/engagement/enps/trend')

  return (
    <Async query={trend} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = envelope.data.filter((row) => row.enps != null)
        const latest = rows[rows.length - 1]
        const summary = current.data?.data

        return (
          <ChartCard
            title="eNPS"
            subtitle="Promoters minus detractors, by survey quarter."
            stat={
              <div>
                <div className="flex gap-8">
                  <ChartStat
                    value={formatScore(latest?.enps ?? null)}
                    label={latest ? `latest — ${formatQuarter(latest.period)}` : 'no survey'}
                  />
                  {summary && (
                    <ChartStat
                      value={formatCount(summary.responses)}
                      label="responses in slice"
                    />
                  )}
                </div>
                <EnpsMeter score={latest?.enps ?? null} />
              </div>
            }
            footnote="A negative eNPS is a real reading, not an error — it means detractors outnumber promoters. Passives count toward the denominator but neither side of the numerator."
            chart={
              <ChartBody height={220}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={rows} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    <ReferenceLine y={0} stroke="var(--color-axis)" strokeWidth={1} />
                    <XAxis
                      dataKey="period"
                      tickFormatter={formatQuarter}
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                    />
                    <YAxis
                      tick={AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      width={44}
                      domain={[-60, 20]}
                    />
                    <Tooltip
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={formatQuarter(String(label))}
                            rows={[
                              { label: 'eNPS', value: formatScore(payload[0]?.payload.enps) },
                              {
                                label: 'Promoters',
                                value: formatCount(payload[0]?.payload.promoters),
                              },
                              {
                                label: 'Detractors',
                                value: formatCount(payload[0]?.payload.detractors),
                              },
                            ]}
                            note={`${formatCount(payload[0]?.payload.responses)} responses`}
                          />
                        ) : null
                      }
                    />
                    <Line
                      type="monotone"
                      dataKey="enps"
                      stroke="var(--color-series-1)"
                      strokeWidth={2}
                      dot={{ r: 3, strokeWidth: 2, stroke: 'var(--color-surface)' }}
                      activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--color-surface)' }}
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
                  { key: 'q', header: 'Quarter', render: (row) => formatQuarter(row.period) },
                  {
                    key: 'enps',
                    header: 'eNPS',
                    align: 'right',
                    render: (row) => formatScore(row.enps),
                  },
                  {
                    key: 'p',
                    header: 'Promoters',
                    align: 'right',
                    render: (row) => formatCount(row.promoters),
                  },
                  {
                    key: 'd',
                    header: 'Detractors',
                    align: 'right',
                    render: (row) => formatCount(row.detractors),
                  },
                  {
                    key: 'n',
                    header: 'Responses',
                    align: 'right',
                    render: (row) => formatCount(row.responses),
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

// --- Participation ----------------------------------------------------------

function Participation() {
  const query = useMetric<Participation[]>('/api/engagement/participation')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = envelope.data
        const responses = rows.reduce((sum, row) => sum + row.responses, 0)
        const eligible = rows.reduce((sum, row) => sum + row.eligible_employees, 0)

        return (
          <ChartCard
            title="Survey participation"
            subtitle="Responses against employees eligible when the survey closed."
            stat={
              <ChartStat
                value={formatRate(eligible ? responses / eligible : null)}
                label={`${formatCount(responses)} of ${formatCount(eligible)} eligible`}
              />
            }
            footnote="The denominator moves with the organization — someone who had already left was never eligible, and counting them would understate participation for exactly the teams losing people."
            chart={
              <ChartBody height={220}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rows} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    <XAxis
                      dataKey="period"
                      tickFormatter={formatQuarter}
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
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
                      cursor={{ fill: 'var(--color-ink-100)' }}
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={formatQuarter(String(label))}
                            rows={[
                              {
                                label: 'Participation',
                                value: formatRate(payload[0]?.payload.participation_rate),
                              },
                              {
                                label: 'Responses',
                                value: formatCount(payload[0]?.payload.responses),
                              },
                              {
                                label: 'Eligible',
                                value: formatCount(payload[0]?.payload.eligible_employees),
                              },
                            ]}
                          />
                        ) : null
                      }
                    />
                    <Bar
                      dataKey="participation_rate"
                      fill="var(--color-series-1)"
                      radius={[4, 4, 0, 0]}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </ChartBody>
            }
            table={
              <DataTable
                rows={rows}
                rowKey={(row) => String(row.survey_id)}
                columns={[
                  { key: 'q', header: 'Survey', render: (row) => formatQuarter(row.period) },
                  {
                    key: 'r',
                    header: 'Responses',
                    align: 'right',
                    render: (row) => formatCount(row.responses),
                  },
                  {
                    key: 'e',
                    header: 'Eligible',
                    align: 'right',
                    render: (row) => formatCount(row.eligible_employees),
                  },
                  {
                    key: 'rate',
                    header: 'Participation',
                    align: 'right',
                    render: (row) => formatRate(row.participation_rate),
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

// --- Driver heatmap ---------------------------------------------------------

/** Fixed bands, so a department's shade means the same thing in every slice. */
function driverStep(score: number | null): { bg: string; fg: string } {
  if (score == null) return { bg: 'transparent', fg: 'var(--color-ink-500)' }
  if (score >= 70) return { bg: 'var(--color-seq-100)', fg: 'var(--color-ink-900)' }
  if (score >= 60) return { bg: 'var(--color-seq-250)', fg: 'var(--color-ink-900)' }
  if (score >= 50) return { bg: 'var(--color-seq-350)', fg: 'var(--color-ink-900)' }
  if (score >= 40) return { bg: 'var(--color-seq-550)', fg: '#ffffff' }
  return { bg: 'var(--color-seq-700)', fg: '#ffffff' }
}

const DRIVER_LEGEND = [
  { label: '<40', bg: 'var(--color-seq-700)' },
  { label: '40–50', bg: 'var(--color-seq-550)' },
  { label: '50–60', bg: 'var(--color-seq-350)' },
  { label: '60–70', bg: 'var(--color-seq-250)' },
  { label: '70+', bg: 'var(--color-seq-100)' },
]

function DriverHeatmap() {
  const query = useMetric<DriverDepartmentPoint[]>('/api/engagement/drivers/by-department')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = [...envelope.data].sort(
          (a, b) => (a.engagement_index ?? 0) - (b.engagement_index ?? 0),
        )

        // The lowest single driver cell anywhere — the thing worth pointing at.
        let worst = { dept: '', driver: '', score: 101 }
        for (const row of rows) {
          for (const driver of DRIVERS) {
            const score = driverScore(row, driver)
            if (score != null && score < worst.score) {
              worst = {
                dept: DEPARTMENTS[row.department_id ?? 0] ?? '—',
                driver: DRIVER_LABELS[driver],
                score,
              }
            }
          }
        }

        return (
          <ChartCard
            title="Engagement drivers by department"
            subtitle="Mean score per driver, 0–100. Sorted by overall engagement index."
            stat={
              worst.score <= 100 ? (
                <ChartStat
                  value={formatDecimal(worst.score)}
                  label={`lowest driver — ${worst.driver} in ${worst.dept}`}
                />
              ) : undefined
            }
            legend={
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className="font-sans text-xs text-ink-500">Driver score</span>
                {DRIVER_LEGEND.map((step) => (
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
            footnote="A grid rather than a radar. Eight overlapping polygons are unreadable, and eight categorical hues cannot stay distinguishable under colour-vision deficiency — a heatmap answers the same question with one hue and a scale."
            chart={
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr>
                      <th className="px-2 py-2 text-left font-sans text-xs font-medium text-ink-500">
                        Department
                      </th>
                      {DRIVERS.map((driver) => (
                        <th
                          key={driver}
                          className="px-2 py-2 text-center font-sans text-xs font-medium text-ink-500"
                        >
                          {DRIVER_LABELS[driver]}
                        </th>
                      ))}
                      <th className="px-2 py-2 text-right font-sans text-xs font-medium text-ink-500">
                        Index
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.department_id}>
                        <td className="px-2 py-1 font-sans text-sm text-ink-900">
                          {DEPARTMENTS[row.department_id ?? 0] ?? '—'}
                        </td>
                        {DRIVERS.map((driver) => {
                          const score = driverScore(row, driver)
                          const step = driverStep(score)
                          return (
                            <td key={driver} className="px-1 py-1">
                              <span
                                className="tnum block rounded px-2 py-1.5 text-center text-sm font-medium"
                                style={{ backgroundColor: step.bg, color: step.fg }}
                              >
                                {formatDecimal(score)}
                              </span>
                            </td>
                          )
                        })}
                        <td className="tnum px-2 py-1 text-right font-sans text-sm text-ink-900">
                          {formatDecimal(row.engagement_index)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            }
            table={
              <DataTable
                rows={rows}
                rowKey={(row) => `${row.department_id}-t`}
                columns={[
                  {
                    key: 'dept',
                    header: 'Department',
                    render: (row) => DEPARTMENTS[row.department_id ?? 0] ?? '—',
                  },
                  ...DRIVERS.map((driver) => ({
                    key: driver as string,
                    header: DRIVER_LABELS[driver],
                    align: 'right' as const,
                    render: (row: DriverDepartmentPoint) =>
                      formatDecimal(driverScore(row, driver)),
                  })),
                  {
                    key: 'index',
                    header: 'Index',
                    align: 'right' as const,
                    render: (row: DriverDepartmentPoint) => formatDecimal(row.engagement_index),
                  },
                  {
                    key: 'n',
                    header: 'Responses',
                    align: 'right' as const,
                    render: (row: DriverDepartmentPoint) => formatCount(row.responses),
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

// --- Engagement to attrition ------------------------------------------------

/** Quartiles are ordered, so the ordinal ramp is the right encoding. Bar height carries
 *  attrition and hue carries the quartile — two different variables, not the same one
 *  encoded twice. */
const QUARTILE_STEPS = [
  'var(--color-seq-700)',
  'var(--color-seq-550)',
  'var(--color-seq-350)',
  'var(--color-seq-250)',
]

function QuartileAttritionCard() {
  const query = useMetric<QuartileAttrition[]>('/api/engagement/attrition-link')

  return (
    <Async query={query} skeleton={<Card><ChartSkeleton /></Card>}>
      {(envelope) => {
        const rows = [...envelope.data].sort((a, b) => a.quartile - b.quartile)
        const bottom = rows.find((row) => row.quartile === 1)
        const top = rows.find((row) => row.quartile === 4)
        const ratio =
          bottom?.annualized_rate && top?.annualized_rate
            ? bottom.annualized_rate / top.annualized_rate
            : null

        return (
          <ChartCard
            title="Engagement against later attrition"
            subtitle="Attrition in the quarter after each survey, by the respondent's engagement quartile."
            stat={
              <ChartStat
                value={ratio ? `${formatDecimal(ratio)}×` : '—'}
                label="bottom quartile leaves this much faster than the top"
              />
            }
            footnote="Attrition is measured in the quarter AFTER the survey closed, not the one containing it. Counting the same period would be circular — people already on their way out answer badly on the way."
            chart={
              <ChartBody height={220}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rows} margin={CHART_MARGIN}>
                    <CartesianGrid {...GRID} />
                    <XAxis
                      dataKey="quartile"
                      tickFormatter={(value: number) =>
                        value === 1 ? 'Q1 least engaged' : value === 4 ? 'Q4 most' : `Q${value}`
                      }
                      tick={AXIS_TICK}
                      axisLine={AXIS_LINE}
                      tickLine={false}
                    />
                    <YAxis
                      tick={AXIS_TICK}
                      axisLine={false}
                      tickLine={false}
                      width={44}
                      tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
                    />
                    <Tooltip
                      cursor={{ fill: 'var(--color-ink-100)' }}
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <ChartTooltip
                            title={`Quartile ${label}`}
                            rows={[
                              {
                                label: 'Annualized attrition',
                                value: formatRate(payload[0]?.payload.annualized_rate),
                              },
                              {
                                label: 'Exits',
                                value: formatCount(payload[0]?.payload.terminations),
                              },
                            ]}
                          />
                        ) : null
                      }
                    />
                    <Bar dataKey="annualized_rate" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                      {rows.map((row, index) => (
                        <Cell key={row.quartile} fill={QUARTILE_STEPS[index] ?? QUARTILE_STEPS[3]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartBody>
            }
            table={
              <DataTable
                rows={rows}
                rowKey={(row) => String(row.quartile)}
                columns={[
                  {
                    key: 'q',
                    header: 'Quartile',
                    render: (row) =>
                      row.quartile === 1
                        ? 'Q1 (least engaged)'
                        : row.quartile === 4
                          ? 'Q4 (most engaged)'
                          : `Q${row.quartile}`,
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

// --- Comment themes ---------------------------------------------------------

/** Enough to show the shape of what people are saying without turning the card into a
 *  transcript. The rest are one endpoint call away. */
const THEMES_SHOWN = 10

/** Sentiment is a status, not a series — so it ships with a label, never colour alone. */
const SENTIMENT_STYLE: Record<string, string> = {
  negative: 'bg-risk-soft text-risk',
  mixed: 'bg-ink-100 text-ink-700',
  neutral: 'bg-ink-100 text-ink-700',
  positive: 'bg-ink-100 text-good-text',
}

function CommentThemes() {
  const query = useMetric<CommentTheme[]>('/api/engagement/themes')

  return (
    <Async
      query={query}
      skeleton={<Card><ChartSkeleton /></Card>}
      empty={{
        title: 'No themes extracted yet',
        hint: 'Open-text comments are classified by Claude in phase 6 and cached, so the dashboard never waits on a live call. Until then this panel is intentionally empty rather than erroring.',
      }}
    >
      {(envelope) => (
        <Card
          title="Comment themes"
          subtitle="Extracted from open-text survey responses, with sentiment and volume."
        >
          {/* Capped at the top ten. The endpoint returns every (theme, sentiment) pair,
              which is twenty rows and twice the height of the card beside it — a column of
              dead space next to a chart is a worse read than a shorter list. */}
          <ul className="space-y-2">
            {envelope.data.slice(0, THEMES_SHOWN).map((theme) => (
              <li
                key={`${theme.theme}-${theme.sentiment}`}
                className="flex items-center justify-between gap-4 rounded border border-ink-200 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate font-sans text-sm font-medium text-ink-900">
                    {theme.theme}
                  </p>
                  <p className="font-sans text-xs text-ink-500">
                    confidence {formatRate(theme.mean_confidence)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span
                    className={`rounded px-2 py-0.5 font-sans text-xs capitalize ${
                      SENTIMENT_STYLE[theme.sentiment] ?? 'bg-ink-100 text-ink-700'
                    }`}
                  >
                    {theme.sentiment}
                  </span>
                  <span className="tnum font-sans text-sm font-medium text-ink-900">
                    {formatCount(theme.volume)}
                  </span>
                </div>
              </li>
            ))}
          </ul>

          <p className="mt-3 font-sans text-[11px] leading-relaxed text-ink-500">
            {envelope.data.length > THEMES_SHOWN
              ? `Top ${THEMES_SHOWN} of ${formatCount(envelope.data.length)} theme-and-sentiment pairs. `
              : ''}
            Themes are assigned once per distinct comment and then counted across every
            response carrying it, so volume is the number of people who said it rather than
            the number of phrasings.
          </p>
        </Card>
      )}
    </Async>
  )
}
