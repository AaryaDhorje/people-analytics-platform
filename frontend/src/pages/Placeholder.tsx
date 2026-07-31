import { PageHeader } from '@/components/Card'

/** Stands in for a domain page until phase 5 builds it.
 *
 * It names what will be here rather than saying "coming soon", so the shell can be
 * navigated and reviewed before the pages exist — and so an empty route never looks
 * like a bug.
 */
export function Placeholder({
  title,
  description,
  planned,
}: {
  title: string
  description: string
  planned: string[]
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <div className="rounded-lg border border-dashed border-ink-200 bg-white p-8">
        <p className="font-sans text-sm font-medium text-ink-700">Not built yet</p>
        <ul className="mt-3 space-y-1">
          {planned.map((item) => (
            <li key={item} className="font-sans text-sm text-ink-500">
              — {item}
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
