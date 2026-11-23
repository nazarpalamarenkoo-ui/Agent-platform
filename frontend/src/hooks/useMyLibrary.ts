import { useQuery } from "@tanstack/react-query"
import { mySkillsApi, myToolsApi } from "@/api"
import { catalogKeys } from "@/hooks/useCatalog"

const STALE = 60_000
const PAGE = { limit: 500 }

export const myLibraryKeys = {
  skills: [...catalogKeys.skills, "mine"] as const,
  tools: [...catalogKeys.tools, "mine"] as const,
}

export function useMySkills() {
  return useQuery({
    queryKey: myLibraryKeys.skills,
    queryFn: ({ signal }) => mySkillsApi.list(PAGE, { signal }),
    staleTime: STALE,
  })
}

export function useMyTools() {
  return useQuery({
    queryKey: myLibraryKeys.tools,
    queryFn: ({ signal }) => myToolsApi.list(PAGE, { signal }),
    staleTime: STALE,
  })
}