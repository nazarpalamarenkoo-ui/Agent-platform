import type { ReactNode } from "react"
import { Notice } from "@/components/Notice"
import { getErrorMessage } from "@/lib/http"

export interface PickItem {
  id: number
  title: string
  description: string
  badges?: string[]
}

interface PickListProps {
  title: string
  items: PickItem[]
  selected: number[]
  onToggle: (id: number) => void
  loading: boolean
  error: Error | null
  emptyText: string
  action?: ReactNode
}

export function PickList({
  title,
  items,
  selected,
  onToggle,
  loading,
  error,
  emptyText,
  action,
}: PickListProps) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-4">
        <h2 className="font-serif text-2xl">
          {title}{" "}
          <span className="font-mono text-xs text-muted-foreground">
            {selected.length}/{items.length}
          </span>
        </h2>
        {action}
      </div>

      {loading ? (
        <p className="font-mono text-xs text-muted-foreground">Loading…</p>
      ) : error ? (
        <Notice tone="error">{getErrorMessage(error)}</Notice>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : (
        <ul className="max-h-72 divide-y divide-hairline/15 overflow-y-auto border-y border-hairline/15">
          {items.map((item) => (
            <li key={item.id}>
              <label className="flex cursor-pointer items-start gap-3 py-3">
                <input
                  type="checkbox"
                  checked={selected.includes(item.id)}
                  onChange={() => onToggle(item.id)}
                  className="mt-1 size-4 shrink-0"
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="font-medium">{item.title}</span>
                    {item.badges?.map((badge) => (
                      <span
                        key={badge}
                        className="rounded border border-hairline/30 px-1.5 font-mono text-[10px] text-muted-foreground"
                      >
                        {badge}
                      </span>
                    ))}
                  </span>
                  <span className="block text-sm text-muted-foreground">{item.description}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}