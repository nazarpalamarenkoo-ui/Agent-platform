import type { ReactNode } from "react"
import { Notice } from "@/components/Notice"
import { getErrorMessage } from "@/lib/http"
import { cn } from "@/lib/utils"
import type { AgentRead } from "@/types/Index"

interface AgentPickerProps {
  agents: AgentRead[]
  selectedIds: number[]
  onToggle: (id: number) => void
  locked?: boolean
  loading: boolean
  error: Error | null
  action?: ReactNode
}

export function AgentPicker({
  agents,
  selectedIds,
  onToggle,
  locked = false,
  loading,
  error,
  action,
}: AgentPickerProps) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-4">
        <div>
          <h2 className="font-serif text-2xl">
            Agent profiles{" "}
            <span className="font-mono text-xs text-muted-foreground">
              {selectedIds.length}/{agents.length}
            </span>
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Select one or multiple agent profiles to form a multi-agent team bundle.
          </p>
        </div>
        {action}
      </div>

      {loading ? (
        <p className="font-mono text-xs text-muted-foreground">Loading…</p>
      ) : error ? (
        <Notice tone="error">{getErrorMessage(error)}</Notice>
      ) : agents.length === 0 ? (
        <p className="text-sm text-muted-foreground">No agent profiles yet.</p>
      ) : (
        <div role="group" aria-label="Agent profiles" className="grid gap-3 sm:grid-cols-2">
          {agents.map((agent) => {
            const active = selectedIds.includes(agent.id)
            const orderIdx = selectedIds.indexOf(agent.id)
            return (
              <button
                key={agent.id}
                type="button"
                aria-pressed={active}
                disabled={locked && !active}
                onClick={() => onToggle(agent.id)}
                className={cn(
                  "rounded-lg border p-4 text-left transition-colors disabled:opacity-40",
                  active ? "border-red bg-accent" : "border-hairline/30 hover:bg-accent",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">{agent.agent_name}</p>
                  {active ? (
                    <span className="rounded border border-red/50 px-1.5 py-0.5 font-mono text-[10px] uppercase text-red-deep">
                      #{orderIdx + 1} selected
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{agent.description}</p>
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  {agent.skills.length} skills · {agent.tools.length} tools
                </p>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}