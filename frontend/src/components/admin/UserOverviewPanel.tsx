import { useState } from "react"
import { Notice } from "@/components/Notice"
import { Stamp } from "@/components/Stamp"
import { Stat } from "@/components/Stat"
import { Button } from "@/components/ui/button"
import {
  useArchiveUserSkill,
  useUserOverview,
  useUserSkillContent,
  useUserSkills,
  useUserTools,
} from "@/hooks/useAdminUsers"
import { useUserBundles } from "@/hooks/useAdminUserBundles"
import { useAgents } from "@/hooks/useCatalog"
import { getErrorMessage } from "@/lib/http"
import type { AdminSkillListItem, AdminUserRead } from "@/types/Index"
import { bundleAgentIdsOf, formatBundleAgents } from "@/hooks/useBundleBuilder"

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 font-mono text-xs uppercase tracking-[0.15em] text-muted-foreground">
        {title}
      </h3>
      {children}
    </div>
  )
}

function Loading() {
  return <p className="font-mono text-xs text-muted-foreground">Loading…</p>
}

function SkillRow({
  userId,
  skill,
  busy,
  onArchive,
}: {
  userId: number
  skill: AdminSkillListItem
  busy: boolean
  onArchive: (skill: AdminSkillListItem) => void
}) {
  const [open, setOpen] = useState(false)
  const content = useUserSkillContent(userId, skill.id, open)
  const archived = skill.archived_at !== null

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2">
            <span className="font-medium">{skill.skill_name}</span>
            {archived ? <Stamp tone="alert">archived</Stamp> : null}
          </p>
          <p className="text-sm text-muted-foreground">{skill.description}</p>
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            {open ? "Hide" : "View"}
          </Button>
          {!archived ? (
            <Button variant="outline" size="sm" disabled={busy} onClick={() => onArchive(skill)}>
              Archive
            </Button>
          ) : null}
        </div>
      </div>
      {open ? (
        content.isPending ? (
          <div className="mt-2">
            <Loading />
          </div>
        ) : content.isError ? (
          <div className="mt-2">
            <Notice tone="error">{getErrorMessage(content.error)}</Notice>
          </div>
        ) : (
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-hairline/30 p-3 font-mono text-xs leading-relaxed">
            {content.data.content}
          </pre>
        )
      ) : null}
    </li>
  )
}

export function UserOverviewPanel({ user }: { user: AdminUserRead }) {
  const [includeArchived, setIncludeArchived] = useState(false)
  const overview = useUserOverview(user.id)
  const bundles = useUserBundles(user.id)
  const skills = useUserSkills(user.id, includeArchived)
  const tools = useUserTools(user.id, includeArchived)
  const agents = useAgents()
  const archive = useArchiveUserSkill(user.id)

  const usedAgents = new Set((bundles.data ?? []).flatMap((b) => bundleAgentIdsOf(b)))
  const data = overview.data

  function onArchive(skill: AdminSkillListItem) {
    const reason = window
      .prompt(`Reason for archiving "${skill.skill_name}" (the user will be notified):`)
      ?.trim()
    if (!reason) return
    archive.mutate({ skillId: skill.id, reason: reason.slice(0, 255) })
  }

  return (
    <div className="space-y-8 rounded-lg border border-hairline/30 p-5">
      {overview.isError ? <Notice tone="error">{getErrorMessage(overview.error)}</Notice> : null}

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Private skills" value={data?.private_skills ?? "–"} />
        <Stat label="Private tools" value={data?.private_tools ?? "–"} />
        <Stat label="Bundles" value={data?.bundles ?? "–"} />
        <Stat label="Agents in use" value={bundles.data ? usedAgents.size : "–"} />
        <Stat label="Token events" value={data?.token_events ?? "–"} />
        <Stat
          label="Tokens"
          value={
            data ? (
              <span className="text-xl">
                {data.tokens_used.toLocaleString("en-US")}
                <span className="text-muted-foreground"> / {data.token_limit.toLocaleString("en-US")}</span>
              </span>
            ) : (
              "–"
            )
          }
        />
      </dl>

      <Block title="Bundles">
        {bundles.isPending ? (
          <Loading />
        ) : bundles.isError ? (
          <Notice tone="error">{getErrorMessage(bundles.error)}</Notice>
        ) : bundles.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No bundles.</p>
        ) : (
          <ul className="divide-y divide-hairline/15 border-y border-hairline/15">
            {bundles.data.map((bundle) => (
              <li key={bundle.id} className="py-2">
                <p className="font-medium">{bundle.name}</p>
                <p className="font-mono text-xs text-muted-foreground">
                  {formatBundleAgents(bundle, agents.data)} · 
                  {bundle.skills.length} skills · 
                  {bundle.tools.length} tools · 
                  {bundle.knowledge_packs.length} packs
                </p>
              </li>
            ))}
          </ul>
        )}
      </Block>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={includeArchived}
          onChange={(event) => setIncludeArchived(event.target.checked)}
          className="size-4"
        />
        Show archived
      </label>

      {archive.isError ? <Notice tone="error">{getErrorMessage(archive.error)}</Notice> : null}

      <Block title="Skills">
        {skills.isPending ? (
          <Loading />
        ) : skills.isError ? (
          <Notice tone="error">{getErrorMessage(skills.error)}</Notice>
        ) : skills.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No skills.</p>
        ) : (
          <ul className="divide-y divide-hairline/15 border-y border-hairline/15">
            {skills.data.map((skill) => (
              <SkillRow
                key={skill.id}
                userId={user.id}
                skill={skill}
                busy={archive.isPending}
                onArchive={onArchive}
              />
            ))}
          </ul>
        )}
      </Block>

      <Block title="Tools">
        {tools.isPending ? (
          <Loading />
        ) : tools.isError ? (
          <Notice tone="error">{getErrorMessage(tools.error)}</Notice>
        ) : tools.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tools.</p>
        ) : (
          <ul className="divide-y divide-hairline/15 border-y border-hairline/15">
            {tools.data.map((tool) => (
              <li key={tool.id} className="py-2">
                <p className="flex items-center gap-2">
                  <span className="font-medium">{tool.tool_name}</span>
                  {tool.archived_at ? <Stamp tone="alert">archived</Stamp> : null}
                </p>
                <p className="text-sm text-muted-foreground">{tool.description}</p>
                <p className="truncate font-mono text-xs text-muted-foreground">{tool.url_masked}</p>
              </li>
            ))}
          </ul>
        )}
      </Block>
    </div>
  )
}