import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface NoticeProps {
  tone?: "info" | "error"
  children: ReactNode
}

export function Notice({ tone = "info", children }: NoticeProps) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "border-l-2 py-1 pl-3 text-sm",
        tone === "error" ? "border-destructive text-destructive" : "border-red text-foreground",
      )}
    >
      {children}
    </div>
  )
}