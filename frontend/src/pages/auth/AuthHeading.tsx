import type { ReactNode } from "react"

interface AuthHeadingProps {
  kicker: string
  title: string
  description?: ReactNode
}

export function AuthHeading({ kicker, title, description }: AuthHeadingProps) {
  return (
    <header className="mb-8">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
        {kicker}
      </p>
      <h1 className="mt-3 font-serif text-4xl">{title}</h1>
      {description ? <p className="mt-3 text-muted-foreground">{description}</p> : null}
    </header>
  )
}