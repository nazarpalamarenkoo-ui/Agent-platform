import type { ReactNode } from "react"

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-hairline/30 p-4">
      <dt className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 font-serif text-3xl tabular-nums">{value}</dd>
    </div>
  )
}