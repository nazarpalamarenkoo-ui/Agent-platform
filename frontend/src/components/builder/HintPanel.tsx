import { useState, type FormEvent } from "react"
import { Chip } from "@/components/Chip"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { SkillDraftCard } from "@/components/builder/SkillDraftCard"
import { useCatalogHint } from "@/hooks/useBundleBuilder"
import { useSkillDraft } from "@/hooks/useSkillDraft"
import { getErrorMessage, isApiError } from "@/lib/http"
import type { HintGap, HintResponse, MySkillRead } from "@/types/Index"

interface HintPanelProps {
  onApply: (hint: HintResponse) => void
  onSkillSaved: (skill: MySkillRead) => void
  configBundleId?: number | null
}

const areaClass =
  "mt-2 w-full rounded-md border border-hairline/30 bg-transparent p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"


export function HintPanel({ onApply, onSkillSaved, configBundleId = null }: HintPanelProps) {
  const [intent, setIntent] = useState("")
  const [sourceText, setSourceText] = useState("")
  const [directIntent, setDirectIntent] = useState("")
  const [directSource, setDirectSource] = useState("")
  const hint = useCatalogHint()
  const draft = useSkillDraft({ configBundleId, onSaved: onSkillSaved })

  const error = hint.error
  const message =
    isApiError(error) && error.status === 429
      ? `Too many requests.${error.retryAfter ? ` Try again in ${error.retryAfter}s.` : ""}`
      : error
        ? getErrorMessage(error)
        : null

  const gaps: HintGap[] = hint.isSuccess ? (hint.data.gaps ?? []) : []
  const hintedPackIds: number[] = hint.isSuccess
    ? hint.data.knowledge_packs.map((p) => p.id)
    : []

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    hint.mutate(intent.trim(), { onSuccess: onApply })
  }

  function onDirectSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (draft.busy || directIntent.trim() === "") return
    draft.requestDraft({
      intent: directIntent.trim(),
      sourceText: directSource,
      knowledgePackIds: hintedPackIds,
    })
  }

  return (
    <section className="rounded-lg border border-hairline/30 p-5">
      <h2 className="font-serif text-2xl">Describe what you need</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        The assistant picks a profile, skills, tools and knowledge packs for you. You can adjust
        the selection below.
      </p>

      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <textarea
          aria-label="What should the agent do?"
          value={intent}
          onChange={(event) => setIntent(event.target.value)}
          maxLength={1000}
          rows={3}
          placeholder="e.g. Draw architecture diagrams for our microservices and review Docker setups"
          className="w-full rounded-md border border-hairline/30 bg-transparent p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={hint.isPending || intent.trim() === ""}>
            {hint.isPending ? "Thinking…" : "Suggest a setup"}
          </Button>
          <span className="font-mono text-xs text-muted-foreground">{intent.length}/1000</span>
        </div>
      </form>

      {message ? (
        <div className="mt-4">
          <Notice tone="error">{message}</Notice>
        </div>
      ) : null}

      {hint.isSuccess ? (
        <p className="mt-4 text-sm">
          {hint.data.reasoning || "Suggestion applied."}{" "}
          <span className="text-muted-foreground">
            ({hint.data.skills.length} skills, {hint.data.tools.length} tools,{" "}
            {hint.data.knowledge_packs.length} packs)
          </span>
        </p>
      ) : null}

      {gaps.length > 0 ? (
        <div className="mt-6 border-t border-hairline/15 pt-5">
          <h3 className="font-serif text-xl">Not in the catalog</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Your task needs these, but they don't exist yet.{" "}
            {configBundleId !== null
              ? "Drafts will be checked against this bundle's knowledge."
              : "Without a bundle the draft can't be checked against knowledge: add source text below, or edit an existing bundle."}
          </p>

          <details className="mt-3">
            <summary className="cursor-pointer text-sm">Add source text (optional)</summary>
            <label className="sr-only" htmlFor="draft-source-text">
              Source text for the draft
            </label>
            <textarea
              id="draft-source-text"
              rows={4}
              maxLength={20_000}
              value={sourceText}
              onChange={(event) => setSourceText(event.target.value)}
              placeholder="Paste documentation or notes the skill should be based on"
              className={areaClass}
            />
          </details>

          <ul className="mt-4 divide-y divide-hairline/15 border-y border-hairline/15">
            {gaps.map((gap) => (
              <li
                key={`${gap.kind}:${gap.name}`}
                className="flex flex-wrap items-start justify-between gap-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2">
                    <Chip>{gap.kind}</Chip>
                    <span className="font-medium">{gap.name}</span>
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">{gap.description}</p>
                  {gap.reason ? (
                    <p className="mt-1 text-xs text-muted-foreground">Why: {gap.reason}</p>
                  ) : null}
                </div>

                {gap.kind === "skill" ? (
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label={`Create draft: ${gap.name}`}
                    disabled={draft.busy}
                    onClick={() =>
                      draft.requestDraft({
                        intent: `${gap.name}: ${gap.description}`,
                        sourceText,
                        knowledgePackIds: hintedPackIds,
                      })
                    }
                  >
                    Create draft
                  </Button>
                ) : (
                  <p className="text-xs text-muted-foreground">Needs an admin to add it.</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-6 border-t border-hairline/15 pt-5">
        <h3 className="font-serif text-xl">Draft a new skill</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Describe a skill that doesn't exist yet. The assistant researches it and writes a draft
          for you to review before anything is saved.{" "}
          {configBundleId !== null
            ? "It will draw on this bundle's knowledge."
            : "Without a bundle or source text the draft can't be checked against knowledge."}
        </p>

        <form onSubmit={onDirectSubmit} className="mt-3 space-y-3">
          <textarea
            aria-label="What should the new skill do?"
            value={directIntent}
            onChange={(event) => setDirectIntent(event.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="e.g. Review Dockerfiles for security and image-size problems"
            className="w-full rounded-md border border-hairline/30 bg-transparent p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <details>
            <summary className="cursor-pointer text-sm">Add source text (optional)</summary>
            <textarea
              aria-label="Source text for the new skill"
              value={directSource}
              onChange={(event) => setDirectSource(event.target.value)}
              maxLength={20_000}
              rows={4}
              placeholder="Paste documentation or notes the skill should be based on"
              className={areaClass}
            />
          </details>
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={draft.busy || directIntent.trim() === ""}>
              {draft.phase.name === "requesting" ? "Sending…" : "Generate draft"}
            </Button>
            <span className="font-mono text-xs text-muted-foreground">
              {directIntent.length}/2000
            </span>
          </div>
        </form>
      </div>

      {draft.requestError ? (
        <div className="mt-4">
          <Notice tone="error">{draft.requestError}</Notice>
        </div>
      ) : null}

      <SkillDraftCard draft={draft} />
    </section>
  )
}