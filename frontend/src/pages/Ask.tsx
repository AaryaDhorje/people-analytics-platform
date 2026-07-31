import { useState, type FormEvent } from 'react'

import { Card, PageHeader } from '@/components/Card'
import { DataTable } from '@/components/ChartCard'
import { ErrorState, Skeleton } from '@/components/States'
import { useAsk } from '@/hooks/useAsk'
import { useUnfilteredMetric } from '@/hooks/useMetric'
import type { AiStatus, ExampleQuestion } from '@/lib/api'
import { EMPTY } from '@/lib/format'

export default function Ask() {
  const [question, setQuestion] = useState('')
  const ask = useAsk()
  const status = useUnfilteredMetric<AiStatus>('/api/ai/status')
  const examples = useUnfilteredMetric<ExampleQuestion[]>('/api/ai/examples')

  const configured = status.data?.data.available ?? true
  const answer = ask.data?.data

  function submit(event: FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (trimmed) ask.mutate(trimmed)
  }

  function run(preset: string) {
    setQuestion(preset)
    ask.mutate(preset)
  }

  return (
    <>
      <PageHeader
        title="Ask your people data"
        description="A question in English becomes one read-only SQL query against the analytical views. The query is shown with the answer."
        // Says outright that the filter bar above does not apply here. It is global chrome
        // and cannot be hidden per page, so leaving it unexplained would imply a scoping
        // that does not exist — a reader could set a department and believe the answer
        // respected it.
        meta="Answers are generated and the SQL is shown, because a number you cannot check is a number you have to take on faith. Questions run against the whole warehouse — the filter bar above does not scope them; say the slice you want in the question itself."
      />

      <div className="grid grid-cols-1 gap-4">
        {!configured && (
          <Card>
            <p className="font-sans text-sm font-medium text-ink-900">
              Natural-language querying is switched off
            </p>
            <p className="mt-1 max-w-prose font-sans text-sm text-ink-500">
              {status.data?.data.reason ??
                'No AI key is configured. Every other page works without one.'}
            </p>
          </Card>
        )}

        <Card>
          <form onSubmit={submit}>
            <label
              htmlFor="ask-question"
              className="font-sans text-xs font-medium tracking-wide text-ink-500 uppercase"
            >
              Your question
            </label>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <input
                id="ask-question"
                type="text"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Which managers have the worst attrition?"
                maxLength={500}
                disabled={!configured}
                className="min-w-0 flex-1 rounded border border-ink-200 px-3 py-2 font-sans text-sm text-ink-900 placeholder:text-ink-300 focus:border-ink-500 focus:outline-none disabled:bg-ink-50"
              />
              <button
                type="submit"
                disabled={!configured || ask.isPending || !question.trim()}
                className="shrink-0 rounded bg-ink-900 px-4 py-2 font-sans text-sm font-medium text-white transition-colors hover:bg-ink-700 disabled:cursor-not-allowed disabled:bg-ink-200"
              >
                {ask.isPending ? 'Thinking…' : 'Ask'}
              </button>
            </div>
          </form>

          {examples.data && (
            <div className="mt-4">
              <p className="font-sans text-xs text-ink-500">Or start from one of these:</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {examples.data.data.map((example) => (
                  <button
                    key={example.question}
                    type="button"
                    title={example.hint}
                    disabled={!configured || ask.isPending}
                    onClick={() => run(example.question)}
                    className="rounded-full border border-ink-200 px-3 py-1 text-left font-sans text-xs text-ink-700 transition-colors hover:border-ink-500 hover:text-ink-900 disabled:cursor-not-allowed disabled:text-ink-300"
                  >
                    {example.question}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>

        {ask.isPending && (
          <Card>
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="mt-3 h-4 w-1/2" />
            <Skeleton className="mt-3 h-32 w-full" />
          </Card>
        )}

        {/* A transport failure — the API is down or the token is wrong. Distinct from the
            model declining to answer, which is a normal 200 handled below. */}
        {ask.isError && <ErrorState error={ask.error} onRetry={() => ask.mutate(question)} />}

        {answer && !ask.isPending && (
          <Answer key={answer.question} answer={answer} />
        )}
      </div>
    </>
  )
}

function Answer({ answer }: { answer: NonNullable<ReturnType<typeof useAsk>['data']>['data'] }) {
  if (answer.refused) return <Refusal answer={answer} />

  const columns = answer.columns.map((name) => {
    const asRate = looksLikeRate(name, answer.rows.map((row) => row[name]))
    return {
      key: name,
      header: name.replace(/_/g, ' '),
      align: 'left' as const,
      render: (row: Record<string, unknown>) => formatCell(row[name], asRate),
    }
  })

  return (
    <Card
      title={answer.question}
      subtitle={answer.explanation || undefined}
      action={<Provenance model={answer.model} cached={answer.cached} />}
    >
      {answer.sql && <SqlPanel sql={answer.sql} tables={answer.tables} />}

      <div className="mt-4 overflow-x-auto">
        <DataTable
          stickyHeader
          rows={answer.rows}
          rowKey={(_row) => String(answer.rows.indexOf(_row))}
          columns={columns}
          emptyMessage="The query ran and matched nothing. That is an answer: there are no rows like that."
        />
      </div>

      {answer.truncated && (
        <p className="mt-3 font-sans text-[11px] text-ink-500">
          Showing the first {answer.rows.length} rows. Every generated query carries a
          mandatory limit, so a question with a very wide answer is truncated rather than
          allowed to pull the whole warehouse through the API.
        </p>
      )}
    </Card>
  )
}

/** The model declining, or the validator rejecting what the model produced.
 *
 * Deliberately not styled as an error. "That cannot be answered from these views" is a
 * correct response to a question about individual salaries, and painting it red would
 * teach the reader that the tool is broken when it is behaving exactly as designed.
 */
function Refusal({
  answer,
}: {
  answer: NonNullable<ReturnType<typeof useAsk>['data']>['data']
}) {
  return (
    <Card title={answer.question} action={<Provenance model={answer.model} cached={answer.cached} />}>
      <p className="font-sans text-sm font-medium text-ink-900">Not answerable from this data</p>
      <p className="mt-1 max-w-prose font-sans text-sm leading-relaxed text-ink-700">
        {answer.refusal_reason}
      </p>

      {/* Shown when the guard rejected the model's SQL rather than the model declining.
          A refusal you can inspect is checkable; one you cannot is just a wall. */}
      {answer.sql && (
        <div className="mt-4">
          <p className="font-sans text-xs text-ink-500">The query that was rejected:</p>
          <pre className="mt-1 overflow-x-auto rounded border border-ink-200 bg-ink-50 p-3 font-mono text-xs text-ink-700">
            {answer.sql}
          </pre>
        </div>
      )}
    </Card>
  )
}

function SqlPanel({ sql, tables }: { sql: string; tables: string[] }) {
  return (
    <details className="group rounded border border-ink-200">
      <summary className="cursor-pointer list-none px-3 py-2 font-sans text-xs text-ink-700 select-none hover:text-ink-900">
        <span className="group-open:hidden">Show the SQL that produced this ▸</span>
        <span className="hidden group-open:inline">Hide the SQL ▾</span>
        {tables.length > 0 && (
          <span className="ml-2 text-ink-500">
            reads {tables.join(', ')}
          </span>
        )}
      </summary>
      <pre className="overflow-x-auto border-t border-ink-200 bg-ink-50 p-3 font-mono text-xs leading-relaxed text-ink-900">
        {sql}
      </pre>
    </details>
  )
}

function Provenance({ model, cached }: { model: string; cached: boolean }) {
  if (!model) return null
  return (
    <span className="shrink-0 font-sans text-[11px] text-ink-500">
      {model}
      {cached && ' · cached'}
    </span>
  )
}

/** Whether a column of generated output should be read as a 0-1 fraction.
 *
 * Two conditions, both required. The name has to end in something this warehouse only ever
 * uses for a proportion, *and* every value has to sit inside [-2, 2]. The range check is
 * what makes the guess safe: a column genuinely holding 0.352 as a count or an amount is
 * possible, but one holding only such values under a name ending `_rate` is not, and any
 * column with a value of 40 is left alone whatever it is called.
 *
 * Without this the demo prints "0.352" where the rest of the product prints "35.2%".
 */
function looksLikeRate(name: string, values: unknown[]): boolean {
  if (!RATE_WORDS.test(name)) return false
  const numbers = values.map(toNumber).filter((n): n is number => n !== null)
  if (numbers.length === 0) return false
  if (!numbers.every((n) => n >= -2 && n <= 2)) return false
  // At least one true fraction. A count column called `attrition_events` holding 0s and 1s
  // would otherwise pass the range check and be rendered as 0% and 100%, which is worse
  // than leaving it alone. Only integers means it is a count, whatever it is called.
  return numbers.some((n) => n > 0 && n < 1)
}

/** Words this warehouse only ever uses for a proportion. Matched anywhere in the name,
 *  because the model aliases freely — `annualized_attrition`, `retention_rate_12m`. */
const RATE_WORDS =
  /(rate|share|pct|percent|ratio|attrition|turnover|retention|conversion|utilization|participation|acceptance|completion)/i

function toNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string') return null
  // Postgres serialises a numeric zero as "0E-20", so the pattern has to accept an
  // exponent — without it that cell rendered the literal string `0E-20` on screen.
  if (!/^-?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(value.trim())) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Values arrive as whatever Postgres returned through JSON. Numerics come back as strings
 *  to preserve precision, which is correct of the driver and unhelpful on screen. */
function formatCell(value: unknown, asRate = false): string {
  if (value === null || value === undefined) return EMPTY
  if (typeof value === 'boolean') return value ? 'yes' : 'no'

  const numeric = toNumber(value)
  if (numeric !== null) {
    return asRate
      ? `${(numeric * 100).toLocaleString('en-GB', { maximumFractionDigits: 1 })}%`
      : trimNumber(numeric)
  }
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function trimNumber(value: number): string {
  if (Number.isInteger(value)) return value.toLocaleString('en-GB')
  return value.toLocaleString('en-GB', { maximumFractionDigits: 3 })
}
