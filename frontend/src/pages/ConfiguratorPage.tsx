import { useState } from "react"
import { Notice } from "@/components/Notice"
import { AgentPicker } from "@/components/builder/AgentPicker"
import { NewAgentForm, NewSkillForm, NewToolForm } from "@/components/builder/CreateForms"
import { HintPanel } from "@/components/builder/HintPanel"
import { MyBundles } from "@/components/builder/MyBundles"
import { PickList } from "@/components/builder/PickList"
import { SummaryPanel } from "@/components/builder/SummaryPanel"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/auth/useAuth"
import {
  selectionOf,
  useCreateBundle,
  useSaveBundleChanges,
  useUpdateAgent,
} from "@/hooks/useBundleBuilder"
import { useDeleteBundle } from "@/hooks/useBundles"
import { useAgents, usePacks, useSkills, useTools } from "@/hooks/useCatalog"
import { fieldErrorsOf } from "@/lib/forms"
import { getErrorMessage } from "@/lib/http"
import type { ConfigBundleRead, HintResponse } from "@/types/Index"

const unique = (ids: number[]) => [...new Set(ids)]
const toggle = (ids: number[], id: number) =>
  ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]
const badgesOf = (...parts: (string | false | undefined)[]): string[] =>
  parts.filter((part): part is string => Boolean(part))

