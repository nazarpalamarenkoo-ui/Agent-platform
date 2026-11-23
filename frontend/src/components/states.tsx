import type { ReactNode } from "react"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { getErrorMessage } from "@/lib/http"

export function LoadingLine() {
  return (
    <p role="status" className="font-mono text-xs text-muted-foreground">
      Loading...
    </p>
  )
}

export function QueryError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="space-y-3">
      <Notice tone="error">{getErrorMessage(error)}</Notice>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  )
}

interface EmptyStateProps {
  title: string
  children?: ReactNode
  action?: ReactNode
}

export function EmptyState({ title, children, action }: EmptyStateProps) {
  return (
    <div className="border border-dashed border-hairline/30 px-6 py-12 text-center">
      <h2 className="font-serif text-2xl">{title}</h2>
      {children ? <p className="mx-auto mt-2 max-w-md text-muted-foreground">{children}</p> : null}
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  )
}