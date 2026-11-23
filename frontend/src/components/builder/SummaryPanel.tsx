import type { ReactNode } from "react"
import { FormField } from "@/components/FormField"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { getErrorMessage } from "@/lib/http"

interface SummaryPanelProps {
  name: string
  description: string
  onNameChange: (value: string) => void
  onDescriptionChange: (value: string) => void
  agentName: string | null
  skills: number
  tools: number
  packs: number
  editing: boolean
  canSubmit: boolean
  submitting: boolean
  error: Error | null
  fieldErrors: Record<string, string | undefined>
  onSubmit: () => void
  onReset: () => void
  extra?: ReactNode
}

export function SummaryPanel({
  name,
  description,
  onNameChange,
  onDescriptionChange,
  agentName,
  skills,
  tools,
  packs,
  editing,
  canSubmit,
  submitting,
  error,
  fieldErrors,
  onSubmit,
  onReset,
  extra,
}: SummaryPanelProps) {
  const hasFieldErrors = Object.keys(fieldErrors).length > 0

  return (
    <aside className="space-y-5 rounded-lg border border-hairline/30 p-5 lg:sticky lg:top-6 lg:self-start">
      <div>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          {editing ? "Editing bundle" : "New bundle"}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          {agentName ?? "No profile selected"} · {skills} skills · {tools} tools · {packs} packs
        </p>
      </div>

      {error && !hasFieldErrors ? <Notice tone="error">{getErrorMessage(error)}</Notice> : null}

      <FormField
        label="Name"
        required
        maxLength={100}
        value={name}
        onChange={(event) => onNameChange(event.target.value)}
        error={fieldErrors.name}
      />
      <FormField
        label="Description"
        required
        maxLength={255}
        value={description}
        onChange={(event) => onDescriptionChange(event.target.value)}
        error={fieldErrors.description}
      />

      <div className="flex gap-2">
        <Button className="flex-1" disabled={!canSubmit || submitting} onClick={onSubmit}>
          {submitting ? "Saving…" : editing ? "Save changes" : "Create bundle"}
        </Button>
        <Button variant="ghost" onClick={onReset}>
          {editing ? "Cancel" : "Clear"}
        </Button>
      </div>

      {extra}
    </aside>
  )
}