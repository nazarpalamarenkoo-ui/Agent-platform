import type { ReactNode } from "react"

export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded border border-hairline/30 px-2 py-0.5 font-mono text-xs">
      {children}
    </span>
  )
}

export function ChipGroup({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1.5 font-mono text-xs uppercase tracking-[0.15em] text-muted-foreground">
        {label}
      </p>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">None</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item) => (
            <Chip key={item}>{item}</Chip>
          ))}
        </div>
      )}
    </div>
  )
}