/** All number formatting lives here.
 *
 * CLAUDE.md: "Money and rates: return raw numbers from the API, format in the
 * frontend." The API therefore sends `0.2079`, never `"20.8%"`, and every rendering
 * decision — precision, currency symbol, thousands separator — is made once, here.
 *
 * Every function tolerates `null`, because the API returns null wherever a metric is
 * genuinely undefined (zero voluntary exits, no timesheets filed). A null must render
 * as an em dash, never as `0` — a fabricated zero is indistinguishable from a real
 * measurement once it is on a chart.
 */

export const EMPTY = '—'

const nf = (options: Intl.NumberFormatOptions) => new Intl.NumberFormat('en-US', options)

const integer = nf({ maximumFractionDigits: 0 })
const oneDecimal = nf({ minimumFractionDigits: 1, maximumFractionDigits: 1 })
const percent1 = nf({ style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 })
const percent0 = nf({ style: 'percent', maximumFractionDigits: 0 })
const currency0 = nf({
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

export function formatCount(value: number | null | undefined): string {
  return value == null ? EMPTY : integer.format(value)
}

export function formatRate(value: number | null | undefined): string {
  return value == null ? EMPTY : percent1.format(value)
}

export function formatRateCoarse(value: number | null | undefined): string {
  return value == null ? EMPTY : percent0.format(value)
}

export function formatDays(value: number | null | undefined): string {
  return value == null ? EMPTY : `${oneDecimal.format(value)}d`
}

export function formatCurrency(value: number | null | undefined): string {
  return value == null ? EMPTY : currency0.format(value)
}

/** eNPS is a signed score on -100..+100, not a percentage. The sign is the point. */
export function formatScore(value: number | null | undefined): string {
  if (value == null) return EMPTY
  const rounded = Math.round(value)
  return rounded > 0 ? `+${rounded}` : String(rounded)
}

export function formatDecimal(value: number | null | undefined): string {
  return value == null ? EMPTY : oneDecimal.format(value)
}

/** The `unit` hint the overview endpoint sends with each KPI. */
export type MetricUnit = 'people' | 'rate' | 'days' | 'currency' | 'score'

export function formatByUnit(value: number | null | undefined, unit: MetricUnit): string {
  switch (unit) {
    case 'rate':
      return formatRate(value)
    case 'days':
      return formatDays(value)
    case 'currency':
      return formatCurrency(value)
    case 'score':
      return formatScore(value)
    default:
      return formatCount(value)
  }
}

/** A signed percentage change, for period-over-period deltas. */
export function formatDelta(value: number | null | undefined): string {
  if (value == null) return EMPTY
  const formatted = percent1.format(Math.abs(value))
  if (Math.abs(value) < 0.0005) return `±${formatted}`
  return value > 0 ? `+${formatted}` : `−${formatted}`
}

/** `2025-07-01` → `Jul 2025`. Charts read left-to-right chronologically, so axis
 *  labels stay short enough not to rotate. */
export function formatMonth(iso: string | null | undefined): string {
  if (!iso) return EMPTY
  const [year, month] = iso.split('-')
  const names = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ]
  const index = Number(month) - 1
  return `${names[index] ?? month} ${year}`
}

export function formatQuarter(iso: string | null | undefined): string {
  if (!iso) return EMPTY
  const [year, month] = iso.split('-')
  return `Q${Math.floor((Number(month) - 1) / 3) + 1} ${year?.slice(2)}`
}

/**
 * Which direction is good, given the metric's own polarity.
 *
 * `higher_is_better` is three-valued on purpose. Headcount rising is neither good nor
 * bad without context, and painting it green would assert something the data does not
 * say — so a null polarity gets neutral ink, not an arrow.
 */
export function deltaTone(
  delta: number | null | undefined,
  higherIsBetter: boolean | null,
): 'good' | 'bad' | 'neutral' {
  if (delta == null || higherIsBetter == null || Math.abs(delta) < 0.0005) return 'neutral'
  const rising = delta > 0
  return rising === higherIsBetter ? 'good' : 'bad'
}
