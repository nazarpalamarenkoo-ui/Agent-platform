import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { adminApi, adminUserContentApi } from "@/api"

const KEY = ["admin", "users"] as const

export const adminUserKeys = {
  overview: (id: number) => [...KEY, id, "overview"] as const,
  skills: (id: number, archived: boolean) => [...KEY, id, "skills", archived] as const,
  tools: (id: number, archived: boolean) => [...KEY, id, "tools", archived] as const,
  skill: (id: number, skillId: number) => [...KEY, id, "skill", skillId] as const,
}

export function useAdminUsers() {
  return useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) => adminApi.users({ limit: 200 }, { signal }),
  })
}

function useRefreshUsers() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: KEY })
}

export function useSetTokenLimit() {
  const refresh = useRefreshUsers()
  return useMutation({
    mutationFn: ({ id, tokenLimit }: { id: number; tokenLimit: number }) =>
      adminApi.setTokenLimit(id, { token_limit: tokenLimit }),
    onSuccess: refresh,
  })
}

export function useResetUsage() {
  const refresh = useRefreshUsers()
  return useMutation({
    mutationFn: (id: number) => adminApi.resetUsage(id),
    onSuccess: refresh,
  })
}
export function useUserOverview(userId: number) {
  return useQuery({
    queryKey: adminUserKeys.overview(userId),
    queryFn: ({ signal }) => adminUserContentApi.overview(userId, { signal }),
  })
}

export function useUserSkills(userId: number, includeArchived: boolean) {
  return useQuery({
    queryKey: adminUserKeys.skills(userId, includeArchived),
    queryFn: ({ signal }) =>
      adminUserContentApi.skills(
        userId,
        { include_archived: includeArchived, limit: 200 },
        { signal },
      ),
  })
}

export function useUserTools(userId: number, includeArchived: boolean) {
  return useQuery({
    queryKey: adminUserKeys.tools(userId, includeArchived),
    queryFn: ({ signal }) =>
      adminUserContentApi.tools(userId, { include_archived: includeArchived }, { signal }),
  })
}

export function useUserSkillContent(userId: number, skillId: number, enabled: boolean) {
  return useQuery({
    queryKey: adminUserKeys.skill(userId, skillId),
    enabled,
    queryFn: ({ signal }) => adminUserContentApi.skill(userId, skillId, { signal }),
  })
}

export function useArchiveUserSkill(userId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ skillId, reason }: { skillId: number; reason: string }) =>
      adminUserContentApi.archiveSkill(userId, skillId, { reason }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: [...KEY, userId] }),
  })
}