import type { ReactNode } from "react"

export function PageContainer({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-5xl px-6 py-12">{children}</div>
}