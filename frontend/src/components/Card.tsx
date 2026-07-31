import type { ReactNode } from 'react'

/** The one container every chart and table sits in.
 *
 * Height is never fixed. A card sized to its plot clips the x-axis band and produces
 * a tiny nested scrollbar — one of the catalogued chart anti-patterns — so cards grow
 * with their content instead.
 */
export function Card({
  title,
  subtitle,
  action,
  children,
  className = '',
}: {
  title?: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-lg border border-ink-200 bg-white p-5 ${className}`}>
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && (
              <h2 className="font-sans text-sm font-semibold tracking-tight text-ink-900">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="mt-0.5 font-sans text-xs leading-relaxed text-ink-500">{subtitle}</p>
            )}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

/** Page heading. Time is the structural spine, so the period being viewed is stated
 *  once at the top rather than repeated on every chart. */
export function PageHeader({
  title,
  description,
  meta,
}: {
  title: string
  description?: string
  meta?: ReactNode
}) {
  return (
    <header className="mb-6">
      <h1 className="font-sans text-2xl font-semibold tracking-tight text-ink-900">{title}</h1>
      {description && (
        <p className="mt-1 max-w-prose font-sans text-sm leading-relaxed text-ink-700">
          {description}
        </p>
      )}
      {meta && <div className="mt-2 font-sans text-xs text-ink-500">{meta}</div>}
    </header>
  )
}
