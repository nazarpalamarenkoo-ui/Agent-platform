import { useId, useState, type FormEvent } from "react"
import { Chip, ChipGroup } from "@/components/Chip"
import { FormField } from "@/components/FormField"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import type { SkillDraftApi } from "@/hooks/useSkillDraft"
import type { SkillDraftResult } from "@/types/Index"

const areaClass =
  "w-full rounded-md border border-hairline/30 bg-transparent p-3 font-mono text-xs leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

interface ReadyFormProps {
  result: SkillDraftResult
  draft: SkillDraftApi
}

function ReadyForm({ result, draft }: ReadyFormProps) {
  const contentId = useId()
  const [name, setName] = useState(
    result.skill_name ?? (result as unknown as { name?: string }).name ?? "",
  )
  const [description, setDescription] = useState(result.description ?? "")
  const [content, setContent] = useState(result.content ?? "")
  const [reading, setReading] = useState(false)

  const canSave =
    name.trim() !== "" && description.trim() !== "" && content.trim() !== "" && !draft.isSaving

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSave) return
    draft.save({ skill_name: name.trim(), description: description.trim(), content })
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Chip>{result.grounded ? "Grounded in knowledge" : "Unverified"}</Chip>
        {result.grounded ? null : (
          <span className="text-sm text-muted-foreground">
            Not checked against any knowledge. Read it carefully before saving.
          </span>
        )}
      </div>

      {result.warnings.map((warning) => (
        <Notice key={warning}>{warning}</Notice>
      ))}
      {result.sources.length > 0 ? <ChipGroup label="Sources" items={result.sources} /> : null}

      <FormField
        label="Skill name"
        required
        maxLength={100}
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <FormField
        label="Description"
        required
        maxLength={255}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        hint={`${description.length}/255`}
      />

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <Label htmlFor={contentId}>Content</Label>
          <div className="flex gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-pressed={!reading}
              onClick={() => setReading(false)}
            >
              Edit
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-pressed={reading}
              onClick={() => setReading(true)}
            >
              Read
            </Button>
          </div>
        </div>
        {reading ? (
          <div
            aria-label="Draft content"
            className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-hairline/30 p-3 text-sm leading-relaxed"
          >
            {content}
          </div>
        ) : (
          <textarea
            id={contentId}
            required
            rows={12}
            maxLength={50_000}
            value={content}
            onChange={(event) => setContent(event.target.value)}
            className={areaClass}
          />
        )}
      </div>

      {draft.saveError ? <Notice tone="error">{draft.saveError}</Notice> : null}

      <div className="flex gap-2">
        <Button type="submit" disabled={!canSave}>
          {draft.isSaving ? "Saving…" : "Save as my skill"}
        </Button>
        <Button type="button" variant="ghost" onClick={draft.discard} disabled={draft.isSaving}>
          Discard
        </Button>
      </div>
    </form>
  )
}

export function SkillDraftCard({ draft }: { draft: SkillDraftApi }) {
  const { phase } = draft
  if (phase.name === "idle") return null

  return (
    <section aria-label="Skill draft" className="mt-6 rounded-lg border border-hairline/30 p-5">
      <h3 className="mb-4 font-serif text-xl">Skill draft</h3>

      {phase.name === "requesting" ? (
        <p role="status" className="font-mono text-xs text-muted-foreground">
          Sending request…
        </p>
      ) : null}

      {phase.name === "waiting" ? (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span aria-hidden="true" className="size-2 animate-pulse bg-red" />
            <p role="status" className="text-sm">
              {phase.label === "Queued"
                ? "Queued: waiting for a free worker."
                : "Generating the draft…"}
            </p>
          </div>
          <p className="text-xs text-muted-foreground">
            This can take a while. Keep working: the draft stays here if you reload the page (in
            this tab).
          </p>
          <Button variant="ghost" size="sm" onClick={draft.discard}>
            Discard
          </Button>
        </div>
      ) : null}

      {phase.name === "error" ? (
        <div className="space-y-3">
          <Notice tone="error">{phase.message}</Notice>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={draft.retryStatus}>
              Check again
            </Button>
            <Button variant="ghost" size="sm" onClick={draft.discard}>
              Discard
            </Button>
          </div>
        </div>
      ) : null}

      {phase.name === "failed" ? (
        <div className="space-y-3">
          <Notice tone="error">{phase.message}</Notice>
          <Button variant="outline" size="sm" onClick={draft.discard}>
            Dismiss
          </Button>
        </div>
      ) : null}

      {phase.name === "ready" ? (
        <ReadyForm key={phase.jobId} result={phase.draft} draft={draft} />
      ) : null}

      {phase.name === "saved" ? (
        <div className="space-y-3">
          <Notice>
            {phase.skill
              ? `Saved "${phase.skill.skill_name}" as your private skill.`
              : "This draft was already saved. You'll find it in your skills list."}
          </Notice>
          <Button variant="outline" size="sm" onClick={draft.discard}>
            Done
          </Button>
        </div>
      ) : null}
    </section>
  )
}
