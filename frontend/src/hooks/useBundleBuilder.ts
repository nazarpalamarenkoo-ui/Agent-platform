import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  agentsApi,
  catalogApi,
  configBundlesApi,
  mySkillsApi,
  myToolsApi,
  skillsApi,
  toolsApi,
} from "@/api"
import { bundleKeys } from "@/hooks/useBundles"
import { catalogKeys } from "@/hooks/useCatalog"
import type {
  AgentCreate,
  AgentRead,
  AgentUpdate,
  BundleItems,
  ConfigBundleCreate,
  ConfigBundleRead,
  CustomAgentCreate,
  MySkillCreate,
  MyToolCreate,
  SkillCreate,
  ToolCreate,
} from "@/types/Index"

export interface BundleSelection {
  agent_ids: number[]
  skill_ids: number[]
  tool_ids: number[]
  knowledge_pack_ids: number[]
}

export function bundleAgentIdsOf(bundle: ConfigBundleRead): number[] {
  if (bundle.agent_profiles && bundle.agent_profiles.length > 0) {
    return bundle.agent_profiles.map((p) => p.id)
  }
  return bundle.agent_id !== null ? [bundle.agent_id] : []
}

export function formatBundleAgents(bundle: ConfigBundleRead, catalogAgents?: AgentRead[]): string {
  if (bundle.agent_profiles && bundle.agent_profiles.length > 0) {
    return bundle.agent_profiles.map((p) => p.agent_name).join(", ")
  }
  if (bundle.agent_id !== null) {
    return catalogAgents?.find((a) => a.id === bundle.agent_id)?.agent_name ?? `#${bundle.agent_id}`
  }
  return "No profile"
}

export function selectionOf(bundle: ConfigBundleRead): BundleSelection {
  return {
    agent_ids: bundleAgentIdsOf(bundle),
    skill_ids: bundle.skills.map((s) => s.id),
    tool_ids: bundle.tools.map((t) => t.id),
    knowledge_pack_ids: bundle.knowledge_packs.map((p) => p.id),
  }
}

function minus(a: number[], b: number[]): number[] {
  const exclude = new Set(b)
  return a.filter((id) => !exclude.has(id))
}

function isEmpty(items: BundleItems): boolean {
  return (
    (items.agent_ids?.length ?? 0) === 0 &&
    (items.skill_ids?.length ?? 0) === 0 &&
    (items.tool_ids?.length ?? 0) === 0 &&
    (items.knowledge_pack_ids?.length ?? 0) === 0
  )
}

export function useCatalogHint() {
  return useMutation({
    mutationFn: (intent: string) => catalogApi.hint({ intent }),
  })
}

export function useCreateBundle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ConfigBundleCreate) => configBundlesApi.create(body),
    onSuccess: (bundle) => {
      queryClient.setQueryData(bundleKeys.detail(bundle.id), bundle)
      void queryClient.invalidateQueries({ queryKey: bundleKeys.all })
    },
  })
}

interface SaveBundleArgs {
  original: ConfigBundleRead
  name: string
  description: string
  selection: BundleSelection
}

export function useSaveBundleChanges() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ original, name, description, selection }: SaveBundleArgs) => {
      const current = selectionOf(original)
      let result = original

      if (name !== original.name || description !== original.description) {
        result = await configBundlesApi.update(original.id, { name, description })
      }

      const added: BundleItems = {
        agent_ids: minus(selection.agent_ids, current.agent_ids),
        skill_ids: minus(selection.skill_ids, current.skill_ids),
        tool_ids: minus(selection.tool_ids, current.tool_ids),
        knowledge_pack_ids: minus(selection.knowledge_pack_ids, current.knowledge_pack_ids),
      }
      if (!isEmpty(added)) result = await configBundlesApi.addItems(original.id, added)

      const removed: BundleItems = {
        agent_ids: minus(current.agent_ids, selection.agent_ids),
        skill_ids: minus(current.skill_ids, selection.skill_ids),
        tool_ids: minus(current.tool_ids, selection.tool_ids),
        knowledge_pack_ids: minus(current.knowledge_pack_ids, selection.knowledge_pack_ids),
      }
      if (!isEmpty(removed)) result = await configBundlesApi.removeItems(original.id, removed)

      return result
    },
    onSuccess: (bundle) => {
      queryClient.setQueryData(bundleKeys.detail(bundle.id), bundle)
      void queryClient.invalidateQueries({ queryKey: bundleKeys.all })
    },
  })
}

export function useCreateAgent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AgentCreate) => agentsApi.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: catalogKeys.agents }),
  })
}

export function useUpdateAgent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: AgentUpdate }) => agentsApi.update(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: catalogKeys.agents }),
  })
}

export function useCreateSkill() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SkillCreate) => skillsApi.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: catalogKeys.skills }),
  })
}

export function useCreateTool() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ToolCreate) => toolsApi.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: catalogKeys.tools }),
  })
}

export function useCreateMySkill() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: MySkillCreate) => mySkillsApi.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: catalogKeys.skills }),
  })
}

export function useCreateMyTool() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: MyToolCreate) => myToolsApi.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: catalogKeys.tools }),
  })
}

export function useCreateCustomAgent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CustomAgentCreate) => agentsApi.createCustom(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: catalogKeys.agents })
      void queryClient.invalidateQueries({ queryKey: bundleKeys.all })
    },
  })
}