import { NavLink, Outlet, useSearchParams } from 'react-router-dom'

import { FilterBar } from '@/components/FilterBar'
import { useHealth } from '@/hooks/useHealth'

/** Sidebar navigation, filter bar, and the API status pill.
 *
 * Nav links carry the current search params forward, so moving between pages keeps
 * the slice you were looking at. A filter that resets on navigation is worse than no
 * filter — it silently changes what the next page means.
 */

const PAGES = [
  { to: '/', label: 'Overview', end: true },
  { to: '/acquisition', label: 'Talent Acquisition' },
  { to: '/retention', label: 'Retention' },
  { to: '/engagement', label: 'Engagement' },
  { to: '/productivity', label: 'Productivity' },
  { to: '/ask', label: 'Ask' },
]

function ApiStatus() {
  const { data, isPending, isError } = useHealth()

  const tone = isPending
    ? 'bg-ink-300'
    : isError
      ? 'bg-risk'
      : 'bg-good'
  const label = isPending ? 'checking' : isError ? 'unreachable' : `v${data?.data.version ?? '?'}`

  return (
    <div className="flex items-center gap-2 px-4 py-3">
      <span className={`h-1.5 w-1.5 rounded-full ${tone}`} aria-hidden="true" />
      <span className="font-sans text-xs text-ink-500">API {label}</span>
    </div>
  )
}

export function AppShell() {
  const [searchParams] = useSearchParams()
  const query = searchParams.toString()
  const suffix = query ? `?${query}` : ''

  return (
    <div className="flex min-h-full">
      <nav
        aria-label="Sections"
        className="flex w-56 shrink-0 flex-col justify-between border-r border-ink-200 bg-white"
      >
        <div>
          <div className="px-4 py-5">
            <p className="font-sans text-sm font-semibold tracking-tight text-ink-900">
              People Analytics
            </p>
            <p className="mt-0.5 font-sans text-xs text-ink-500">Synthetic data</p>
          </div>

          <ul className="space-y-0.5 px-2">
            {PAGES.map((page) => (
              <li key={page.to}>
                <NavLink
                  to={`${page.to}${suffix}`}
                  end={page.end}
                  className={({ isActive }) =>
                    [
                      'block rounded px-2.5 py-1.5 font-sans text-sm transition-colors',
                      isActive
                        ? 'bg-ink-100 font-medium text-ink-900'
                        : 'text-ink-700 hover:bg-ink-50',
                    ].join(' ')
                  }
                >
                  {page.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>

        <ApiStatus />
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <FilterBar />
        <main className="flex-1 px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
