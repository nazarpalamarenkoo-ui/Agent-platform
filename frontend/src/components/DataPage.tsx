import type { ReactNode } from "react"
import type { UseQueryResult } from "@tanstack/react-query"
import { Notice } from "@/components/Notice"
import { getErrorMessage } from "@/lib/http"

interface DataPageProps<T> {
  kicker: string
  title: string
  description?: string
  actions?: ReactNode
  query: UseQueryResult<T[]>
  empty: string
  children: (items: T[]) => ReactNode
}

export function DataPage<T>({
  kicker,
  title,
  description,
  actions,
  query,
  empty,
  children,
}: DataPageProps<T>) {
  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-10 flex items-end justify-between gap-6">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            {kicker}
          </p>
          <h1 className="mt-3 font-serif text-5xl">{title}</h1>
          {description ? <p className="mt-3 text-muted-foreground">{description}</p> : null}
        </div>
        {actions}
      </header>

      {query.isPending ? (
        <p className="font-mono text-xs text-muted-foreground">Loading…</p>
      ) : query.isError ? (
        <Notice tone="error">{getErrorMessage(query.error)}</Notice>
      ) : query.data.length === 0 ? (
        <p className="text-muted-foreground">{empty}</p>
      ) : (
        children(query.data)
      )}
    </div>
  )
}