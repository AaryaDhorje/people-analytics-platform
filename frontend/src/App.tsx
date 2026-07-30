import { useHealth } from '@/hooks/useHealth'

/** Phase-0 shell. It exists to prove the request path end to end: Vite → React →
 *  TanStack Query → CORS → FastAPI → envelope. The real navigation, global filter
 *  bar, and dashboard pages arrive in phase 5. */
export default function App() {
  const { data, isPending, isError, error } = useHealth()

  return (
    <main className="mx-auto flex min-h-full max-w-3xl flex-col justify-center gap-8 px-6 py-16">
      <header className="space-y-3">
        <p className="font-sans text-xs font-medium tracking-[0.18em] text-ink-500 uppercase">
          Phase 0 · Foundation
        </p>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-ink-900">
          People Analytics
        </h1>
        <p className="max-w-prose font-sans text-base leading-relaxed text-ink-700">
          Talent acquisition, retention, engagement, and productivity over a synthetic HR
          warehouse. All data is generated — no real employee records are involved.
        </p>
      </header>

      <section
        aria-labelledby="api-status"
        className="rounded-lg border border-ink-100 bg-white p-6 shadow-sm"
      >
        <h2
          id="api-status"
          className="font-sans text-xs font-medium tracking-[0.18em] text-ink-500 uppercase"
        >
          API status
        </h2>

        {isPending && (
          <div className="mt-4 space-y-2" role="status" aria-live="polite">
            <div className="h-5 w-40 animate-pulse rounded bg-ink-100" />
            <div className="h-4 w-64 animate-pulse rounded bg-ink-100" />
            <span className="sr-only">Checking the API</span>
          </div>
        )}

        {isError && (
          <div className="mt-4 space-y-1">
            <p className="font-display text-lg font-semibold text-ink-900">Not reachable</p>
            <p className="font-sans text-sm leading-relaxed text-ink-700">
              {error instanceof Error ? error.message : 'Unknown error.'}
            </p>
            <p className="font-sans text-sm leading-relaxed text-ink-500">
              Start it with{' '}
              <code className="rounded bg-ink-100 px-1.5 py-0.5 text-ink-900">
                uvicorn app.main:app --reload
              </code>{' '}
              in <code className="text-ink-900">backend/</code>.
            </p>
          </div>
        )}

        {data && (
          <dl className="mt-4 grid grid-cols-3 gap-6">
            {[
              { label: 'Status', value: data.data.status },
              { label: 'Environment', value: data.data.env },
              { label: 'Version', value: data.data.version },
            ].map((item) => (
              <div key={item.label}>
                <dt className="font-sans text-xs text-ink-500">{item.label}</dt>
                <dd className="font-display tnum mt-1 text-xl font-semibold text-ink-900">
                  {item.value}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <footer className="font-sans text-xs text-ink-500">
        Metric definitions are fixed in <code className="text-ink-700">docs/METRICS.md</code>.
      </footer>
    </main>
  )
}
