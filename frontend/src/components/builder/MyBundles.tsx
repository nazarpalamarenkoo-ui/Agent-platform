import { mySkillsApi } from "@/api"
import { ChipGroup } from "@/components/Chip"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { useBundles, useCloneBundle } from "@/hooks/useBundles"
import { useSkills } from "@/hooks/useCatalog"
import { downloadErrorMessage, useDownload } from "@/hooks/useDownload"
import { useBundleZip } from "@/hooks/useDownloadHistory"
import { getErrorMessage } from "@/lib/http"
import { cn } from "@/lib/utils"
import type { AgentRead, ConfigBundleRead } from "@/types/Index"
import { formatBundleAgents } from "@/hooks/useBundleBuilder"

function SkillFileButton({ id, name }: { id: number; name: string }) {
  const download = useDownload()
  return (
    <div className="text-right">
      <Button
        variant="ghost"
        size="sm"
        aria-label={`Download SKILL.md: ${name}`}
        disabled={download.isPending}
        onClick={() =>
          download.mutate({
            load: () => mySkillsApi.downloadMarkdown(id),
            fallbackName: "SKILL.md",
          })
        }
      >
        {download.isPending ? "Preparing…" : "SKILL.md"}
      </Button>
      {download.isError ? (
        <p role="alert" className="text-xs text-destructive">
          {downloadErrorMessage(download.error)}
        </p>
      ) : null}
    </div>
  )
}

interface BundleRowProps {
  bundle: ConfigBundleRead
  agentName: string
  active: boolean
  disabled: boolean
  privateSkillIds: Set<number>
  onEdit: (bundle: ConfigBundleRead) => void
  onDelete: (bundle: ConfigBundleRead) => void
}

function BundleRow({
  bundle,
  agentName,
  active,
  disabled,
  privateSkillIds,
  onEdit,
  onDelete,
}: BundleRowProps) {
  const clone = useCloneBundle(bundle.id)
  const zip = useBundleZip()
  const privateSkills = bundle.skills.filter((skill) => privateSkillIds.has(skill.id))

  return (
    <li className={cn("space-y-4 rounded-lg border p-4", active ? "border-red" : "border-hairline/30")}>
      <div>
        <p className="font-medium">{bundle.name}</p>
        <p className="text-sm text-muted-foreground">{bundle.description}</p>
        <p className="mt-1 font-mono text-xs text-muted-foreground">Profile: {agentName}</p>
      </div>

      <ChipGroup label="Skills" items={bundle.skills.map((s) => s.skill_name)} />
      <ChipGroup label="Tools" items={bundle.tools.map((t) => t.tool_name)} />
      <ChipGroup label="Packs" items={bundle.knowledge_packs.map((p) => p.name)} />

      {privateSkills.length > 0 ? (
        <div>
          <p className="mb-1.5 font-mono text-xs uppercase tracking-[0.15em] text-muted-foreground">
            Private skills
          </p>
          <ul className="divide-y divide-hairline/15">
            {privateSkills.map((skill) => (
              <li key={skill.id} className="flex items-center justify-between gap-3 py-1">
                <span className="min-w-0 truncate text-sm">{skill.skill_name}</span>
                <SkillFileButton id={skill.id} name={skill.skill_name} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {clone.isError ? <Notice tone="error">{getErrorMessage(clone.error)}</Notice> : null}
      {zip.isError ? <Notice tone="error">{downloadErrorMessage(zip.error)}</Notice> : null}

      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => onEdit(bundle)}>
          Edit
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={clone.isPending}
          onClick={() =>
            clone.mutate({ name: `${bundle.name} (copy)`.slice(0, 100), description: bundle.description })
          }
        >
          Clone
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={zip.isPending}
          onClick={() => zip.start(bundle)}
        >
          {zip.isPending ? "Preparing…" : "Download .zip"}
        </Button>
        <Button variant="ghost" size="sm" disabled={disabled} onClick={() => onDelete(bundle)}>
          Delete
        </Button>
      </div>
    </li>
  )
}

interface MyBundlesProps {
  agents: AgentRead[]
  activeId: number | null
  deleting: boolean
  onEdit: (bundle: ConfigBundleRead) => void
  onDelete: (bundle: ConfigBundleRead) => void
}

export function MyBundles({ agents, activeId, deleting, onEdit, onDelete }: MyBundlesProps) {
  const query = useBundles()
  const skills = useSkills()
  const privateSkillIds = new Set(
    (skills.data ?? []).filter((skill) => skill.visibility === "private").map((skill) => skill.id),
  )

  return (
    <section>
      <h2 className="mb-4 font-serif text-3xl">My bundles</h2>
      {query.isPending ? (
        <p className="font-mono text-xs text-muted-foreground">Loading…</p>
      ) : query.isError ? (
        <Notice tone="error">{getErrorMessage(query.error)}</Notice>
      ) : query.data.length === 0 ? (
        <p className="text-muted-foreground">You have no bundles yet. Create the first one above.</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {query.data.map((bundle) => (
            <BundleRow
              key={bundle.id}
              bundle={bundle}
              agentName={formatBundleAgents(bundle, agents)}
              active={bundle.id === activeId}
              disabled={deleting}
              privateSkillIds={privateSkillIds}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </ul>
      )}
    </section>
  )
}