import type { ReactNode } from "react"

interface PageHeaderProps {
  kicker: string
  title: string
  description?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ kicker, title, description, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-6 border-b border-hairline/15 pb-8">
      <div className="min-w-0">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          {kicker}
        </p>
        <h1 className="mt-3 break-words font-serif text-5xl">{title}</h1>
        {description ? (
          <p className="mt-3 max-w-xl text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
    </header>
  )
}