export function ConfiguratorPage() {
  const { isAdmin } = useAuth()
  const agents = useAgents()
  const skills = useSkills()
  const tools = useTools()
  const packs = usePacks()

  const [agentIds, setAgentIds] = useState<number[]>([])
  const [skillIds, setSkillIds] = useState<number[]>([])
  const [toolIds, setToolIds] = useState<number[]>([])
  const [packIds, setPackIds] = useState<number[]>([])
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [editing, setEditing] = useState<ConfigBundleRead | null>(null)

  const create = useCreateBundle()
  const save = useSaveBundleChanges()
  const updateAgent = useUpdateAgent()
  const remove = useDeleteBundle()

  const selectedAgents = (agents.data ?? []).filter((a) => agentIds.includes(a.id))
  const primaryAgent = selectedAgents[0] ?? null
  const selectedAgentNames =
    selectedAgents.length > 0 ? selectedAgents.map((a) => a.agent_name).join(", ") : null

  const baseSkills = new Set(selectedAgents.flatMap((a) => a.skills.map((s) => s.id)))
  const baseTools = new Set(selectedAgents.flatMap((a) => a.tools.map((t) => t.id)))

  const submitError = editing ? save.error : create.error
  const submitting = create.isPending || save.isPending
  const canSubmit = agentIds.length > 0 && name.trim() !== "" && description.trim() !== ""

  function reset() {
    setAgentIds([])
    setSkillIds([])
    setToolIds([])
    setPackIds([])
    setName("")
    setDescription("")
    setEditing(null)
    create.reset()
    save.reset()
  }

  function toggleAgent(id: number) {
    const isAdding = !agentIds.includes(id)
    setAgentIds((prev) => toggle(prev, id))
    if (isAdding) {
      const agent = agents.data?.find((a) => a.id === id)
      if (!agent) return
      setSkillIds((prev) => unique([...prev, ...agent.skills.map((s) => s.id)]))
      setToolIds((prev) => unique([...prev, ...agent.tools.map((t) => t.id)]))
    }
  }

  function applyHint(hint: HintResponse) {
    const profile = hint.agent_profile
    if (profile) {
      setAgentIds((prev) => unique([profile.id, ...prev]))
    }
    setSkillIds(
      unique([...hint.skills.map((s) => s.id), ...(profile?.base_skills.map((s) => s.id) ?? [])]),
    )
    setToolIds(
      unique([...hint.tools.map((t) => t.id), ...(profile?.base_tools.map((t) => t.id) ?? [])]),
    )
    setPackIds(unique(hint.knowledge_packs.map((p) => p.id)))
  }

  function loadBundle(bundle: ConfigBundleRead) {
    const selection = selectionOf(bundle)
    setEditing(bundle)
    setAgentIds(selection.agent_ids)
    setSkillIds(selection.skill_ids)
    setToolIds(selection.tool_ids)
    setPackIds(selection.knowledge_pack_ids)
    setName(bundle.name)
    setDescription(bundle.description)
    create.reset()
    save.reset()
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  function submit() {
    if (agentIds.length === 0) return
    const selection = {
      agent_ids: agentIds,
      skill_ids: skillIds,
      tool_ids: toolIds,
      knowledge_pack_ids: packIds,
    }
    if (editing) {
      save.mutate(
        { original: editing, name: name.trim(), description: description.trim(), selection },
        { onSuccess: reset },
      )
    } else {
      create.mutate(
        {
          agent_id: agentIds[0],
          agent_ids: agentIds,
          name: name.trim(),
          description: description.trim(),
          skill_ids: skillIds,
          tool_ids: toolIds,
          knowledge_pack_ids: packIds,
        },
        { onSuccess: reset },
      )
    }
  }

  function deleteBundle(bundle: ConfigBundleRead) {
    if (!window.confirm(`Delete bundle "${bundle.name}"?`)) return
    remove.mutate(bundle.id, {
      onSuccess: () => {
        if (editing?.id === bundle.id) reset()
      },
    })
  }

  function saveToProfile() {
    if (!primaryAgent || agentIds.length !== 1) return
    const ok = window.confirm(
      `Overwrite skills and tools of the profile "${primaryAgent.agent_name}" with the current selection? This affects everyone who uses this profile.`,
    )
    if (ok) updateAgent.mutate({ id: primaryAgent.id, body: { skill_ids: skillIds, tool_ids: toolIds } })
  }

  const adminExtra =
    isAdmin && agentIds.length === 1 ? (
      <div className="space-y-2 border-t border-hairline/15 pt-4">
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          disabled={!primaryAgent || updateAgent.isPending}
          onClick={saveToProfile}
        >
          {updateAgent.isPending ? "Saving…" : "Save skills & tools to profile"}
        </Button>
        {updateAgent.isError ? (
          <Notice tone="error">{getErrorMessage(updateAgent.error)}</Notice>
        ) : updateAgent.isSuccess ? (
          <p className="text-xs text-muted-foreground">Profile updated.</p>
        ) : null}
      </div>
    ) : null

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-10">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          Configurator
        </p>
        <h1 className="mt-3 font-serif text-5xl">Build an agent bundle</h1>
        <p className="mt-3 text-muted-foreground">
          Pick one or multiple agent profiles, add skills, tools and knowledge, or let the assistant suggest a setup.
        </p>
      </header>

      <div className="grid gap-10 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-10">
          <HintPanel
            onApply={applyHint}
            onSkillSaved={(skill) => setSkillIds((prev) => unique([...prev, skill.id]))}
            configBundleId={editing?.id ?? null}
          />

          <AgentPicker
            agents={agents.data ?? []}
            selectedIds={agentIds}
            onToggle={toggleAgent}
            loading={agents.isPending}
            error={agents.error}
            action={
              <NewAgentForm
                skillIds={skillIds}
                toolIds={toolIds}
                packIds={packIds}
                onCreated={(newId) => setAgentIds((prev) => unique([...prev, newId]))}
              />
            }
          />

          <PickList
            title="Skills"
            items={(skills.data ?? []).map((s) => ({
              id: s.id,
              title: s.skill_name,
              description: s.description,
              badges: badgesOf(
                s.visibility === "private" && "private",
                baseSkills.has(s.id) && "in profile",
              ),
            }))}
            selected={skillIds}
            onToggle={(id) => setSkillIds((prev) => toggle(prev, id))}
            loading={skills.isPending}
            error={skills.error}
            emptyText="No skills yet."
            action={<NewSkillForm onCreated={(id) => setSkillIds((prev) => unique([...prev, id]))} />}
          />

          <PickList
            title="Tools"
            items={(tools.data ?? []).map((t) => ({
              id: t.id,
              title: t.tool_name,
              description: t.description,
              badges: badgesOf(baseTools.has(t.id) && "in profile"),
            }))}
            selected={toolIds}
            onToggle={(id) => setToolIds((prev) => toggle(prev, id))}
            loading={tools.isPending}
            error={tools.error}
            emptyText="No tools yet."
            action={<NewToolForm onCreated={(id) => setToolIds((prev) => unique([...prev, id]))} />}
          />

          <PickList
            title="Knowledge packs"
            items={(packs.data ?? []).map((p) => ({
              id: p.id,
              title: p.name,
              description: p.description,
              badges: [`v${p.version}`],
            }))}
            selected={packIds}
            onToggle={(id) => setPackIds((prev) => toggle(prev, id))}
            loading={packs.isPending}
            error={packs.error}
            emptyText="No knowledge packs yet."
          />
        </div>

        <SummaryPanel
          name={name}
          description={description}
          onNameChange={setName}
          onDescriptionChange={setDescription}
          agentName={selectedAgentNames}
          skills={skillIds.length}
          tools={toolIds.length}
          packs={packIds.length}
          editing={editing !== null}
          canSubmit={canSubmit}
          submitting={submitting}
          error={submitError}
          fieldErrors={fieldErrorsOf(submitError)}
          onSubmit={submit}
          onReset={reset}
          extra={adminExtra}
        />
      </div>

      <div className="mt-16 border-t border-hairline/15 pt-10">
        {remove.isError ? (
          <div className="mb-6">
            <Notice tone="error">{getErrorMessage(remove.error)}</Notice>
          </div>
        ) : null}
        <MyBundles
          agents={agents.data ?? []}
          activeId={editing?.id ?? null}
          deleting={remove.isPending}
          onEdit={loadBundle}
          onDelete={deleteBundle}
        />
      </div>
    </div>
  )
}