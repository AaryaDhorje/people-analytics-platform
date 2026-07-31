import { useFilters } from '@/hooks/useFilters'

/** One filter row above everything it scopes.
 *
 * Never per-chart and never inside a card: every chart on the page re-renders against
 * the same slice, so two charts can never disagree about which period they show.
 *
 * Values are hardcoded rather than fetched from a dimensions endpoint. The dimension
 * tables hold eight departments, four locations and six levels and none of them change
 * during the build — a lookup endpoint would be a round-trip to learn constants.
 */

const DEPARTMENTS = [
  { id: 1, name: 'Engineering' },
  { id: 2, name: 'Sales' },
  { id: 3, name: 'Support' },
  { id: 4, name: 'Operations' },
  { id: 5, name: 'Product' },
  { id: 6, name: 'Marketing' },
  { id: 7, name: 'Finance' },
  { id: 8, name: 'People' },
]

const LOCATIONS = [
  { id: 1, name: 'San Francisco' },
  { id: 2, name: 'Austin' },
  { id: 3, name: 'London' },
  { id: 4, name: 'Bengaluru' },
]

const LEVELS = [
  { id: 1, name: 'L1 Associate' },
  { id: 2, name: 'L2 Analyst' },
  { id: 3, name: 'L3 Senior' },
  { id: 4, name: 'L4 Lead' },
  { id: 5, name: 'L5 Manager' },
  { id: 6, name: 'L6 Director' },
]

const selectClass =
  'rounded border border-ink-200 bg-white px-2.5 py-1.5 font-sans text-sm text-ink-900 ' +
  'transition-colors hover:border-ink-300 focus:border-seq-450 focus:outline-none'

export function FilterBar() {
  const { filters, setFilter, clearFilters, activeCount } = useFilters()

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-ink-200 bg-ink-50 px-6 py-3">
      <span className="mr-1 font-sans text-xs font-medium tracking-wide text-ink-500 uppercase">
        Filters
      </span>

      <label className="sr-only" htmlFor="filter-department">
        Department
      </label>
      <select
        id="filter-department"
        className={selectClass}
        value={filters.department_id ?? ''}
        onChange={(event) =>
          setFilter('department_id', event.target.value ? Number(event.target.value) : undefined)
        }
      >
        <option value="">All departments</option>
        {DEPARTMENTS.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>

      <label className="sr-only" htmlFor="filter-location">
        Location
      </label>
      <select
        id="filter-location"
        className={selectClass}
        value={filters.location_id ?? ''}
        onChange={(event) =>
          setFilter('location_id', event.target.value ? Number(event.target.value) : undefined)
        }
      >
        <option value="">All locations</option>
        {LOCATIONS.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>

      <label className="sr-only" htmlFor="filter-level">
        Job level
      </label>
      <select
        id="filter-level"
        className={selectClass}
        value={filters.level ?? ''}
        onChange={(event) =>
          setFilter('level', event.target.value ? Number(event.target.value) : undefined)
        }
      >
        <option value="">All levels</option>
        {LEVELS.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>

      <label className="sr-only" htmlFor="filter-from">
        From month
      </label>
      <input
        id="filter-from"
        type="month"
        className={selectClass}
        value={filters.date_from?.slice(0, 7) ?? ''}
        onChange={(event) =>
          setFilter('date_from', event.target.value ? `${event.target.value}-01` : undefined)
        }
      />
      <span className="font-sans text-xs text-ink-500">to</span>
      <label className="sr-only" htmlFor="filter-to">
        To month
      </label>
      <input
        id="filter-to"
        type="month"
        className={selectClass}
        value={filters.date_to?.slice(0, 7) ?? ''}
        onChange={(event) =>
          setFilter('date_to', event.target.value ? `${event.target.value}-01` : undefined)
        }
      />

      {activeCount > 0 && (
        <button
          type="button"
          onClick={clearFilters}
          className="ml-auto rounded px-2.5 py-1.5 font-sans text-sm text-ink-700 underline-offset-2 transition-colors hover:bg-ink-100 hover:underline"
        >
          Clear {activeCount} filter{activeCount === 1 ? '' : 's'}
        </button>
      )}
    </div>
  )
}
