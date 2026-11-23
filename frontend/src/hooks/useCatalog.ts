import { useQuery } from "@tanstack/react-query"
import { agentsApi, knowledgePacksApi, skillsApi, toolsApi } from "@/api"

const STALE = 5 * 60_000
const PAGE = { limit: 500 }

export const catalogKeys = {
  agents: ["catalog", "agents"] as const,
  skills: ["catalog", "skills"] as const,
  tools: ["catalog", "tools"] as const,
  packs: ["catalog", "packs"] as const,
}

export function useAgents() {
  return useQuery({
    queryKey: catalogKeys.agents,
    queryFn: ({ signal }) => agentsApi.list(PAGE, { signal }),
    staleTime: STALE,
  })
}

export function useSkills() {
  return useQuery({
    queryKey: catalogKeys.skills,
    queryFn: ({ signal }) => skillsApi.list(PAGE, { signal }),
    staleTime: STALE,
  })
}

export function useTools() {
  return useQuery({
    queryKey: catalogKeys.tools,
    queryFn: ({ signal }) => toolsApi.list(PAGE, { signal }),
    staleTime: STALE,
  })
}

export function usePacks() {
  return useQuery({
    queryKey: catalogKeys.packs,
    queryFn: ({ signal }) => knowledgePacksApi.list(PAGE, { signal }),
    staleTime: STALE,
  })
}