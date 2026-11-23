import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface StampProps {
  tone?: "default" | "alert"
  children: ReactNode
}

export function Stamp({ tone = "default", children }: StampProps) {
  return (
    <span
      className={cn(
        "inline-block border px-1.5 py-0.5 font-mono text-[10px] uppercase leading-none tracking-wider",
        tone === "alert"
          ? "border-red/50 text-red-deep"
          : "border-hairline/30 text-muted-foreground",
      )}
    >
      {children}
    </span>
  )
}